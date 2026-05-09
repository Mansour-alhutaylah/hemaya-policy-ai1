import json
import os
import re
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()


from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend import auth, database, models, schemas
from backend.database import get_db, set_user_context
from backend.email_utils import (
    send_otp_email,
    send_password_reset_email,
    EmailDeliveryError,
)
from backend.text_extractor import extract_text, extract_text_segments
from backend.checkpoint_analyzer import (
    run_checkpoint_analysis, chat_with_context, chat_with_user_context,
    run_simulation, generate_insights, explain_mapping,
)
from backend.ecc2_analyzer import run_ecc2_analysis, verify_ecc2_loaded
from backend.sacs002_analyzer import run_sacs002_analysis
from backend.vector_store import get_embeddings, store_chunks_with_embeddings, delete_policy_chunks
from backend.chunker import chunk_text, chunk_text_segments
from backend.routers.remediation import router as remediation_router
from backend.routers.reports_export import router as export_router
from backend.routers.explainability import router as explainability_router


app = FastAPI()
app.include_router(remediation_router)
app.include_router(export_router)
app.include_router(explainability_router)


@app.on_event("startup")
def startup_seed():
    """
    Startup tasks split into two tiers:

    Tier A — DDL migrations (ALTER TABLE, CREATE TABLE):
        Only run when RUN_STARTUP_MIGRATIONS=true.
        Safe to skip on normal restarts once schema is up to date.
        Set this flag when deploying a new version that adds columns or tables.

    Tier B — Data seeds (always run, idempotent):
        seed_checkpoints, framework row inserts, SACS-002 auto-import.
        These use INSERT ... ON CONFLICT DO NOTHING and are safe every boot.
    """
    from backend.checkpoint_seed import seed_checkpoints
    from sqlalchemy import text as _ddl

    _run_migrations = os.getenv("RUN_STARTUP_MIGRATIONS", "false").lower() == "true"

    if _run_migrations:
        # Idempotent DDL — adds new columns and tables without touching existing data.
        # remediation_drafts and policy_versions arrived from remote (policy-versioning feature).
        try:
            with database.engine.connect() as _conn:
                _conn.execute(_ddl("ALTER TABLE gaps ADD COLUMN IF NOT EXISTS mapping_id  VARCHAR"))
                _conn.execute(_ddl("ALTER TABLE gaps ADD COLUMN IF NOT EXISTS owner_name  VARCHAR"))
                _conn.execute(_ddl("""
                    CREATE TABLE IF NOT EXISTS remediation_drafts (
                        id                   VARCHAR PRIMARY KEY,
                        policy_id            VARCHAR NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
                        mapping_review_id    VARCHAR REFERENCES mapping_reviews(id) ON DELETE SET NULL,
                        control_id           VARCHAR REFERENCES control_library(id) ON DELETE SET NULL,
                        framework_id         VARCHAR REFERENCES frameworks(id) ON DELETE SET NULL,
                        missing_requirements JSONB   NOT NULL DEFAULT '[]',
                        ai_rationale         TEXT,
                        suggested_policy_text TEXT   NOT NULL,
                        section_headers      JSONB,
                        remediation_status   VARCHAR NOT NULL DEFAULT 'draft',
                        review_notes         TEXT,
                        created_by           UUID    REFERENCES users(id) ON DELETE SET NULL,
                        reviewed_by          UUID    REFERENCES users(id) ON DELETE SET NULL,
                        reviewed_at          TIMESTAMPTZ,
                        created_at           TIMESTAMPTZ DEFAULT NOW(),
                        updated_at           TIMESTAMPTZ DEFAULT NOW()
                    )
                """))
                _conn.execute(_ddl("CREATE INDEX IF NOT EXISTS ix_remediation_drafts_policy_id ON remediation_drafts(policy_id)"))
                _conn.execute(_ddl("""
                    CREATE TABLE IF NOT EXISTS policy_versions (
                        id                    VARCHAR PRIMARY KEY,
                        policy_id             VARCHAR NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
                        version_number        INTEGER NOT NULL,
                        version_type          VARCHAR NOT NULL,
                        content               TEXT    NOT NULL,
                        compliance_score      FLOAT,
                        remediation_draft_id  VARCHAR REFERENCES remediation_drafts(id) ON DELETE SET NULL,
                        change_summary        TEXT,
                        created_by            UUID    REFERENCES users(id) ON DELETE SET NULL,
                        created_at            TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE (policy_id, version_number)
                    )
                """))
                _conn.execute(_ddl("CREATE INDEX IF NOT EXISTS ix_policy_versions_policy_id ON policy_versions(policy_id)"))
                _conn.commit()
            print("[startup] gaps + remediation_drafts + policy_versions migrations complete")
        except Exception as e:
            print(f"[startup] Migration warning: {e}")

    if _run_migrations:
        # Idempotent DDL — adds new columns without touching existing data.
        try:
            with database.engine.connect() as _conn:
                _conn.execute(_ddl("ALTER TABLE gaps ADD COLUMN IF NOT EXISTS mapping_id  VARCHAR"))
                _conn.execute(_ddl("ALTER TABLE gaps ADD COLUMN IF NOT EXISTS owner_name  VARCHAR"))
                _conn.commit()
            print("[startup] gaps column migration complete")
        except Exception as e:
            print(f"[startup] Migration warning (gaps): {e}")

        # Create sacs002_metadata if it doesn't exist yet.
        # Uses TEXT instead of ENUM types to avoid DO$$ type-creation noise.
        # FK to ecc_framework omitted to tolerate cold-start ordering.
        try:
            with database.engine.connect() as _conn:
                _conn.execute(_ddl("""
                    CREATE TABLE IF NOT EXISTS sacs002_metadata (
                        id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        framework_id            VARCHAR(50)  NOT NULL DEFAULT 'SACS-002',
                        control_code            VARCHAR(30)  NOT NULL,
                        section                 TEXT,
                        nist_function_code      VARCHAR(10),
                        nist_function_name      TEXT,
                        nist_category_code      VARCHAR(20),
                        nist_category_name      TEXT,
                        applicable_classes      JSONB,
                        governance_control      BOOLEAN DEFAULT FALSE,
                        technical_control       BOOLEAN DEFAULT FALSE,
                        operational_control     BOOLEAN DEFAULT FALSE,
                        review_required         BOOLEAN DEFAULT FALSE,
                        approval_required       BOOLEAN DEFAULT FALSE,
                        testing_required        BOOLEAN DEFAULT FALSE,
                        monitoring_required     BOOLEAN DEFAULT FALSE,
                        third_party_assessment  BOOLEAN DEFAULT FALSE,
                        created_at              TIMESTAMPTZ DEFAULT NOW(),
                        CONSTRAINT uq_sacs002_meta_control UNIQUE (framework_id, control_code)
                    )
                """))
                _conn.execute(_ddl(
                    "CREATE INDEX IF NOT EXISTS idx_sacs002_meta_nist_cat "
                    "ON sacs002_metadata (nist_category_code)"
                ))
                _conn.execute(_ddl(
                    "CREATE INDEX IF NOT EXISTS idx_sacs002_meta_section "
                    "ON sacs002_metadata (section)"
                ))
                _conn.commit()
            print("[startup] sacs002_metadata table ensured")
        except Exception as e:
            print(f"[startup] sacs002_metadata DDL warning: {e}")
    else:
        print("[startup] DDL migrations skipped (set RUN_STARTUP_MIGRATIONS=true to run)")

    # ── Tier B: data seeds — always run, idempotent ───────────────────────
    db = database.SessionLocal()
    try:
        try:
            seed_checkpoints(db)
        except Exception as e:
            print(f"[startup] seed_checkpoints warning: {e}")

        # Ensure ECC-2:2024 and SACS-002 exist in the frameworks master table
        # so they appear in the upload dropdown immediately.
        try:
            from backend.ecc2_analyzer import _ensure_framework_row as _ecc2_row
            _ecc2_row(db)
            print("[startup] ECC-2:2024 framework row ensured")
        except Exception as e:
            print(f"[startup] ECC-2:2024 row warning: {e}")
        try:
            from backend.sacs002_analyzer import _ensure_framework_row as _sacs002_row
            _sacs002_row(db)
            print("[startup] SACS-002 framework row ensured")
        except Exception as e:
            print(f"[startup] SACS-002 row warning: {e}")

        # Auto-import SACS-002 from bundled JSON files if structured tables are empty.
        # Skips immediately (single COUNT query) when data already exists.
        try:
            from backend.sacs002_analyzer import seed_sacs002_if_empty
            n = seed_sacs002_if_empty(db)
            if n > 0:
                print(f"[startup] SACS-002 structured data ready ({n} controls)")
        except Exception as e:
            print(f"[startup] SACS-002 auto-import warning: {e}")
    finally:
        db.close()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    print(f"\n[UNHANDLED ERROR] {request.method} {request.url}\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# OAuth2 dependency for JWT bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
    set_user_context(db, user.id)
    return user


# ─── Admin authorisation ────────────────────────────────────────────────────
# Defined here (above all routes) so any endpoint can depend on it. The
# admin-only sections lower in this file reuse the same constant + helper.
ADMIN_EMAIL = "himayaadmin@gmail.com"


def require_admin(current_user: models.User = Depends(get_current_user)):
    """Dependency: raises 403 if the caller is not the admin account."""
    if current_user.email != ADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def serialize(obj: Any):
    return jsonable_encoder(obj)


def set_policy_progress(db: Session, policy_id: str, percent: int, stage: str = "") -> None:
    """Atomically update a policy's processing progress (0..100) + stage label.

    Used by the upload + analysis pipelines so the Policies page can show
    "Processing • NN%". Failures are swallowed (with rollback) — progress
    is purely informational and must never block the real work.
    """
    from sqlalchemy import text as _t
    try:
        pct = max(0, min(100, int(percent)))
    except Exception:
        pct = 0
    try:
        db.execute(
            _t("UPDATE policies SET progress = :p, progress_stage = :s WHERE id = :pid"),
            {"p": pct, "s": stage or None, "pid": policy_id},
        )
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[set_policy_progress] {policy_id} -> {pct}% '{stage}' failed: {e}")


ENTITY_MAP: Dict[str, Any] = {
    "Policy": models.Policy,
    "ComplianceResult": models.ComplianceResult,
    "Gap": models.Gap,
    "MappingReview": models.MappingReview,
    "Report": models.Report,
    "AuditLog": models.AuditLog,
    "ControlLibrary": models.ControlLibrary,
    "AIInsight": models.AIInsight,
    "Framework": models.Framework,
}


# Auth Routes
@app.post("/api/auth/register")
async def register(user: schemas.RegisterRequest, db: Session = Depends(get_db)):
    normalized_email = user.email.lower()
    db_user = db.query(models.User).filter(models.User.email == normalized_email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # bcrypt limit (72 bytes)
    if len(user.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be <= 72 bytes")

    hashed_password = auth.get_password_hash(user.password)

    new_user = models.User(
        email=normalized_email,
        password_hash=hashed_password,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        is_verified=False,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Generate OTP, hash it, persist it, then send email
    otp = auth.generate_otp()
    token = models.OTPToken(
        user_id=new_user.id,
        otp_hash=auth.hash_otp(otp),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(token)
    db.commit()

    try:
        await send_otp_email(new_user.email, otp)
    except EmailDeliveryError as e:
        raise HTTPException(status_code=503, detail=e.public_message)

    return {"message": "Registration successful. Please check your email for the verification code."}



def _get_setting(db, key: str, default: str) -> str:
    """Read a single value from system_settings, returning default on any error."""
    from sqlalchemy import text as _t
    try:
        row = db.execute(_t("SELECT value FROM system_settings WHERE key = :k"), {"k": key}).fetchone()
        return row[0] if row else default
    except Exception:
        # Roll back so the connection doesn't stay in InFailedSqlTransaction state
        try:
            db.rollback()
        except Exception:
            pass
        return default


@app.post("/api/auth/login")
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    from sqlalchemy import text as _t
    from datetime import timedelta

    max_attempts       = int(_get_setting(db, "max_login_attempts",       "5"))
    lockout_minutes    = int(_get_setting(db, "lockout_duration_minutes",  "15"))
    session_timeout    = int(_get_setting(db, "session_timeout_minutes",   "60"))

    db_user = db.query(models.User).filter(models.User.email == user.email.lower()).first()

    if db_user:
        # Check whether this account is currently locked out
        try:
            row = db.execute(
                _t("SELECT failed_login_attempts, locked_until FROM users WHERE id = :uid"),
                {"uid": str(db_user.id)},
            ).fetchone()
            attempts     = int(row[0] or 0) if row else 0
            locked_until = row[1] if row else None
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            attempts = 0
            locked_until = None

        if locked_until is not None:
            from datetime import datetime, timezone as _tz
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=_tz.utc)
            if datetime.now(_tz.utc) < locked_until:
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed login attempts. Please try again later.",
                )


    if not db_user or not auth.verify_password(user.password, db_user.password_hash):
        # Record the failed attempt
        if db_user:
            new_attempts = attempts + 1
            from datetime import datetime, timezone as _tz
            new_locked = (
                datetime.now(_tz.utc) + timedelta(minutes=lockout_minutes)
                if new_attempts >= max_attempts else None
            )
            try:
                db.execute(
                    _t("UPDATE users SET failed_login_attempts = :a, locked_until = :lu WHERE id = :uid"),
                    {"a": new_attempts, "lu": new_locked, "uid": str(db_user.id)},
                )
                db.commit()
            except Exception:
                db.rollback()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not db_user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Email not verified. Please check your inbox for the verification code.",
        )

    # Successful login — reset lockout counters
    try:
        db.execute(
            _t("UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE id = :uid"),
            {"uid": str(db_user.id)},
        )
        db.commit()
    except Exception:
        db.rollback()

    access_token = auth.create_access_token(
        data={"sub": db_user.email},
        expires_delta=timedelta(minutes=session_timeout),
    )
    return {
        "token": access_token,
        "session_timeout_minutes": session_timeout,
        "user": {
            "id": str(db_user.id),
            "email": db_user.email,
            "first_name": db_user.first_name,
            "last_name": db_user.last_name,
            "phone": db_user.phone,
        },
    }


@app.post("/api/auth/verify-otp")
def verify_otp(req: schemas.OTPVerifyRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == req.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = (
        db.query(models.OTPToken)
        .filter(models.OTPToken.user_id == user.id)
        .order_by(models.OTPToken.created_at.desc())
        .first()
    )

    if not token:
        raise HTTPException(
            status_code=400,
            detail="No verification code found. Please request a new one.",
        )

    if token.failed_attempts >= 3:
        db.delete(token)
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Too many failed attempts. Please request a new code.",
        )

    if token.expires_at < datetime.now(timezone.utc):
        db.delete(token)
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Verification code has expired. Please request a new one.",
        )

    if not auth.verify_otp_code(req.otp, token.otp_hash):
        token.failed_attempts += 1
        db.commit()
        if token.failed_attempts >= 3:
            db.delete(token)
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="Incorrect code. Too many attempts — please request a new code.",
            )
        remaining = 3 - token.failed_attempts
        raise HTTPException(
            status_code=400,
            detail=f"Incorrect verification code. {remaining} attempt(s) remaining.",
        )

    # OTP is valid — mark user as verified and delete the token
    user.is_verified = True
    db.delete(token)
    db.commit()
    return {"message": "Email verified successfully. You can now log in."}


@app.post("/api/auth/resend-otp")
async def resend_otp(req: schemas.ResendOTPRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == req.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_verified:
        raise HTTPException(status_code=400, detail="This email address is already verified.")

    # Enforce 60-second cooldown based on the most recent token's created_at
    existing = (
        db.query(models.OTPToken)
        .filter(models.OTPToken.user_id == user.id)
        .order_by(models.OTPToken.created_at.desc())
        .first()
    )

    if existing:
        cooldown_ends = existing.created_at + timedelta(seconds=60)
        if datetime.now(timezone.utc) < cooldown_ends:
            wait = int((cooldown_ends - datetime.now(timezone.utc)).total_seconds())
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {wait} seconds before requesting a new code.",
            )
        # Delete all stale tokens for this user before issuing a new one
        db.query(models.OTPToken).filter(models.OTPToken.user_id == user.id).delete()

    otp = auth.generate_otp()
    new_token = models.OTPToken(
        user_id=user.id,
        otp_hash=auth.hash_otp(otp),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(new_token)
    db.commit()

    try:
        await send_otp_email(user.email, otp)
    except EmailDeliveryError as e:
        # Roll the token back so the user can request again immediately.
        try:
            db.query(models.OTPToken).filter(
                models.OTPToken.id == new_token.id
            ).delete()
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=503, detail=e.public_message)

    return {"message": "Verification code resent. Please check your email."}


@app.post("/api/auth/forgot-password")
async def forgot_password(req: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == req.email.lower()).first()
    # Always return the same message to prevent email enumeration
    generic_response = {"message": "If this email is registered, you will receive a reset code."}
    if not user:
        return generic_response

    # Enforce 60-second cooldown
    existing = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.user_id == user.id)
        .order_by(models.PasswordResetToken.created_at.desc())
        .first()
    )
    if existing:
        cooldown_ends = existing.created_at + timedelta(seconds=60)
        if datetime.now(timezone.utc) < cooldown_ends:
            # Silently drop — returning a different status code would reveal
            # that this email is registered (enumeration attack vector).
            return generic_response
        db.query(models.PasswordResetToken).filter(models.PasswordResetToken.user_id == user.id).delete()

    otp = auth.generate_otp()
    token = models.PasswordResetToken(
        user_id=user.id,
        otp_hash=auth.hash_otp(otp),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(token)
    db.commit()

    try:
        await send_password_reset_email(user.email, otp)
    except EmailDeliveryError as e:
        # Roll back the token so the user can retry without hitting the
        # 60-second cooldown. Surface a friendly message instead of the
        # raw SMTP exception.
        try:
            db.query(models.PasswordResetToken).filter(
                models.PasswordResetToken.id == token.id
            ).delete()
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=503, detail=e.public_message)

    return generic_response


@app.post("/api/auth/verify-reset-otp")
def verify_reset_otp(req: schemas.VerifyResetOTPRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == req.email.lower()).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid request.")

    token = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.user_id == user.id)
        .order_by(models.PasswordResetToken.created_at.desc())
        .first()
    )

    if not token:
        raise HTTPException(status_code=400, detail="No reset code found. Please request a new one.")

    if token.failed_attempts >= 3:
        db.delete(token)
        db.commit()
        raise HTTPException(status_code=400, detail="Too many failed attempts. Please request a new code.")

    if token.expires_at < datetime.now(timezone.utc):
        db.delete(token)
        db.commit()
        raise HTTPException(status_code=400, detail="Reset code has expired. Please request a new one.")

    if not auth.verify_otp_code(req.otp, token.otp_hash):
        token.failed_attempts += 1
        db.commit()
        if token.failed_attempts >= 3:
            db.delete(token)
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="Incorrect code. Too many attempts — please request a new code.",
            )
        remaining = 3 - token.failed_attempts
        raise HTTPException(
            status_code=400,
            detail=f"Incorrect code. {remaining} attempt(s) remaining.",
        )

    # OTP valid — delete it and return a short-lived signed reset token
    db.delete(token)
    db.commit()
    return {"reset_token": auth.create_reset_token(user.email)}


@app.post("/api/auth/reset-password")
def reset_password(req: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    email = auth.decode_reset_token(req.reset_token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid request.")

    if len(req.new_password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be <= 72 bytes")

    user.password_hash = auth.get_password_hash(req.new_password)
    db.commit()
    return {"message": "Password reset successfully. You can now log in."}


@app.post("/api/auth/change-password")
def change_password(
    req: schemas.ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Authenticated password change. Verifies the current password before
    re-hashing the new one. Authorization is implicit: the JWT identifies the
    only account that can be modified."""
    if not auth.verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    if req.current_password == req.new_password:
        raise HTTPException(
            status_code=400,
            detail="New password must be different from the current password.",
        )

    if len(req.new_password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be <= 72 bytes")

    current_user.password_hash = auth.get_password_hash(req.new_password)
    db.commit()
    return {"message": "Password updated successfully."}


@app.get("/api/auth/me", response_model=schemas.User)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@app.post("/api/auth/updateMe")
def update_me(settings: Dict[str, Any], current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.settings = settings.get("settings", settings)
    db.commit()
    return {"ok": True}


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".xlsx", ".xls"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# Policy upload — creates policy row, embeds chunks, returns policy id
@app.post("/api/integrations/upload")
async def upload_policy(
    file: UploadFile = File(...),
    department: str = Form("General"),
    version: str = Form("1.0"),
    description: str = Form(""),
    framework: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from sqlalchemy import text as _sql

    policy_id = str(uuid.uuid4())
    original_name = file.filename or "upload"
    ext = Path(original_name).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Validate the selected framework against frameworks present in the DB.
    framework_value = (framework or "").strip() or None
    if framework_value:
        exists = db.execute(_sql(
            "SELECT 1 FROM frameworks WHERE name = :name LIMIT 1"
        ), {"name": framework_value}).fetchone()
        if not exists:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown framework '{framework_value}'. Upload a reference document for it first.",
            )

    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 50 MB limit")

    file_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{original_name}"
    dest = UPLOAD_DIR / file_name
    dest.write_bytes(raw)

    # Save policy row with status='processing' and progress=5 (file accepted).
    db.execute(_sql("""
        INSERT INTO policies
        (id, file_name, description, department, version, status, progress, progress_stage,
         file_url, file_type, content_preview, framework_code, owner_id,
         uploaded_at, created_at)
        VALUES (:id,:fn,:desc,:dept,:ver,'processing', 5, 'File accepted',
                :furl,:ft,:prev,:fwc,:oid,:at,:cat)
    """), {
        "id": policy_id,
        "fn": original_name,
        "desc": description or original_name,
        "dept": department,
        "ver": version,
        "furl": f"/uploads/{file_name}",
        "ft": ext.replace(".", "").upper(),
        "prev": "",
        "fwc": framework_value,
        "oid": str(current_user.id),
        "at": datetime.now(timezone.utc),
        "cat": datetime.now(timezone.utc),
    })
    db.commit()

    # Extract text — Phase 11 uses the segmented extractor so each chunk
    # carries page_number (PDF) or paragraph_index (DOCX). For TXT/XLSX
    # both source fields stay NULL. content_preview keeps the joined text
    # for keyword search and downstream callers that expect a string.
    set_policy_progress(db, policy_id, 15, "Extracting text")
    segments = []
    try:
        segments = extract_text_segments(str(dest), ext)
    except Exception as e:
        print(f"  [upload] segmented extraction failed: {e}; "
              f"falling back to plain extract_text")
        segments = []
    if not segments:
        # Final fallback: legacy extractor produces plain text but no
        # source attribution. Wrap in a single segment so downstream
        # chunking still works.
        try:
            content = extract_text(str(dest), ext)
        except TypeError:
            content = extract_text(str(dest))
        if content and not content.startswith("[Extraction error"):
            segments = [{"text": content, "page_number": None,
                         "paragraph_index": None}]
    content = "\n".join(s["text"] for s in segments) if segments else ""
    set_policy_progress(db, policy_id, 30, "Text extracted")

    # Save full content for keyword search during analysis
    if content:
        db.execute(_sql(
            "UPDATE policies SET content_preview = :content WHERE id = :pid"
        ), {"content": content, "pid": policy_id})
        db.commit()

    # Chunk and embed the full text — Phase 11 uses the source-aware
    # chunker so each chunk carries page_number / paragraph_index.
    chunks_count = 0
    if segments:
        try:
            set_policy_progress(db, policy_id, 45, "Chunking document")
            chunks = chunk_text_segments(segments)
            if chunks:
                set_policy_progress(db, policy_id, 60, f"Embedding {len(chunks)} chunks")
                embeddings = await get_embeddings([c["text"] for c in chunks])
                set_policy_progress(db, policy_id, 85, "Storing embeddings")
                store_chunks_with_embeddings(db, policy_id, chunks, embeddings)
                chunks_count = len(chunks)
                print(f"  Embedded {chunks_count} chunks for {original_name}")
        except Exception as e:
            print(f"  Embedding error (will auto-embed during analysis): {e}")

    # Mark as uploaded (100%, ready for analysis)
    db.execute(_sql(
        "UPDATE policies SET status='uploaded', progress=100, progress_stage='Ready' WHERE id=:pid"
    ), {"pid": policy_id})
    db.commit()
    print(f"Policy saved: {original_name}")

    # Audit log
    try:
        db.execute(_sql("""
            INSERT INTO audit_logs
            (id, actor_id, action, target_type, target_id, details, timestamp)
            VALUES (:id,:aid,'upload_policy','policy',:tid,:det,:ts)
        """), {
            "id": str(uuid.uuid4()),
            "aid": str(current_user.id) if hasattr(current_user, "id") else None,
            "tid": policy_id,
            "det": json.dumps({"file_name": original_name, "chunks": chunks_count}),
            "ts": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as _e:
        print(f"Audit log warning: {_e}")

    return {
        "id": policy_id,
        "file_name": original_name,
        "file_url": f"/uploads/{file_name}",
        "content_preview": content[:500] if content else "",
        "status": "uploaded",
        "chunks": chunks_count,
    }


# ━━━ Dashboard Stats ━━━
@app.get("/api/dashboard/stats")
def dashboard_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    policy_id: Optional[str] = None,
):
    from sqlalchemy import text as _t

    is_admin = current_user.email == ADMIN_EMAIL

    # Build WHERE fragments — scope by specific policy and/or current user.
    # Admin sees all; regular users only see their own policies.
    policy_filter_cr  = "AND cr.policy_id = :pid" if policy_id else ""
    policy_filter_gap = "AND g.policy_id = :pid"  if policy_id else ""
    user_filter_cr    = "" if is_admin else "AND p.owner_id = :uid"
    user_filter_gap   = "" if is_admin else (
        "AND g.policy_id IN (SELECT id FROM policies WHERE owner_id = :uid)"
    )
    bind = {"pid": policy_id, "uid": str(current_user.id)}

    # Latest compliance result per framework (scoped to user's policies)
    rows = db.execute(_t(f"""
        SELECT DISTINCT ON (f.name)
               f.name, cr.compliance_score,
               cr.controls_covered, cr.controls_partial, cr.controls_missing
        FROM compliance_results cr
        JOIN policies p ON p.id = cr.policy_id
        LEFT JOIN frameworks f ON cr.framework_id = f.id
        WHERE 1=1 {policy_filter_cr} {user_filter_cr}
        ORDER BY f.name, cr.analyzed_at DESC
    """), bind).fetchall()

    framework_scores = [
        {"framework": r[0] or "Unknown", "score": round(r[1] or 0, 1),
         "covered": r[2] or 0, "partial": r[3] or 0, "missing": r[4] or 0}
        for r in rows
    ]
    security_score = (
        round(sum(r[1] or 0 for r in rows) / len(rows), 1) if rows else 0
    )

    # Open gaps (scoped to user's policies)
    open_gaps = db.execute(_t(
        f"SELECT COUNT(*) FROM gaps g WHERE g.status='Open' "
        f"{policy_filter_gap} {user_filter_gap}"
    ), bind).fetchone()[0]

    # Severity distribution
    sev_rows = db.execute(_t(
        f"SELECT g.severity, COUNT(*) FROM gaps g WHERE g.status='Open' "
        f"{policy_filter_gap} {user_filter_gap} GROUP BY g.severity"
    ), bind).fetchall()
    severity_distribution = {r[0]: r[1] for r in sev_rows}

    # Controls mapped
    controls_mapped = sum(r[2] or 0 for r in rows)

    # Status overview
    status_overview = {
        "compliant": sum(r[2] or 0 for r in rows),
        "partial":   sum(r[3] or 0 for r in rows),
        "non_compliant": sum(r[4] or 0 for r in rows),
    }

    return {
        "security_score": security_score,
        "framework_scores": framework_scores,
        "open_gaps": open_gaps,
        "severity_distribution": severity_distribution,
        "controls_mapped": controls_mapped,
        "status_overview": status_overview,
    }


# ━━━ Dedicated entity routes (raw SQL, correct column names) ━━━
# Must be defined BEFORE the generic /api/entities/{entity} route

@app.get("/api/entities/Framework")
def get_frameworks(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List frameworks that actually have a reference document loaded
    (chunks > 0) — i.e. frameworks usable for policy analysis."""
    from sqlalchemy import text as _t
    params = dict(request.query_params)
    include_empty = params.get("include_empty") == "true"

    # Known structured frameworks: always appear in the dropdown regardless of
    # whether their ecc_framework rows have been imported yet. Structured
    # frameworks use dedicated DB tables rather than uploaded PDF chunks.
    _STRUCTURED_NAMES = ("'ECC-2:2024'", "'SACS-002'")
    _structured_name_list = ", ".join(_STRUCTURED_NAMES)

    # is_structured = TRUE if ecc_framework has rows for this framework, OR
    # if the name is a known structured framework (covers pre-import state).
    _structured_subq = (
        f"(EXISTS (SELECT 1 FROM ecc_framework ef WHERE ef.framework_id = f.name LIMIT 1)"
        f" OR f.name IN ({_structured_name_list}))"
    )

    # Debug/test entries have names starting with '_'. Exclude them from every
    # non-admin query so they never reach the production dropdown.
    _no_debug = "f.name NOT LIKE '\\_%%' ESCAPE '\\'"

    rich_with_empty = f"""
        SELECT f.id, f.name, f.description, f.version,
               f.original_file_name, f.file_url, f.file_type, f.file_size,
               f.uploaded_at, u.email AS uploaded_by,
               COALESCE(c.chunks, 0) AS chunks,
               {_structured_subq} AS is_structured
        FROM frameworks f
        LEFT JOIN users u ON u.id = f.uploaded_by
        LEFT JOIN (
            SELECT framework_id, COUNT(*) AS chunks
            FROM framework_chunks
            GROUP BY framework_id
        ) c ON c.framework_id = f.id
        ORDER BY f.name ASC
    """
    rich_loaded_only = f"""
        SELECT f.id, f.name, f.description, f.version,
               f.original_file_name, f.file_url, f.file_type, f.file_size,
               f.uploaded_at, u.email AS uploaded_by,
               COUNT(fc.*) AS chunks,
               {_structured_subq} AS is_structured
        FROM frameworks f
        LEFT JOIN users u ON u.id = f.uploaded_by
        LEFT JOIN framework_chunks fc ON fc.framework_id = f.id
        WHERE {_no_debug}
        GROUP BY f.id, u.email
        HAVING COUNT(fc.*) > 0
           OR {_structured_subq}
        ORDER BY f.name ASC
    """
    basic_with_empty = f"""
        SELECT f.id, f.name, f.description,
               COALESCE(c.chunks, 0) AS chunks,
               {_structured_subq} AS is_structured
        FROM frameworks f
        LEFT JOIN (
            SELECT framework_id, COUNT(*) AS chunks
            FROM framework_chunks GROUP BY framework_id
        ) c ON c.framework_id = f.id
        ORDER BY f.name ASC
    """
    basic_loaded_only = f"""
        SELECT f.id, f.name, f.description, COUNT(fc.*) AS chunks,
               {_structured_subq} AS is_structured
        FROM frameworks f
        LEFT JOIN framework_chunks fc ON fc.framework_id = f.id
        WHERE {_no_debug}
        GROUP BY f.id, f.name, f.description
        HAVING COUNT(fc.*) > 0
           OR {_structured_subq}
        ORDER BY f.name ASC
    """

    rich = True
    try:
        rows = db.execute(_t(rich_with_empty if include_empty else rich_loaded_only)).fetchall()
    except Exception as e:
        # File columns missing — fall back to the basic shape so the page
        # still loads (and the upload modal etc. still works).
        print(f"[get_frameworks] rich query failed, falling back: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        rich = False
        rows = db.execute(_t(basic_with_empty if include_empty else basic_loaded_only)).fetchall()

    if rich:
        return [
            {
                "id": r[0], "name": r[1], "description": r[2], "version": r[3],
                "original_file_name": r[4], "file_url": r[5], "file_type": r[6],
                "file_size": r[7],
                "uploaded_at": r[8].isoformat() if r[8] else None,
                "uploaded_by": r[9],
                "chunks": r[10] or 0,
                "is_structured": bool(r[11]),
            }
            for r in rows
        ]
    return [
        {
            "id": r[0], "name": r[1], "description": r[2],
            "version": None, "original_file_name": None, "file_url": None,
            "file_type": None, "file_size": None, "uploaded_at": None,
            "uploaded_by": None,
            "chunks": r[3] or 0,
            "is_structured": bool(r[4]),
        }
        for r in rows
    ]


@app.get("/api/entities/Policy")
def get_policies(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List policies with uploader email resolved via the upload audit-log entry."""
    from sqlalchemy import text as _t
    params = dict(request.query_params)
    limit = int(params.get("limit", 100))
    status_filter = params.get("status")

    is_admin = current_user.email == ADMIN_EMAIL
    where_parts = []
    if status_filter:
        where_parts.append("p.status = :st")
    if not is_admin:
        where_parts.append("p.owner_id = :uid")
    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    # Defensive: progress columns may not exist on older DBs — fall back gracefully.
    rich_sql = f"""
        SELECT p.id, p.file_name, p.description, p.department, p.version,
               p.status, p.file_url, p.file_type, p.content_preview,
               p.framework_code, p.uploaded_at, p.last_analyzed_at, p.created_at,
               u.email AS uploaded_by,
               COALESCE(p.progress, 0) AS progress,
               p.progress_stage,
               COALESCE(p.pause_requested, FALSE) AS pause_requested,
               p.paused_at
        FROM policies p
        LEFT JOIN LATERAL (
            SELECT actor_id
            FROM audit_logs
            WHERE action = 'upload_policy' AND target_id = p.id
            ORDER BY timestamp ASC
            LIMIT 1
        ) al ON TRUE
        LEFT JOIN users u ON u.id = al.actor_id
        {where}
        ORDER BY p.created_at DESC
        LIMIT :lim
    """
    basic_sql = f"""
        SELECT p.id, p.file_name, p.description, p.department, p.version,
               p.status, p.file_url, p.file_type, p.content_preview,
               p.framework_code, p.uploaded_at, p.last_analyzed_at, p.created_at,
               u.email AS uploaded_by
        FROM policies p
        LEFT JOIN LATERAL (
            SELECT actor_id
            FROM audit_logs
            WHERE action = 'upload_policy' AND target_id = p.id
            ORDER BY timestamp ASC
            LIMIT 1
        ) al ON TRUE
        LEFT JOIN users u ON u.id = al.actor_id
        {where}
        ORDER BY p.created_at DESC
        LIMIT :lim
    """

    params = {"lim": limit, "st": status_filter, "uid": str(current_user.id)}
    rich = True
    try:
        rows = db.execute(_t(rich_sql), params).fetchall()
    except Exception as e:
        print(f"[get_policies] rich query failed, falling back: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        rich = False
        rows = db.execute(_t(basic_sql), params).fetchall()

    return [
        {"id": r[0], "file_name": r[1], "description": r[2],
         "department": r[3], "version": r[4], "status": r[5],
         "file_url": r[6], "file_type": r[7], "content_preview": r[8],
         "framework_code": r[9],
         "uploaded_at": r[10].isoformat() if r[10] else None,
         "last_analyzed_at": r[11].isoformat() if r[11] else None,
         "created_at": r[12].isoformat() if r[12] else None,
         "uploaded_by": r[13],
         "progress": int(r[14]) if rich and r[14] is not None else (
             100 if r[5] == 'analyzed' else 0
         ),
         "progress_stage": (r[15] if rich else None) or None,
         "pause_requested": bool(r[16]) if rich else False,
         "paused_at": (r[17].isoformat() if rich and r[17] else None)}
        for r in rows
    ]


@app.get("/api/entities/AuditLog")
@app.get("/api/entities/audit_logs")
def get_audit_logs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Admin-only: regular users cannot read the audit trail."""
    from sqlalchemy import text as _t
    params = dict(request.query_params)
    limit = int(params.get("limit", 100))
    rows = db.execute(_t("""
        SELECT al.id, u.email AS actor, al.action, al.target_type,
               al.target_id, al.details::text AS details, al.timestamp
        FROM audit_logs al
        LEFT JOIN users u ON al.actor_id = u.id
        ORDER BY al.timestamp DESC
        LIMIT :lim
    """), {"lim": limit}).fetchall()
    return [
        {"id": r[0], "actor": r[1] or "system", "action": r[2],
         "target_type": r[3], "target_id": r[4], "details": r[5],
         "timestamp": r[6].isoformat() if r[6] else None}
        for r in rows
    ]


@app.get("/api/entities/ComplianceResult")
def get_compliance_results(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from sqlalchemy import text as _t
    params = dict(request.query_params)
    limit = int(params.get("limit", 100))
    policy_id = params.get("policy_id")
    is_admin = current_user.email == ADMIN_EMAIL
    where_parts = []
    if policy_id:
        where_parts.append("cr.policy_id = :pid")
    if not is_admin:
        where_parts.append("p.owner_id = :uid")
    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    rows = db.execute(_t(f"""
        SELECT cr.id, cr.policy_id, f.name AS framework,
               cr.compliance_score, cr.controls_covered,
               cr.controls_partial, cr.controls_missing,
               cr.status, cr.analyzed_at, cr.analysis_duration,
               cr.details::text AS details
        FROM compliance_results cr
        JOIN policies p ON p.id = cr.policy_id
        LEFT JOIN frameworks f ON cr.framework_id = f.id
        {where}
        ORDER BY cr.analyzed_at DESC
        LIMIT :lim
    """), {"lim": limit, "pid": policy_id, "uid": str(current_user.id)}).fetchall()
    return [
        {"id": r[0], "policy_id": r[1], "framework": r[2] or "Unknown",
         "compliance_score": r[3], "controls_covered": r[4],
         "controls_partial": r[5], "controls_missing": r[6],
         "status": r[7],
         "analyzed_at": r[8].isoformat() if r[8] else None,
         "analysis_duration": r[9], "details": r[10]}
        for r in rows
    ]


@app.get("/api/entities/Gap")
def get_gaps(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from sqlalchemy import text as _t
    params = dict(request.query_params)
    limit = int(params.get("limit", 100))
    policy_id = params.get("policy_id")
    status_filter = params.get("status")
    is_admin = current_user.email == ADMIN_EMAIL
    where_parts = []
    if policy_id:
        where_parts.append("g.policy_id = :pid")
    if status_filter:
        where_parts.append("g.status = :st")
    if not is_admin:
        where_parts.append("p.owner_id = :uid")
    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    rows = db.execute(_t(f"""
        SELECT g.id, g.policy_id, f.name AS framework,
               cl.control_code AS control_id, g.control_name,
               g.severity, g.status, g.description, g.remediation,
               g.created_at, g.owner_name, g.mapping_id
        FROM gaps g
        JOIN policies p ON p.id = g.policy_id
        LEFT JOIN frameworks f ON g.framework_id = f.id
        LEFT JOIN control_library cl ON g.control_id = cl.id
        {where}
        ORDER BY g.created_at DESC
        LIMIT :lim
    """), {"lim": limit, "pid": policy_id, "st": status_filter,
           "uid": str(current_user.id)}).fetchall()
    return [
        {"id": r[0], "policy_id": r[1], "framework": r[2] or "Unknown",
         "control_id": r[3] or "", "control_name": r[4],
         "severity": r[5], "status": r[6],
         "description": r[7], "remediation": r[8],
         "created_at": r[9].isoformat() if r[9] else None,
         "owner_name": r[10], "mapping_id": r[11]}
        for r in rows
    ]


@app.get("/api/entities/MappingReview")
def get_mapping_reviews(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from sqlalchemy import text as _t
    params = dict(request.query_params)
    limit = int(params.get("limit", 100))
    policy_id = params.get("policy_id")
    is_admin = current_user.email == ADMIN_EMAIL
    where_parts = []
    if policy_id:
        where_parts.append("mr.policy_id = :pid")
    if not is_admin:
        where_parts.append("p.owner_id = :uid")
    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    rows = db.execute(_t(f"""
        SELECT mr.id, mr.policy_id, f.name AS framework,
               cl.control_code AS control_id,
               mr.evidence_snippet, mr.confidence_score,
               mr.ai_rationale, mr.decision, mr.review_notes,
               mr.reviewed_at, mr.created_at
        FROM mapping_reviews mr
        JOIN policies p ON p.id = mr.policy_id
        LEFT JOIN frameworks f ON mr.framework_id = f.id
        LEFT JOIN control_library cl ON mr.control_id = cl.id
        {where}
        ORDER BY mr.created_at DESC
        LIMIT :lim
    """), {"lim": limit, "pid": policy_id, "uid": str(current_user.id)}).fetchall()
    return [
        {"id": r[0], "policy_id": r[1], "framework": r[2] or "Unknown",
         "control_id": r[3] or "", "evidence_snippet": r[4],
         "confidence_score": r[5], "ai_rationale": r[6],
         "decision": r[7], "review_notes": r[8],
         "reviewed_at": r[9].isoformat() if r[9] else None,
         "created_at": r[10].isoformat() if r[10] else None}
        for r in rows
    ]


# ━━━ Mapping Review Action Endpoints ━━━

def _clean_ai_rationale(text: str) -> str:
    """Strip confidence-level markers like [High] / [Medium] from AI rationale text."""
    import re
    cleaned = re.sub(r"\[(Critical|High|Medium|Low)\]", "", text or "", flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def _extract_severity(text: str) -> str:
    """Pull the severity level from AI rationale brackets, default Medium."""
    import re
    m = re.search(r"\[(Critical|High|Medium|Low)\]", text or "", re.IGNORECASE)
    return m.group(1).capitalize() if m else "Medium"


@app.post("/api/mappings/{mapping_id}/accept")
def accept_mapping(
    mapping_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from sqlalchemy import text as _t

    # Fetch the mapping with joined control and framework data
    row = db.execute(_t("""
        SELECT mr.id, mr.policy_id, mr.framework_id, mr.control_id,
               mr.ai_rationale, mr.evidence_snippet,
               cl.title AS control_title, cl.control_code,
               cl.severity_if_missing
        FROM mapping_reviews mr
        LEFT JOIN control_library cl ON mr.control_id = cl.id
        WHERE mr.id = :mid
    """), {"mid": mapping_id}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Mapping not found")

    (mr_id, policy_id, framework_id, control_id,
     ai_rationale, evidence_snippet,
     control_title, control_code, severity_if_missing) = row

    # Mark mapping accepted (idempotent: re-running with same mapping_id is fine).
    db.execute(_t("""
        UPDATE mapping_reviews
        SET decision = 'Accepted', reviewed_at = NOW(), reviewer_id = :uid
        WHERE id = :mid
    """), {"uid": str(current_user.id), "mid": mapping_id})

    # Phase 6 idempotency: INSERT...ON CONFLICT against the partial unique
    # index uq_gaps_mapping_id (gaps.mapping_id, WHERE mapping_id IS NOT NULL).
    # If the same mapping is accepted twice (double-click race, network retry,
    # multi-tab user, etc.), the second INSERT no-ops and rowcount returns 0.
    # The endpoint stays a 200 OK with gap_created=False on the second call.
    clean_rationale = _clean_ai_rationale(ai_rationale)
    severity = _extract_severity(ai_rationale) or severity_if_missing or "Medium"
    new_gap_id = str(__import__("uuid").uuid4())
    res = db.execute(_t("""
        INSERT INTO gaps
          (id, policy_id, framework_id, control_id, control_name,
           severity, status, description, remediation, mapping_id, created_at)
        VALUES
          (:id, :pid, :fid, :cid, :cname,
           :sev, 'Open', :desc, :rem, :mid, NOW())
        ON CONFLICT (mapping_id) WHERE mapping_id IS NOT NULL DO NOTHING
    """), {
        "id":    new_gap_id,
        "pid":   policy_id,
        "fid":   framework_id,
        "cid":   control_id,
        "cname": control_title or control_code or "Unknown Control",
        "sev":   severity,
        "desc":  clean_rationale or evidence_snippet or "",
        "rem":   clean_rationale or "",
        "mid":   mapping_id,
    })
    gap_created = (res.rowcount == 1)

    db.commit()
    return {"status": "accepted", "gap_created": gap_created}


@app.post("/api/mappings/{mapping_id}/reject")
def reject_mapping(
    mapping_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from sqlalchemy import text as _t

    review_notes = (payload.get("review_notes") or "").strip()
    if not review_notes:
        raise HTTPException(status_code=422, detail="Justification required to override AI")

    row = db.execute(_t("SELECT id FROM mapping_reviews WHERE id = :mid"),
                     {"mid": mapping_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Mapping not found")

    db.execute(_t("""
        UPDATE mapping_reviews
        SET decision = 'Compliant (Manual Override)',
            review_notes = :notes,
            reviewed_at  = NOW(),
            reviewer_id  = :uid
        WHERE id = :mid
    """), {"notes": review_notes, "uid": str(current_user.id), "mid": mapping_id})
    db.commit()
    return {"status": "rejected"}


# ━━━ Gap Update Endpoint ━━━

@app.put("/api/gaps/{gap_id}")
def update_gap(
    gap_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from sqlalchemy import text as _t

    row = db.execute(_t("SELECT id FROM gaps WHERE id = :gid"), {"gid": gap_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Gap not found")

    allowed = {"status", "owner_name", "remediation", "remediation_notes"}
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=422, detail="No valid fields to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["gid"] = gap_id
    db.execute(_t(f"UPDATE gaps SET {set_clause} WHERE id = :gid"), updates)
    db.commit()
    return {"status": "updated", "gap_id": gap_id}


# Generic Entity Routes
@app.get("/api/entities/{entity}")
def list_entities(entity: str, request: Request, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    model = ENTITY_MAP.get(entity)
    if not model:
        raise HTTPException(status_code=404, detail="Entity not found")

    params = dict(request.query_params)
    sort = params.pop("sort", None)
    limit = int(params.pop("limit", 100)) if params.get("limit") else 100

    q = db.query(model)
    for key, value in params.items():
        if hasattr(model, key):
            q = q.filter(getattr(model, key) == value)

    if sort and hasattr(model, sort.lstrip("-")):
        col = getattr(model, sort.lstrip("-"))
        q = q.order_by(col.desc() if sort.startswith("-") else col.asc())

    results = q.limit(limit).all()
    return serialize(results)


@app.get("/api/entities/{entity}/{item_id}")
def get_entity(entity: str, item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    model = ENTITY_MAP.get(entity)
    if not model:
        raise HTTPException(status_code=404, detail="Entity not found")
    item = db.query(model).filter(model.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return serialize(item)


ADMIN_ONLY_ENTITIES = {"Framework"}


@app.post("/api/entities/{entity}")
def create_or_update_entity(entity: str, payload: Dict[str, Any], db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    model = ENTITY_MAP.get(entity)
    if not model:
        raise HTTPException(status_code=404, detail="Entity not found")
    if entity in ADMIN_ONLY_ENTITIES and current_user.email != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")

    item_id = payload.get("id")
    if item_id:
        item = db.query(model).filter(model.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Not found")
        for key, value in payload.items():
            if hasattr(item, key) and key != "id":
                setattr(item, key, value)
        db.commit()
        db.refresh(item)
        return serialize(item)

    item = model(**payload)
    db.add(item)
    db.commit()
    db.refresh(item)
    return serialize(item)


@app.delete("/api/entities/Report/{item_id}")
def delete_report(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    report = db.query(models.Report).filter(models.Report.id == item_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Not found")

    # Remove the stored file, if it was persisted under /uploads/reports/
    if report.download_url and report.download_url.startswith("/uploads/reports/"):
        fname = report.download_url.rsplit("/", 1)[-1]
        try:
            file_path = REPORTS_DIR / fname
            if file_path.is_file():
                file_path.unlink()
        except Exception as _e:
            print(f"Report file cleanup warning: {_e}")

    db.delete(report)
    db.commit()

    try:
        from sqlalchemy import text as _audit_sql
        db.execute(_audit_sql("""
            INSERT INTO audit_logs (id, actor_id, action, target_type, target_id, details, timestamp)
            VALUES (:id, :aid, 'report_delete', 'report', :tid, :det, :ts)
        """), {
            "id": str(uuid.uuid4()),
            "aid": str(current_user.id) if hasattr(current_user, "id") else None,
            "tid": item_id,
            "det": json.dumps({"download_url": report.download_url}),
            "ts": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as _e:
        print(f"Audit log warning: {_e}")

    return {"ok": True}


@app.delete("/api/entities/Policy/{item_id}")
def delete_policy(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    policy = db.query(models.Policy).filter(models.Policy.id == item_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Not found")
    if current_user.email != ADMIN_EMAIL and str(policy.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorised")

    # Clean children that are not declared as cascade relationships on Policy.
    db.query(models.AIInsight).filter(models.AIInsight.policy_id == item_id).delete(synchronize_session=False)
    db.query(models.Report).filter(models.Report.policy_id == item_id).delete(synchronize_session=False)

    # Vector embeddings live in a raw table with an FK to policies.id.
    delete_policy_chunks(db, item_id)

    # cascade="all, delete-orphan" handles ComplianceResult, Gap, MappingReview.
    db.delete(policy)
    db.commit()

    try:
        from sqlalchemy import text as _audit_sql
        db.execute(_audit_sql("""
            INSERT INTO audit_logs (id, actor_id, action, target_type, target_id, details, timestamp)
            VALUES (:id, :aid, 'policy_delete', 'policy', :tid, :det, :ts)
        """), {
            "id": str(uuid.uuid4()),
            "aid": str(current_user.id) if hasattr(current_user, "id") else None,
            "tid": item_id,
            "det": json.dumps({"file_name": policy.file_name}),
            "ts": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as _e:
        print(f"Audit log warning: {_e}")

    return {"ok": True}


@app.delete("/api/entities/{entity}/{item_id}")
def delete_entity(entity: str, item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    model = ENTITY_MAP.get(entity)
    if not model:
        raise HTTPException(status_code=404, detail="Entity not found")
    if entity in ADMIN_ONLY_ENTITIES and current_user.email != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")
    item = db.query(model).filter(model.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


# Functions
@app.post("/api/functions/analyze_policy")
async def analyze_policy(request: schemas.AnalyzeRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    from sqlalchemy import text as _t

    policy = db.query(models.Policy).filter(models.Policy.id == request.policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if current_user.email != ADMIN_EMAIL and str(policy.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorised")

    # Phase 4b readiness gate. Refuse to analyze against any framework that
    # has controls without checkpoints — those produce silent "fake
    # compliance" findings. Returns HTTP 409 with the per-framework status
    # so the UI can render an actionable "framework needs to be re-uploaded
    # / repaired" warning.
    from backend.framework_loader import framework_readiness
    print(
        f"[analyze_policy] policy_id={request.policy_id} "
        f"frameworks={request.frameworks} "
        f"policy.status={policy.status!r} "
        f"progress={getattr(policy, 'progress', None)} "
        f"progress_stage={getattr(policy, 'progress_stage', None)!r} "
        f"last_analyzed_at={getattr(policy, 'last_analyzed_at', None)} "
        f"pause_requested={getattr(policy, 'pause_requested', None)}"
    )
    unready = []
    for fname in (request.frameworks or []):
        rd = framework_readiness(db, fname)
        print(
            f"[analyze_policy]   readiness({fname!r}): "
            f"is_ready={rd['is_ready']} structured={rd.get('structured')} "
            f"total={rd['total_controls']} zero_cp={rd['zero_cp_controls']} "
            f"reason={rd.get('reason')!r}"
        )
        if not rd["is_ready"]:
            unready.append({
                "framework": fname,
                "reason": rd["reason"],
                "total_controls": rd["total_controls"],
                "zero_checkpoint_controls": rd["zero_cp_controls"],
            })
    if unready:
        print(f"[analyze_policy] 409 — unready frameworks: {[u['framework'] for u in unready]}")
        raise HTTPException(status_code=409, detail={
            "error": "frameworks_not_ready",
            "message": ("One or more frameworks are incomplete (some controls "
                        "have no checkpoints). Re-upload the affected framework "
                        "with force=true to retry."),
            "unready_frameworks": unready,
        })

    resume = bool(getattr(request, "resume", False))

    # Reset pause flag — a new run (or a resume) is starting.
    db.execute(_t(
        "UPDATE policies SET status='processing', pause_requested=FALSE, "
        "paused_at = CASE WHEN :resume THEN paused_at ELSE NULL END "
        "WHERE id = :pid"
    ), {"resume": resume, "pid": policy.id})
    db.commit()
    set_policy_progress(db, policy.id, 5,
                        "Resuming analysis" if resume else "Preparing analysis")

    if not resume:
        # Fresh run — wipe previous analysis data so we don't leave stale rows.
        db.query(models.AIInsight).filter(models.AIInsight.policy_id == policy.id).delete()
        db.query(models.Gap).filter(models.Gap.policy_id == policy.id).delete()
        db.query(models.MappingReview).filter(models.MappingReview.policy_id == policy.id).delete()
        db.query(models.ComplianceResult).filter(models.ComplianceResult.policy_id == policy.id).delete()
        db.commit()
        set_policy_progress(db, policy.id, 10, "Cleared previous results")

    def _progress_cb(percent: int, stage: str):
        set_policy_progress(db, policy.id, percent, stage)

    try:
        all_results = {}

        # ── Structured analyzers (ECC-2:2024, SACS-002) ──────────────────
        frameworks_list = list(request.frameworks)
        if "ECC-2:2024" in frameworks_list:
            frameworks_list.remove("ECC-2:2024")
            ecc2_result = await run_ecc2_analysis(
                db, request.policy_id, progress_cb=_progress_cb
            )
            all_results.update(ecc2_result)

        if "SACS-002" in frameworks_list:
            frameworks_list.remove("SACS-002")
            sacs002_result = await run_sacs002_analysis(
                db, request.policy_id, progress_cb=_progress_cb
            )
            all_results.update(sacs002_result)

        # ── Other frameworks: use legacy checkpoint analyzer ───────────────
        if frameworks_list:
            legacy_result = await run_checkpoint_analysis(
                db, request.policy_id, frameworks_list,
                progress_cb=_progress_cb, resume=resume,
            )
            if isinstance(legacy_result, dict) and legacy_result.get("paused"):
                return {"success": True, "paused": True, "results": legacy_result.get("results", {})}
            all_results.update(legacy_result)

        # Mark the policy as fully analyzed — must happen BEFORE returning so
        # the frontend polling loop sees status='analyzed' on the next refetch.
        try:
            db.execute(_t("""
                UPDATE policies
                SET status='analyzed',
                    progress=100,
                    progress_stage='Completed',
                    last_analyzed_at=:ts
                WHERE id=:pid
            """), {"ts": datetime.now(timezone.utc), "pid": policy.id})
            db.commit()
        except Exception as _ue:
            db.rollback()
            print(f"[analyze_policy] WARNING: final status update failed: {_ue}")
    except Exception as e:
        _err_msg = f"Failed: {str(e)[:180]}"
        try:
            db.execute(
                _t("UPDATE policies SET status='failed', progress=0, "
                   "progress_stage=:msg, last_analyzed_at=:ts WHERE id=:pid"),
                {"msg": _err_msg, "ts": datetime.now(timezone.utc), "pid": policy.id},
            )
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    return {"success": True, "results": all_results}


@app.get("/api/ecc2/status")
def ecc2_status(db: Session = Depends(get_db)):
    """
    Verify that the ECC-2:2024 structured data is loaded and the analyzer
    is wired to the correct tables.

    Returns row counts for all three layers, orphan checks, a sample control
    lookup, and a go/no-go status field.
    """
    try:
        return verify_ecc2_loaded(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ECC-2 status check failed: {e}")


@app.get("/api/sacs002/status")
def sacs002_status(db: Session = Depends(get_db)):
    """
    Verify that the SACS-002 structured data is loaded and the analyzer
    is wired to the correct tables. Returns row counts for all three layers
    plus sacs002_metadata, orphan checks, and a go/no-go status field.
    """
    from sqlalchemy import text as _st
    result = {
        "framework_id": "SACS-002",
        "layer1_count": 0,
        "layer2_count": 0,
        "layer3_count": 0,
        "sacs002_metadata_count": 0,
        "joined_count": 0,
        "orphan_l3_count": 0,
        "missing_l2_count": 0,
        "errors": [],
        "status": "not_loaded",
    }
    try:
        result["layer1_count"] = db.execute(_st(
            "SELECT COUNT(*) FROM ecc_framework WHERE framework_id = 'SACS-002'"
        )).fetchone()[0]
    except Exception as e:
        result["errors"].append(f"ecc_framework: {e}")
    try:
        result["layer2_count"] = db.execute(_st(
            "SELECT COUNT(*) FROM ecc_compliance_metadata WHERE framework_id = 'SACS-002'"
        )).fetchone()[0]
    except Exception as e:
        result["errors"].append(f"ecc_compliance_metadata: {e}")
    try:
        result["layer3_count"] = db.execute(_st(
            "SELECT COUNT(*) FROM ecc_ai_checkpoints WHERE framework_id = 'SACS-002'"
        )).fetchone()[0]
    except Exception as e:
        result["errors"].append(f"ecc_ai_checkpoints: {e}")
    try:
        result["sacs002_metadata_count"] = db.execute(_st(
            "SELECT COUNT(*) FROM sacs002_metadata WHERE framework_id = 'SACS-002'"
        )).fetchone()[0]
    except Exception as e:
        # Table may not exist yet — created on next server restart
        result["errors"].append(f"sacs002_metadata (run server restart to create): {e}")
    try:
        result["joined_count"] = db.execute(_st("""
            SELECT COUNT(*) FROM ecc_framework f
            LEFT JOIN ecc_compliance_metadata m
                ON f.framework_id = m.framework_id AND f.control_code = m.control_code
            WHERE f.framework_id = 'SACS-002'
        """)).fetchone()[0]
    except Exception as e:
        result["errors"].append(f"joined_count: {e}")
    try:
        result["orphan_l3_count"] = db.execute(_st("""
            SELECT COUNT(*)
            FROM ecc_ai_checkpoints c
            LEFT JOIN ecc_framework f
                ON c.framework_id = f.framework_id AND c.control_code = f.control_code
            WHERE c.framework_id = 'SACS-002' AND f.control_code IS NULL
        """)).fetchone()[0]
    except Exception as e:
        result["errors"].append(f"orphan check: {e}")
    try:
        result["missing_l2_count"] = db.execute(_st("""
            SELECT COUNT(*)
            FROM ecc_framework f
            LEFT JOIN ecc_compliance_metadata m
                ON f.framework_id = m.framework_id AND f.control_code = m.control_code
            WHERE f.framework_id = 'SACS-002' AND m.control_code IS NULL
        """)).fetchone()[0]
    except Exception as e:
        result["errors"].append(f"missing_l2: {e}")
    if result["layer1_count"] >= 92 and result["layer3_count"] >= 92:
        result["status"] = "loaded"
    elif result["layer1_count"] > 0:
        result["status"] = "partial"
    else:
        result["status"] = "not_loaded"
    return result


@app.post("/api/functions/pause_policy")
def pause_policy(payload: Dict[str, Any], db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Cooperative pause: sets pause_requested=true on the policy row.

    The running analyzer polls this flag at safe checkpoints (after each
    framework finishes), commits its work, sets status='paused', and exits.
    Pause latency is bounded by per-framework duration; the
    verification_cache makes resume cheap.
    """
    from sqlalchemy import text as _t

    policy_id = payload.get("policy_id")
    if not policy_id:
        raise HTTPException(status_code=400, detail="policy_id is required")

    policy = db.query(models.Policy).filter(models.Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if current_user.email != ADMIN_EMAIL and str(policy.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorised")
    if policy.status != "processing":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot pause a policy in status '{policy.status}'.",
        )

    db.execute(_t(
        "UPDATE policies SET pause_requested = TRUE, "
        "progress_stage = 'Pause requested…' WHERE id = :pid"
    ), {"pid": policy_id})
    db.commit()

    try:
        db.execute(_t("""
            INSERT INTO audit_logs (id, actor_id, action, target_type, target_id, details, timestamp)
            VALUES (:id, :aid, 'analysis_pause', 'policy', :tid, :det, :ts)
        """), {
            "id": str(uuid.uuid4()),
            "aid": str(current_user.id) if hasattr(current_user, "id") else None,
            "tid": policy_id,
            "det": json.dumps({"file_name": policy.file_name}),
            "ts": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as _e:
        print(f"Audit log warning: {_e}")

    return {"ok": True, "pause_requested": True}


def _frameworks_for_policy(db, policy_id: str) -> list:
    """Return the framework names a policy should be analyzed against.

    Uses policies.framework_code when set; otherwise falls back to all
    frameworks that have a reference document loaded. Mirrors the
    frontend's doRunAnalysis logic so resume targets the same set.
    """
    from sqlalchemy import text as _t
    row = db.execute(_t(
        "SELECT framework_code FROM policies WHERE id = :pid"
    ), {"pid": policy_id}).fetchone()
    if row and row[0]:
        return [row[0]]
    rows = db.execute(_t(
        "SELECT DISTINCT f.name FROM framework_chunks fc "
        "JOIN frameworks f ON f.id = fc.framework_id"
    )).fetchall()
    return [r[0] for r in rows if r[0]]


async def _resume_analysis_in_background(policy_id: str, frameworks: list):
    """Fire-and-forget resume worker with its own DB session.

    Used by /api/functions/resume_policy so the user's HTTP request
    returns instantly and the polling UI shows live progress as the
    analyzer continues.
    """
    from sqlalchemy import text as _t
    db = database.SessionLocal()
    try:
        db.execute(_t(
            "UPDATE policies SET status='processing', pause_requested=FALSE "
            "WHERE id = :pid"
        ), {"pid": policy_id})
        db.commit()
        set_policy_progress(db, policy_id, 5, "Resuming analysis")

        def _cb(percent: int, stage: str):
            set_policy_progress(db, policy_id, percent, stage)

        result = await run_checkpoint_analysis(
            db, policy_id, frameworks, progress_cb=_cb, resume=True
        )
        if not (isinstance(result, dict) and result.get("paused")):
            try:
                db.execute(_t("""
                    UPDATE policies
                    SET status='analyzed',
                        progress=100,
                        progress_stage='Completed',
                        last_analyzed_at=:ts
                    WHERE id=:pid
                """), {"ts": datetime.now(timezone.utc), "pid": policy_id})
                db.commit()
            except Exception as _ue:
                db.rollback()
                print(f"[resume_analysis] WARNING: final status update failed: {_ue}")
    except Exception as e:
        _err_msg = f"Failed: {str(e)[:180]}"
        try:
            db.execute(_t(
                "UPDATE policies SET status='failed', progress=0, "
                "progress_stage=:msg, last_analyzed_at=:ts WHERE id=:pid"
            ), {"msg": _err_msg, "ts": datetime.now(timezone.utc), "pid": policy_id})
            db.commit()
        except Exception:
            db.rollback()
        print(f"[resume] background analysis failed: {e}")
    finally:
        db.close()


@app.post("/api/functions/resume_policy")
async def resume_policy(payload: Dict[str, Any], db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Resume a paused policy. Returns immediately; analysis runs in
    the background and progress is visible via the existing polling on
    GET /api/entities/Policy."""
    from sqlalchemy import text as _t
    import asyncio

    policy_id = payload.get("policy_id")
    if not policy_id:
        raise HTTPException(status_code=400, detail="policy_id is required")

    policy = db.query(models.Policy).filter(models.Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if current_user.email != ADMIN_EMAIL and str(policy.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorised")
    if policy.status != "paused":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot resume a policy in status '{policy.status}'.",
        )

    frameworks = _frameworks_for_policy(db, policy_id)
    if not frameworks:
        raise HTTPException(
            status_code=400,
            detail="No loaded framework available for this policy.",
        )

    db.execute(_t(
        "UPDATE policies SET status='processing', pause_requested=FALSE, "
        "progress_stage='Resuming…' WHERE id = :pid"
    ), {"pid": policy_id})
    db.commit()

    try:
        db.execute(_t("""
            INSERT INTO audit_logs (id, actor_id, action, target_type, target_id, details, timestamp)
            VALUES (:id, :aid, 'analysis_resume', 'policy', :tid, :det, :ts)
        """), {
            "id": str(uuid.uuid4()),
            "aid": str(current_user.id) if hasattr(current_user, "id") else None,
            "tid": policy_id,
            "det": json.dumps({"file_name": policy.file_name, "frameworks": frameworks}),
            "ts": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as _e:
        print(f"Audit log warning: {_e}")

    asyncio.create_task(_resume_analysis_in_background(policy_id, frameworks))
    return {"ok": True, "resumed": True, "frameworks": frameworks}


@app.post("/api/functions/run_simulation")
async def run_simulation_route(request: Dict[str, Any], db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    result = await run_simulation(
        db,
        request.get("policy_id"),
        request.get("selected_controls", request.get("control_ids", [])),
    )
    return result


@app.post("/api/functions/generate_report")
async def generate_report(request: schemas.GenerateReportRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    policy = db.query(models.Policy).filter(models.Policy.id == request.policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    download_url = f"/uploads/report_{request.policy_id}_{int(datetime.now(timezone.utc).timestamp())}.txt"
    report = models.Report(
        policy_id=policy.id,
        report_type=request.report_type,
        format=request.format,
        status="Completed",
        download_url=download_url,
        frameworks_included=request.frameworks_included,
        generated_at=datetime.now(timezone.utc),
    )
    db.add(report)

    from sqlalchemy import text as _audit_sql
    db.execute(_audit_sql("""
        INSERT INTO audit_logs (id, actor_id, action, target_type, target_id, details, timestamp)
        VALUES (:id, :aid, 'report_generate', 'report', :tid, :det, :ts)
    """), {
        "id": str(uuid.uuid4()),
        "aid": str(current_user.id) if hasattr(current_user, "id") else None,
        "tid": report.id,
        "det": json.dumps({"report_type": request.report_type, "format": request.format}),
        "ts": datetime.now(timezone.utc),
    })
    db.commit()
    db.refresh(report)

    return {"success": True, "report": serialize(report)}


@app.post("/api/functions/chat_assistant")
@app.post("/api/assistant/chat")
async def chat_assistant(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """User-scoped compliance Q&A.

    Always returns within ~50s — the helper is wrapped in asyncio.wait_for so
    a stalled embedding/LLM call surfaces as a clean 504 instead of leaving
    the client hanging. On any other failure we surface a friendly 503; raw
    stack traces never reach the client.
    """
    import asyncio as _asyncio

    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    if len(message) > 4000:
        raise HTTPException(
            status_code=400,
            detail="Message is too long (max 4000 characters).",
        )

    if not os.environ.get("OPENAI_API_KEY"):
        # Catch this before we burn a request on the LLM.
        raise HTTPException(
            status_code=503,
            detail=(
                "The assistant is not configured (missing API key). "
                "Please contact your administrator."
            ),
        )

    is_admin = current_user.email == ADMIN_EMAIL
    print(
        f"[/api/assistant/chat] user={current_user.email} admin={is_admin} "
        f"len={len(message)}",
        flush=True,
    )

    try:
        result = await _asyncio.wait_for(
            chat_with_user_context(db, message, current_user, is_admin=is_admin),
            timeout=50.0,
        )
    except _asyncio.TimeoutError:
        print("[/api/assistant/chat] TIMEOUT after 50s", flush=True)
        raise HTTPException(
            status_code=504,
            detail=(
                "The assistant took too long to respond. "
                "Please try a simpler question or try again."
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        print(
            f"[/api/assistant/chat] {type(exc).__name__}: {exc}",
            flush=True,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "The assistant is temporarily unavailable. "
                "Please try again in a moment."
            ),
        )

    return {
        "answer": result.get("answer") or "",
        "sources": result.get("sources") or [],
        "has_data": bool(result.get("has_data")),
        "has_policies": bool(result.get("has_policies")),
        "policies_in_scope": result.get("policies_in_scope") or 0,
        # Back-compat alias for any client still reading `response`.
        "response": result.get("answer") or "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/functions/db_health")
def db_health(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc).isoformat()
    return {"ok": True, "time": now}


# ━━━ Framework Document Management ━━━

@app.post("/api/functions/upload_framework_doc")
async def upload_framework_doc(
    file: UploadFile = File(...),
    framework: str = Form(...),
    description: str = Form(""),
    version: str = Form(""),
    force: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Upload a framework reference document.

    Admin-only. Persists the file under /uploads/frameworks/<timestamped>
    so re-uploads don't overwrite previous files, and writes the file
    metadata (name, version, file_url, uploaded_at, uploaded_by) onto the
    framework row so the framework is treated as a real database-backed
    uploaded document — not just a static name.

    If the same file (by SHA-256 hash) was already extracted for this
    framework name and force=False, returns the cached extraction result
    without re-running the pipeline. Pass force=True to delete the existing
    controls + checkpoints and re-extract from scratch.
    """
    import hashlib
    from sqlalchemy import text as _sql

    original_name = file.filename or "upload"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty framework document")
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Framework file exceeds 50 MB limit")

    file_hash = hashlib.sha256(raw).hexdigest()
    print(f"[fw-upload] {framework}: file={original_name} bytes={len(raw)} sha256={file_hash[:16]}... force={force}")

    # Cache check: if the framework already has this exact file_hash and the
    # caller didn't ask for re-extraction, return the cached row counts.
    if not force:
        try:
            cached = db.execute(_sql(
                "SELECT id, file_hash FROM frameworks WHERE name = :name"
            ), {"name": framework}).fetchone()
            if cached and cached[1] and cached[1] == file_hash:
                fid = cached[0]
                ctrl_count = db.execute(_sql(
                    "SELECT COUNT(*) FROM control_library WHERE framework_id = :fid"
                ), {"fid": fid}).fetchone()[0]
                cp_count = db.execute(_sql(
                    "SELECT COUNT(*) FROM control_checkpoints WHERE framework = :fid"
                ), {"fid": fid}).fetchone()[0]
                chunk_count = db.execute(_sql(
                    "SELECT COUNT(*) FROM framework_chunks WHERE framework_id = :fid"
                ), {"fid": fid}).fetchone()[0]
                print(f"[fw-upload] cache hit: skipping extraction "
                      f"(controls={ctrl_count}, checkpoints={cp_count})")
                return {
                    "framework": framework,
                    "source": original_name,
                    "status": "cached",
                    "from_cache": True,
                    "force_reprocess": False,
                    "file_hash": file_hash,
                    "chunks_created": chunk_count,
                    "controls_extracted": ctrl_count,
                    "checkpoints_generated": cp_count,
                    # file_hash is only ever stored on complete extractions, so
                    # a cache hit by definition means the cached run was complete.
                    "extraction_complete": True,
                    "failed_windows_count": 0,
                    "failed_windows": [],
                    "extraction_warnings": [],
                    "warning": None,
                }
        except Exception as _e:
            db.rollback()
            print(f"[fw-upload] cache check failed, proceeding with extraction: {_e}")

    fw_dir = UPLOAD_DIR / "frameworks"
    fw_dir.mkdir(exist_ok=True)
    stored_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{original_name}"
    file_path = fw_dir / stored_name
    file_path.write_bytes(raw)

    from backend.framework_loader import load_framework_document

    result = await load_framework_document(
        db, str(file_path), framework, original_name, force=force
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    result["from_cache"] = False
    result["force_reprocess"] = force
    result["file_hash"] = file_hash

    # Phase 4b readiness gate. Only persist file_hash AND only mark the
    # framework "ready" when BOTH conditions hold:
    #   1. Extraction (windows + checkpoint generation) reported complete
    #      (failed_windows + failed_checkpoint_batches both empty)
    #   2. Every control_library row has at least one matching
    #      control_checkpoints row (framework_readiness.is_ready)
    # Without (2), analysis would silently report "no findings" for any
    # zero-checkpoint control — the "fake compliance" failure the audit
    # identified.
    from backend.framework_loader import framework_readiness
    extraction_complete = bool(result.get("extraction_complete", True))
    rd = framework_readiness(db, framework)
    persist_hash = extraction_complete and rd["is_ready"]
    if extraction_complete and not rd["is_ready"]:
        print(f"[fw-upload] extraction reported complete BUT readiness gate "
              f"failed: {rd['reason']}; file_hash will NOT be persisted")
    elif not extraction_complete:
        print(f"[fw-upload] extraction incomplete "
              f"({result.get('failed_windows_count', 0)} window(s), "
              f"{result.get('failed_checkpoint_batches_count', 0)} batch(es) failed); "
              f"file_hash will NOT be persisted to frameworks row")
    new_status = (
        "ready" if persist_hash
        else ("incomplete" if extraction_complete else "failed")
    )
    result["readiness"] = rd
    result["extraction_status"] = new_status

    # Update framework row with the file metadata so the UI can show the
    # real uploaded document and the Replace flow works cleanly.
    try:
        db.execute(_sql("""
            UPDATE frameworks
               SET original_file_name = :ofn,
                   file_url    = :furl,
                   file_type   = :ft,
                   file_size   = :fs,
                   file_hash   = :fhash,
                   uploaded_at = :at,
                   uploaded_by = :uby,
                   version     = COALESCE(NULLIF(:ver, ''), version),
                   description = COALESCE(NULLIF(:desc, ''), description),
                   extraction_status = :ext_status
             WHERE name = :name
        """), {
            "ofn":  original_name,
            "furl": f"/uploads/frameworks/{stored_name}",
            "ft":   ext.replace(".", "").upper(),
            "fs":   len(raw),
            "fhash": file_hash if persist_hash else None,
            "at":   datetime.now(timezone.utc),
            "uby":  str(current_user.id) if hasattr(current_user, "id") else None,
            "ver":  (version or "").strip(),
            "desc": (description or "").strip(),
            "ext_status": new_status,
            "name": framework,
        })
        db.commit()
    except Exception as _e:
        print(f"Framework metadata update warning: {_e}")
        db.rollback()

    try:
        db.execute(_sql("""
            INSERT INTO audit_logs (id, actor_id, action, target_type, target_id, details, timestamp)
            VALUES (:id, :aid, 'framework_upload', 'framework', :tid, :det, :ts)
        """), {
            "id": str(uuid.uuid4()),
            "aid": str(current_user.id) if hasattr(current_user, "id") else None,
            "tid": framework,
            "det": json.dumps({"name": framework, "file": original_name, "version": version}),
            "ts": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as _e:
        print(f"Audit log warning: {_e}")

    return result


@app.get("/api/functions/framework_status")
def framework_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Check which frameworks have reference documents loaded.

    If ?framework=<name> is passed, the response is scoped to that single
    framework (used by the per-policy "Run Analysis" gate so the warning
    only appears when the policy's *actual* framework is missing).
    Without the param, returns the legacy three-framework summary.
    """
    from backend.framework_loader import get_framework_stats
    stats = get_framework_stats(db)

    target = (request.query_params.get("framework") or "").strip()

    if target:
        # Structured-table frameworks — check ecc_framework, not framework_chunks.
        if target in ("ECC-2:2024", "SACS-002"):
            from sqlalchemy import text as _t
            try:
                count = db.execute(_t(
                    "SELECT COUNT(*) FROM ecc_framework WHERE framework_id = :fwid"
                ), {"fwid": target}).scalar() or 0
            except Exception:
                count = 0
            loaded = count > 0
            return {
                "framework": target,
                "frameworks": {target: {"chunks": count, "documents": 1 if loaded else 0}},
                "ready": loaded,
                "loaded": loaded,
                "source": "structured_ecc_tables",
            }

        fw_stats = stats.get(target, {"chunks": 0, "documents": 0})
        loaded = fw_stats.get("chunks", 0) > 0
        return {
            "framework": target,
            "frameworks": {target: fw_stats},
            "ready": loaded,
            "loaded": loaded,
        }

    return {
        "frameworks": {
            "NCA ECC": stats.get("NCA ECC", {"chunks": 0, "documents": 0}),
            "ISO 27001": stats.get("ISO 27001", {"chunks": 0, "documents": 0}),
            "NIST 800-53": stats.get("NIST 800-53", {"chunks": 0, "documents": 0}),
        },
        "ready": all(
            stats.get(fw, {}).get("chunks", 0) > 0
            for fw in ["NCA ECC", "ISO 27001", "NIST 800-53"]
        ),
    }


@app.get("/api/functions/ai_insights/{policy_id}")
async def get_ai_insights(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Return AI insights for a policy. Powers the AI Insights page."""
    insights = (
        db.query(models.AIInsight)
        .filter(models.AIInsight.policy_id == policy_id)
        .order_by(models.AIInsight.created_at.desc())
        .all()
    )
    return serialize(insights)


REPORTS_DIR = UPLOAD_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


@app.post("/api/functions/save_report")
async def save_report(
    file: UploadFile = File(...),
    policy_id: str = Form(...),
    format: str = Form("PDF"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Persist a generated report file and create a Report DB row."""
    policy = db.query(models.Policy).filter(models.Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty report file")
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Report exceeds 50 MB limit")

    fmt = (format or "PDF").upper()
    ext = Path(file.filename or "").suffix.lower() or (".pdf" if fmt == "PDF" else ".csv")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    stored_name = f"{ts}_{uuid.uuid4().hex[:8]}{ext}"
    dest = REPORTS_DIR / stored_name
    dest.write_bytes(raw)

    report = models.Report(
        policy_id=policy.id,
        report_type="Compliance Report",
        format=fmt,
        status="Completed",
        download_url=f"/uploads/reports/{stored_name}",
        frameworks_included=[],
        generated_at=datetime.now(timezone.utc),
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    try:
        from sqlalchemy import text as _audit_sql
        db.execute(_audit_sql("""
            INSERT INTO audit_logs (id, actor_id, action, target_type, target_id, details, timestamp)
            VALUES (:id, :aid, 'report_generate', 'report', :tid, :det, :ts)
        """), {
            "id": str(uuid.uuid4()),
            "aid": str(current_user.id) if hasattr(current_user, "id") else None,
            "tid": report.id,
            "det": json.dumps({"policy_id": policy_id, "format": fmt, "file_name": file.filename}),
            "ts": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as _e:
        print(f"Audit log warning: {_e}")

    return serialize(report)


@app.get("/api/functions/policy_report_data/{policy_id}")
def policy_report_data(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Aggregate all available analysis data for a single policy, for report generation."""
    from sqlalchemy import text as _t

    policy = db.query(models.Policy).filter(models.Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    results = db.execute(_t("""
        SELECT cr.id, f.name AS framework, cr.compliance_score,
               cr.controls_covered, cr.controls_partial, cr.controls_missing,
               cr.status, cr.analyzed_at, cr.analysis_duration
        FROM compliance_results cr
        LEFT JOIN frameworks f ON cr.framework_id = f.id
        WHERE cr.policy_id = :pid
        ORDER BY cr.analyzed_at DESC
    """), {"pid": policy_id}).fetchall()

    gaps = db.execute(_t("""
        SELECT g.id, f.name AS framework, cl.control_code AS control_id,
               g.control_name, g.severity, g.status, g.description,
               g.remediation, g.created_at
        FROM gaps g
        LEFT JOIN frameworks f ON g.framework_id = f.id
        LEFT JOIN control_library cl ON g.control_id = cl.id
        WHERE g.policy_id = :pid
        ORDER BY
            CASE g.severity
                WHEN 'Critical' THEN 0 WHEN 'High' THEN 1
                WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 ELSE 4
            END,
            g.created_at DESC
    """), {"pid": policy_id}).fetchall()

    mappings = db.execute(_t("""
        SELECT mr.id, f.name AS framework, cl.control_code AS control_id,
               mr.evidence_snippet, mr.confidence_score,
               mr.ai_rationale, mr.decision, mr.reviewed_at
        FROM mapping_reviews mr
        LEFT JOIN frameworks f ON mr.framework_id = f.id
        LEFT JOIN control_library cl ON mr.control_id = cl.id
        WHERE mr.policy_id = :pid
        ORDER BY mr.confidence_score DESC NULLS LAST
    """), {"pid": policy_id}).fetchall()

    insights = (
        db.query(models.AIInsight)
        .filter(models.AIInsight.policy_id == policy_id)
        .order_by(models.AIInsight.created_at.desc())
        .all()
    )

    return {
        "policy": {
            "id": policy.id,
            "file_name": policy.file_name,
            "description": policy.description,
            "department": policy.department,
            "version": policy.version,
            "status": policy.status,
            "file_type": policy.file_type,
            "content_preview": policy.content_preview,
            "uploaded_at": policy.uploaded_at.isoformat() if policy.uploaded_at else None,
            "last_analyzed_at": policy.last_analyzed_at.isoformat() if policy.last_analyzed_at else None,
        },
        "compliance_results": [
            {"id": r[0], "framework": r[1] or "Unknown", "compliance_score": r[2] or 0,
             "controls_covered": r[3] or 0, "controls_partial": r[4] or 0,
             "controls_missing": r[5] or 0, "status": r[6],
             "analyzed_at": r[7].isoformat() if r[7] else None,
             "analysis_duration": r[8] or 0}
            for r in results
        ],
        "gaps": [
            {"id": r[0], "framework": r[1] or "Unknown", "control_id": r[2] or "",
             "control_name": r[3], "severity": r[4], "status": r[5],
             "description": r[6], "remediation": r[7],
             "created_at": r[8].isoformat() if r[8] else None}
            for r in gaps
        ],
        "mappings": [
            {"id": r[0], "framework": r[1] or "Unknown", "control_id": r[2] or "",
             "evidence_snippet": r[3], "confidence_score": r[4] or 0,
             "ai_rationale": r[5], "decision": r[6],
             "reviewed_at": r[7].isoformat() if r[7] else None}
            for r in mappings
        ],
        "insights": [
            {"id": i.id, "insight_type": i.insight_type, "title": i.title,
             "description": i.description, "priority": i.priority,
             "confidence": i.confidence, "status": i.status,
             "created_at": i.created_at.isoformat() if i.created_at else None}
            for i in insights
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/functions/explain_mapping")
async def explain_mapping_route(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Generate a detailed XAI explanation for a mapping decision. Powers the Explainability page."""
    mapping_id = payload.get("mapping_id", "")
    result = await explain_mapping(db, mapping_id)
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ADMIN ROUTES — restricted to himayaadmin@gmail.com
# ADMIN_EMAIL + require_admin are defined near the top of this file so any
# route can depend on them, including the framework-management endpoints.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@app.on_event("startup")
def seed_admin_user():
    """Ensure the admin account exists in the database on every startup."""
    db = database.SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.email == ADMIN_EMAIL).first()
        if not existing:
            hashed = auth.get_password_hash("09himaya09")
            admin = models.User(
                email=ADMIN_EMAIL,
                password_hash=hashed,
                first_name="Himaya",
                last_name="Admin",
                role="admin",
            )
            db.add(admin)
            db.commit()
            print(f"[startup] Admin user created: {ADMIN_EMAIL}")
    except Exception as e:
        db.rollback()
        print(f"[startup] Could not seed admin user: {e}")
    finally:
        db.close()


@app.on_event("startup")
def setup_framework_file_columns():
    """Idempotently add file-document columns to the frameworks table.

    Frameworks are stored as uploaded reference documents; older databases
    won't have the file metadata columns yet, so we ALTER on startup.
    """
    from sqlalchemy import text as _t
    statements = [
        "ALTER TABLE frameworks ADD COLUMN IF NOT EXISTS version TEXT",
        "ALTER TABLE frameworks ADD COLUMN IF NOT EXISTS original_file_name TEXT",
        "ALTER TABLE frameworks ADD COLUMN IF NOT EXISTS file_url TEXT",
        "ALTER TABLE frameworks ADD COLUMN IF NOT EXISTS file_type TEXT",
        "ALTER TABLE frameworks ADD COLUMN IF NOT EXISTS file_size INTEGER",
        "ALTER TABLE frameworks ADD COLUMN IF NOT EXISTS uploaded_at TIMESTAMPTZ",
        # Plain UUID column with NO inline FK reference. Adding the FK constraint
        # on a managed Postgres can fail (constraint name collision, permissions,
        # or users.id type mismatch). If that single statement fails, the column
        # never gets created and the list endpoint 500s — which is what broke
        # the Admin Frameworks page. The JOIN below works without a real FK.
        "ALTER TABLE frameworks ADD COLUMN IF NOT EXISTS uploaded_by UUID",
        "ALTER TABLE frameworks ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
        # SHA-256 of last successfully extracted file. Same hash + force=false
        # short-circuits the extraction pipeline (cache hit).
        "ALTER TABLE frameworks ADD COLUMN IF NOT EXISTS file_hash TEXT",
    ]
    db = database.SessionLocal()
    try:
        for sql in statements:
            try:
                db.execute(_t(sql))
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"[startup] Framework column migration warning: {sql} → {e}")
        print("[startup] Framework file columns ensured")
    finally:
        db.close()


@app.on_event("startup")
def setup_policy_owner_column():
    """Ensure policies.owner_id exists for user isolation."""
    from sqlalchemy import text as _t
    db = database.SessionLocal()
    try:
        db.execute(_t(
            "ALTER TABLE policies ADD COLUMN IF NOT EXISTS owner_id UUID "
            "REFERENCES users(id) ON DELETE SET NULL"
        ))
        db.commit()
        # Back-fill: policies already uploaded without an owner_id get the admin's id
        db.execute(_t("""
            UPDATE policies SET owner_id = (
                SELECT id FROM users WHERE email = :admin LIMIT 1
            ) WHERE owner_id IS NULL
        """), {"admin": ADMIN_EMAIL})
        db.commit()
        print("[startup] policies.owner_id ensured")
    except Exception as e:
        db.rollback()
        print(f"[startup] owner_id migration warning: {e}")
    finally:
        db.close()


@app.on_event("startup")
def setup_policy_progress_columns():
    """Idempotently add real-time progress columns to the policies table.

    The processing pipeline (upload → extraction → chunking → embedding →
    framework analysis) writes progress here so the Policies page shows
    "Processing • NN%" instead of a static spinner.
    """
    from sqlalchemy import text as _t
    statements = [
        "ALTER TABLE policies ADD COLUMN IF NOT EXISTS progress INTEGER DEFAULT 0",
        "ALTER TABLE policies ADD COLUMN IF NOT EXISTS progress_stage TEXT",
        # Cooperative pause flag + paused_at timestamp.
        "ALTER TABLE policies ADD COLUMN IF NOT EXISTS pause_requested BOOLEAN DEFAULT FALSE",
        "ALTER TABLE policies ADD COLUMN IF NOT EXISTS paused_at TIMESTAMPTZ",
    ]
    db = database.SessionLocal()
    try:
        for sql in statements:
            try:
                db.execute(_t(sql))
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"[startup] Policy progress column migration warning: {sql} → {e}")
        print("[startup] Policy progress columns ensured")
    finally:
        db.close()


def ensure_pgvector_columns(db):
    """Ensure pgvector-related columns exist. Idempotent.

    Previously ALTERed on every upload from store_chunks_with_embeddings;
    now runs once at startup.
    """
    from sqlalchemy import text as _t
    statements = [
        "ALTER TABLE policy_chunks ADD COLUMN IF NOT EXISTS classification VARCHAR DEFAULT 'descriptive'",
        # Phase 11: source attribution. Five additive nullable columns.
        # PDF chunks populate page_number; DOCX chunks populate paragraph_index;
        # TXT/XLSX leave both NULL. Existing rows stay NULL until a manual
        # re-analysis triggers _rechunk_for_source_attribution.
        "ALTER TABLE policy_chunks ADD COLUMN IF NOT EXISTS page_number INT NULL",
        "ALTER TABLE policy_chunks ADD COLUMN IF NOT EXISTS paragraph_index INT NULL",
        "ALTER TABLE policy_ecc_assessments ADD COLUMN IF NOT EXISTS chunk_id VARCHAR NULL",
        "ALTER TABLE policy_ecc_assessments ADD COLUMN IF NOT EXISTS page_number INT NULL",
        "ALTER TABLE policy_ecc_assessments ADD COLUMN IF NOT EXISTS paragraph_index INT NULL",
    ]
    for stmt in statements:
        try:
            db.execute(_t(stmt))
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"  [startup] {stmt[:50]}... -> {e}")


@app.on_event("startup")
def setup_pgvector_columns():
    """Run idempotent ALTER TABLE for runtime-managed pgvector/policy_chunks columns."""
    db = database.SessionLocal()
    try:
        ensure_pgvector_columns(db)
        print("[startup] pgvector columns ensured")
    finally:
        db.close()


@app.on_event("startup")
def setup_system_settings():
    """Create system_settings table, seed defaults, and add lockout columns to users."""
    from sqlalchemy import text as _t
    db = database.SessionLocal()
    try:
        # system_settings table
        db.execute(_t("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # Default settings — only insert if the key doesn't already exist
        defaults = {
            "session_timeout_minutes":   "60",
            "max_login_attempts":        "5",
            "lockout_duration_minutes":  "15",
            "llm_model":                 "gpt-4o-mini",
            "top_k_retrieval":           "10",
            "notify_analysis_complete":  "true",
            "notify_failed_analysis":    "true",
            "notify_weekly_report":      "false",
            "notify_new_user":           "true",
        }
        for key, value in defaults.items():
            db.execute(_t("""
                INSERT INTO system_settings (key, value)
                VALUES (:k, :v)
                ON CONFLICT (key) DO NOTHING
            """), {"k": key, "v": value})

        # Add lockout columns to users only if they don't exist yet.
        # Using information_schema avoids a DDL ALTER TABLE on every startup,
        # which causes a statement-timeout on Supabase's connection pooler.
        existing_cols = {
            row[0]
            for row in db.execute(_t("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users'
                  AND column_name IN ('failed_login_attempts', 'locked_until')
            """)).fetchall()
        }
        if "failed_login_attempts" not in existing_cols:
            db.execute(_t("""
                ALTER TABLE users
                ADD COLUMN failed_login_attempts INTEGER DEFAULT 0
            """))
        if "locked_until" not in existing_cols:
            db.execute(_t("""
                ALTER TABLE users
                ADD COLUMN locked_until TIMESTAMPTZ DEFAULT NULL
            """))

        db.commit()
        print("[startup] system_settings ready.")
    except Exception as e:
        db.rollback()
        print(f"[startup] setup_system_settings warning: {e}")
    finally:
        db.close()


ALLOWED_SETTINGS_KEYS = {
    "session_timeout_minutes",
    "max_login_attempts",
    "lockout_duration_minutes",
    "llm_model",
    "top_k_retrieval",
    "notify_analysis_complete",
    "notify_failed_analysis",
    "notify_weekly_report",
    "notify_new_user",
}


@app.get("/api/admin/settings")
def get_admin_settings(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Return all system settings as a key→value dict."""
    from sqlalchemy import text as _t
    rows = db.execute(_t("SELECT key, value FROM system_settings")).fetchall()
    return {r[0]: r[1] for r in rows}


@app.patch("/api/admin/settings")
def update_admin_settings(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Update one or more system settings. Only known keys are accepted."""
    from sqlalchemy import text as _t
    unknown = set(payload.keys()) - ALLOWED_SETTINGS_KEYS
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown setting keys: {unknown}")
    for key, value in payload.items():
        db.execute(_t("""
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (:k, :v, NOW())
            ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = NOW()
        """), {"k": key, "v": str(value)})
    db.commit()
    rows = db.execute(_t("SELECT key, value FROM system_settings")).fetchall()
    return {r[0]: r[1] for r in rows}


@app.patch("/api/auth/profile")
def update_profile(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Update first_name / last_name of the currently authenticated user."""
    allowed = {"first_name", "last_name"}
    for field in allowed:
        if field in payload:
            setattr(current_user, field, payload[field])
    db.commit()
    db.refresh(current_user)
    return {"first_name": current_user.first_name, "last_name": current_user.last_name}


@app.get("/api/admin/stats")
def admin_stats(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Dashboard summary statistics."""
    total_users = db.query(models.User).count()
    uploaded_policies = db.query(models.Policy).count()
    completed = db.query(models.Policy).filter(models.Policy.status == "analyzed").count()
    pending = db.query(models.Policy).filter(models.Policy.status.in_(["uploaded", "processing"])).count()
    failed = db.query(models.Policy).filter(models.Policy.status == "failed").count()

    scores = db.query(models.ComplianceResult.compliance_score).all()
    avg_score = round(sum(s[0] for s in scores if s[0]) / len(scores), 1) if scores else 0.0

    return {
        "totalUsers": total_users,
        "uploadedPolicies": uploaded_policies,
        "completedAnalyses": completed,
        "pendingAnalyses": pending,
        "failedAnalyses": failed,
        "avgComplianceScore": avg_score,
    }


@app.get("/api/admin/users")
def admin_list_users(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Return all registered users."""
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    return [
        {
            "id": str(u.id),
            "first_name": u.first_name,
            "last_name": u.last_name,
            "email": u.email,
            "role": u.role or "Regular User",
            "is_active": u.role != "disabled",
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@app.patch("/api/admin/users/{user_id}/role")
def admin_update_user_role(
    user_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Change a user's role."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = payload.get("role", user.role)
    db.commit()
    return {"ok": True, "role": user.role}


@app.patch("/api/admin/users/{user_id}/status")
def admin_update_user_status(
    user_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Activate or deactivate a user account (stored as role='disabled')."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    is_active = payload.get("is_active", True)
    if not is_active:
        user.role = "disabled"
    else:
        # Restore to Regular User if previously disabled
        if user.role == "disabled":
            user.role = "Regular User"
    db.commit()
    return {"ok": True, "is_active": user.role != "disabled"}


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """Permanently delete a user account."""
    if str(admin.id) == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"ok": True}


@app.get("/api/admin/policies")
def admin_list_policies(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Return all uploaded policies with uploader name and most recent framework."""
    from sqlalchemy import text as _t
    try:
        rows = db.execute(_t("""
            SELECT
                p.id,
                p.file_name,
                p.department,
                p.status,
                p.created_at,
                COALESCE(
                    NULLIF(TRIM(u.first_name || ' ' || COALESCE(u.last_name, '')), ''),
                    u.email
                ) AS uploaded_by,
                (
                    SELECT f.name
                    FROM compliance_results cr
                    JOIN frameworks f ON f.id = cr.framework_id
                    WHERE cr.policy_id = p.id
                    ORDER BY cr.analyzed_at DESC
                    LIMIT 1
                ) AS framework
            FROM policies p
            LEFT JOIN LATERAL (
                SELECT actor_id
                FROM audit_logs
                WHERE action = 'upload_policy' AND target_id = p.id
                ORDER BY timestamp ASC
                LIMIT 1
            ) al ON TRUE
            LEFT JOIN users u ON u.id = al.actor_id
            ORDER BY p.created_at DESC
        """)).fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return [
        {
            "id": str(r[0]),
            "file_name": r[1],
            "department": r[2],
            "status": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
            "uploaded_by": r[5],
            "framework": r[6],
        }
        for r in rows
    ]


@app.delete("/api/admin/policies/{policy_id}")
def admin_delete_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Delete a policy and all its analysis data (cascaded by DB)."""
    policy = db.query(models.Policy).filter(models.Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    db.delete(policy)
    db.commit()
    return {"ok": True}


@app.post("/api/admin/policies/{policy_id}/reset_status")
def admin_reset_policy_status(
    policy_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """
    Reset a policy that is stuck in 'processing' back to 'uploaded'.

    Safe to call when:
    - A previous analysis job crashed without writing status='failed'
    - The server was restarted mid-analysis
    - pause_requested was never cleared

    Returns the old and new status so the caller can confirm the change.
    """
    from sqlalchemy import text as _t
    row = db.execute(_t(
        "SELECT status, progress, progress_stage, pause_requested "
        "FROM policies WHERE id = :pid"
    ), {"pid": policy_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")

    old_status, old_progress, old_stage, old_pause = row
    db.execute(_t("""
        UPDATE policies
        SET status          = 'uploaded',
            progress        = 0,
            progress_stage  = 'Reset by admin',
            pause_requested = FALSE,
            paused_at       = NULL
        WHERE id = :pid
    """), {"pid": policy_id})
    db.commit()
    print(
        f"[admin_reset] policy_id={policy_id} "
        f"was status={old_status!r} progress={old_progress} "
        f"stage={old_stage!r} pause_requested={old_pause} → reset to 'uploaded'"
    )
    return {
        "ok": True,
        "policy_id": policy_id,
        "previous": {"status": old_status, "progress": old_progress,
                     "progress_stage": old_stage, "pause_requested": old_pause},
        "now": {"status": "uploaded", "progress": 0},
    }


@app.post("/api/admin/policies/{policy_id}/reanalyze")
async def admin_reanalyze_policy(
    policy_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Trigger a fresh analysis for a policy."""
    policy = db.query(models.Policy).filter(models.Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    frameworks = payload.get("frameworks", ["NCA ECC", "ISO 27001", "NIST 800-53"])

    # Clear previous results
    db.query(models.Gap).filter(models.Gap.policy_id == policy_id).delete()
    db.query(models.MappingReview).filter(models.MappingReview.policy_id == policy_id).delete()
    db.query(models.ComplianceResult).filter(models.ComplianceResult.policy_id == policy_id).delete()
    db.commit()

    policy.status = "processing"
    db.commit()

    from backend.rag_engine import run_full_analysis
    results = await run_full_analysis(db, policy_id, frameworks)
    return {"ok": True, "results": results}


@app.get("/api/admin/frameworks")
def admin_list_frameworks(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Return all frameworks (incl. file metadata) with control + checkpoint counts.

    Defensive: if any of the file-document columns are missing in this
    deployment (because the startup migration failed), fall back to the
    basic columns so the page still loads instead of 500-ing.
    """
    from sqlalchemy import text as _t

    rich_sql = """
        SELECT
            f.id, f.name, f.description, f.version,
            f.original_file_name, f.file_url, f.file_type, f.file_size,
            f.uploaded_at, u.email AS uploaded_by_email,
            COALESCE(ctrl.controls, 0)        AS controls,
            COALESCE(chunks.chunks, 0)        AS chunks
        FROM frameworks f
        LEFT JOIN users u ON u.id = f.uploaded_by
        LEFT JOIN (
            SELECT framework_id, COUNT(*) AS controls
            FROM control_library GROUP BY framework_id
        ) ctrl ON ctrl.framework_id = f.id
        LEFT JOIN (
            SELECT framework_id, COUNT(*) AS chunks
            FROM framework_chunks GROUP BY framework_id
        ) chunks ON chunks.framework_id = f.id
        ORDER BY f.name ASC
    """

    basic_sql = """
        SELECT
            f.id, f.name, f.description,
            COALESCE(ctrl.controls, 0) AS controls,
            COALESCE(chunks.chunks, 0) AS chunks
        FROM frameworks f
        LEFT JOIN (
            SELECT framework_id, COUNT(*) AS controls
            FROM control_library GROUP BY framework_id
        ) ctrl ON ctrl.framework_id = f.id
        LEFT JOIN (
            SELECT framework_id, COUNT(*) AS chunks
            FROM framework_chunks GROUP BY framework_id
        ) chunks ON chunks.framework_id = f.id
        ORDER BY f.name ASC
    """

    rich = True
    try:
        rows = db.execute(_t(rich_sql)).fetchall()
    except Exception as e:
        # File columns missing or any other column-related failure — fall back.
        print(f"[admin_list_frameworks] rich query failed, falling back: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        rich = False
        try:
            rows = db.execute(_t(basic_sql)).fetchall()
        except Exception as e2:
            try:
                db.rollback()
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=f"Could not load frameworks: {e2}")

    result = []
    for r in rows:
        try:
            chk_row = db.execute(
                _t("SELECT COUNT(*) FROM control_checkpoints WHERE framework = :fwid"),
                {"fwid": r[0]},
            ).fetchone()
            checkpoint_count = chk_row[0] if chk_row else 0
        except Exception:
            checkpoint_count = 0
            try:
                db.rollback()
            except Exception:
                pass

        if rich:
            result.append({
                "id": r[0],
                "name": r[1],
                "description": r[2],
                "version": r[3],
                "original_file_name": r[4],
                "file_url": r[5],
                "file_type": r[6],
                "file_size": r[7],
                "uploaded_at": r[8].isoformat() if r[8] else None,
                "uploaded_by": r[9],
                "controls": r[10],
                "chunks": r[11],
                "checkpoints": checkpoint_count,
            })
        else:
            result.append({
                "id": r[0],
                "name": r[1],
                "description": r[2],
                "version": None,
                "original_file_name": None,
                "file_url": None,
                "file_type": None,
                "file_size": None,
                "uploaded_at": None,
                "uploaded_by": None,
                "controls": r[3],
                "chunks": r[4],
                "checkpoints": checkpoint_count,
            })
    return result


@app.get("/api/admin/frameworks/{framework_id}")
def admin_get_framework(
    framework_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Return framework details with controls and their checkpoints."""
    from sqlalchemy import text as _t
    fw = db.query(models.Framework).filter(models.Framework.id == framework_id).first()
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found")

    controls = (
        db.query(models.ControlLibrary)
        .filter(models.ControlLibrary.framework_id == framework_id)
        .order_by(models.ControlLibrary.control_code)
        .all()
    )

    controls_with_checkpoints = []
    for ctrl in controls:
        try:
            chk_rows = db.execute(
                _t("""
                    SELECT id, checkpoint_index, requirement, keywords, weight
                    FROM control_checkpoints
                    WHERE framework = :fwid AND control_code = :code
                    ORDER BY checkpoint_index
                """),
                {"fwid": framework_id, "code": ctrl.control_code},
            ).fetchall()
            checkpoints = [
                {"id": c[0], "index": c[1], "requirement": c[2], "keywords": c[3], "weight": c[4]}
                for c in chk_rows
            ]
        except Exception:
            checkpoints = []
        controls_with_checkpoints.append({
            "id": ctrl.id,
            "control_code": ctrl.control_code,
            "title": ctrl.title,
            "keywords": ctrl.keywords,
            "severity_if_missing": ctrl.severity_if_missing,
            "checkpoints": checkpoints,
        })

    return {
        "id": fw.id,
        "name": fw.name,
        "description": fw.description,
        "controls": controls_with_checkpoints,
    }


@app.post("/api/admin/frameworks")
def admin_create_framework(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Create a new framework. Name is required and must be unique."""
    name = (payload.get("name") or "").strip()
    description = (payload.get("description") or "").strip() or None
    if not name:
        raise HTTPException(status_code=400, detail="Framework name is required")
    existing = db.query(models.Framework).filter(models.Framework.name == name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A framework named '{name}' already exists")
    fw = models.Framework(name=name, description=description)
    db.add(fw)
    db.commit()
    db.refresh(fw)
    return {"id": fw.id, "name": fw.name, "description": fw.description, "controls": 0, "checkpoints": 0}


@app.patch("/api/admin/frameworks/{framework_id}")
def admin_update_framework(
    framework_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Update framework metadata (name and/or description)."""
    fw = db.query(models.Framework).filter(models.Framework.id == framework_id).first()
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found")

    new_name = payload.get("name")
    if new_name is not None:
        new_name = new_name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Framework name cannot be empty")
        if new_name != fw.name:
            clash = (
                db.query(models.Framework)
                .filter(models.Framework.name == new_name, models.Framework.id != framework_id)
                .first()
            )
            if clash:
                raise HTTPException(status_code=409, detail=f"A framework named '{new_name}' already exists")
            # Keep policies that reference this framework by name in sync.
            from sqlalchemy import text as _t
            db.execute(
                _t("UPDATE policies SET framework_code = :new WHERE framework_code = :old"),
                {"new": new_name, "old": fw.name},
            )
            fw.name = new_name

    if "description" in payload:
        desc = payload.get("description")
        fw.description = (desc or "").strip() or None

    db.commit()
    db.refresh(fw)
    return {"id": fw.id, "name": fw.name, "description": fw.description}


@app.delete("/api/admin/frameworks/{framework_id}")
def admin_delete_framework(
    framework_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Delete a framework and its dependent corpus.

    Refuses if any policy is still linked to this framework via
    framework_code, so we never orphan analysis data.
    """
    from sqlalchemy import text as _t

    fw = db.query(models.Framework).filter(models.Framework.id == framework_id).first()
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found")

    policy_count = db.execute(
        _t("SELECT COUNT(*) FROM policies WHERE framework_code = :name"),
        {"name": fw.name},
    ).fetchone()[0]
    if policy_count and policy_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete '{fw.name}': {policy_count} policy/policies are still linked to "
                "this framework. Reassign or remove those policies first."
            ),
        )

    # Cascade dependent rows that don't have ON DELETE CASCADE in the schema.
    try:
        db.execute(_t("DELETE FROM control_checkpoints WHERE framework = :fwid"), {"fwid": framework_id})
        db.execute(_t("DELETE FROM framework_chunks WHERE framework_id = :fwid"), {"fwid": framework_id})
        db.execute(_t("DELETE FROM control_library WHERE framework_id = :fwid"), {"fwid": framework_id})
        # Also clear analysis rows that reference the framework so deletion succeeds.
        db.execute(_t("DELETE FROM mapping_reviews WHERE framework_id = :fwid"), {"fwid": framework_id})
        db.execute(_t("DELETE FROM gaps WHERE framework_id = :fwid"), {"fwid": framework_id})
        db.execute(_t("DELETE FROM compliance_results WHERE framework_id = :fwid"), {"fwid": framework_id})
    except Exception as _e:
        # If a table doesn't exist in this deployment, fall through; the
        # framework delete itself will still succeed if the FK isn't enforced.
        print(f"Framework dependency cleanup warning: {_e}")
        db.rollback()

    db.delete(fw)
    db.commit()

    try:
        db.execute(_t("""
            INSERT INTO audit_logs (id, actor_id, action, target_type, target_id, details, timestamp)
            VALUES (:id, :aid, 'framework_delete', 'framework', :tid, :det, :ts)
        """), {
            "id": str(uuid.uuid4()),
            "aid": None,
            "tid": framework_id,
            "det": json.dumps({"name": fw.name}),
            "ts": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as _e:
        print(f"Audit log warning: {_e}")

    return {"ok": True}


@app.post("/api/admin/frameworks/{framework_id}/controls")
def admin_add_control(
    framework_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Add a new control to a framework."""
    fw = db.query(models.Framework).filter(models.Framework.id == framework_id).first()
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found")
    ctrl = models.ControlLibrary(
        framework_id=framework_id,
        control_code=payload.get("control_code", ""),
        title=payload.get("title", ""),
        keywords=payload.get("keywords", []),
        severity_if_missing=payload.get("severity_if_missing", "Medium"),
    )
    db.add(ctrl)
    db.commit()
    db.refresh(ctrl)
    return {"id": ctrl.id, "control_code": ctrl.control_code, "title": ctrl.title}


@app.get("/api/admin/analysis-results")
def admin_analysis_results(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Return compliance results with policy name, framework name, and uploader."""
    from sqlalchemy import text as _t
    try:
        rows = db.execute(_t("""
            SELECT
                cr.id,
                cr.policy_id,
                p.file_name,
                f.name AS framework_name,
                cr.compliance_score,
                cr.controls_covered,
                cr.controls_partial,
                cr.controls_missing,
                cr.status,
                cr.analyzed_at,
                COALESCE(
                    NULLIF(TRIM(u.first_name || ' ' || COALESCE(u.last_name, '')), ''),
                    u.email
                ) AS uploaded_by
            FROM compliance_results cr
            JOIN policies p ON p.id = cr.policy_id
            LEFT JOIN frameworks f ON f.id = cr.framework_id
            LEFT JOIN LATERAL (
                SELECT actor_id
                FROM audit_logs
                WHERE action = 'upload_policy' AND target_id = p.id
                ORDER BY timestamp ASC
                LIMIT 1
            ) al ON TRUE
            LEFT JOIN users u ON u.id = al.actor_id
            ORDER BY cr.analyzed_at DESC
            LIMIT 200
        """)).fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return [
        {
            "id": r[0],
            "policy_id": r[1],
            "policy_name": r[2],
            "framework": r[3],
            "compliance_score": r[4],
            "controls_covered": r[5],
            "controls_partial": r[6],
            "controls_missing": r[7],
            "status": r[8],
            "analyzed_at": r[9].isoformat() if r[9] else None,
            "uploaded_by": r[10],
        }
        for r in rows
    ]


@app.delete("/api/admin/analysis-results/{result_id}")
def admin_delete_analysis_result(
    result_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Delete a single compliance result row."""
    item = db.query(models.ComplianceResult).filter(models.ComplianceResult.id == result_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Analysis result not found")

    policy_id = item.policy_id
    db.delete(item)
    db.commit()

    try:
        from sqlalchemy import text as _audit_sql
        db.execute(_audit_sql("""
            INSERT INTO audit_logs (id, actor_id, action, target_type, target_id, details, timestamp)
            VALUES (:id, :aid, 'analysis_delete', 'compliance_result', :tid, :det, :ts)
        """), {
            "id": str(uuid.uuid4()),
            "aid": str(current_user.id) if hasattr(current_user, "id") else None,
            "tid": result_id,
            "det": json.dumps({"policy_id": policy_id}),
            "ts": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as _e:
        print(f"Audit log warning: {_e}")

    return {"ok": True}


@app.get("/api/admin/activity-logs")
def admin_activity_logs(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Return recent audit log entries with resolved actor name."""
    from sqlalchemy import text as _t
    try:
        rows = db.execute(_t("""
            SELECT
                al.id,
                al.action,
                al.target_type,
                al.target_id,
                al.details::text,
                al.timestamp,
                COALESCE(
                    NULLIF(TRIM(u.first_name || ' ' || COALESCE(u.last_name, '')), ''),
                    u.email
                ) AS actor_name
            FROM audit_logs al
            LEFT JOIN users u ON u.id = al.actor_id
            ORDER BY al.timestamp DESC
            LIMIT 200
        """)).fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return [
        {
            "id": r[0],
            "action": r[1],
            "target_type": r[2],
            "target_id": r[3],
            "details": r[4],
            "timestamp": r[5].isoformat() if r[5] else None,
            "actor_name": r[6],
        }
        for r in rows
    ]

