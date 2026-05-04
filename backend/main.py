import json
import os
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
from backend.database import get_db
from backend.email_utils import (
    send_otp_email,
    send_password_reset_email,
    EmailDeliveryError,
)
from backend.text_extractor import extract_text
from backend.checkpoint_analyzer import (
    run_checkpoint_analysis, chat_with_context,
    run_simulation, generate_insights, explain_mapping,
)
from backend.vector_store import get_embeddings, store_chunks_with_embeddings, delete_policy_chunks
from backend.chunker import chunk_text


app = FastAPI()


@app.on_event("startup")
def startup_seed():
    """Seed checkpoint data on server start."""
    from backend.checkpoint_seed import seed_checkpoints
    db = database.SessionLocal()
    try:
        seed_checkpoints(db)
    except Exception as e:
        print(f"Seed warning: {e}")
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

    # Extract text
    set_policy_progress(db, policy_id, 15, "Extracting text")
    try:
        content = extract_text(str(dest), ext)
    except TypeError:
        content = extract_text(str(dest))
    if not content or content.startswith("[Extraction error"):
        content = ""
    set_policy_progress(db, policy_id, 30, "Text extracted")

    # Save full content for keyword search during analysis
    if content:
        db.execute(_sql(
            "UPDATE policies SET content_preview = :content WHERE id = :pid"
        ), {"content": content, "pid": policy_id})
        db.commit()

    # Chunk and embed the full text
    chunks_count = 0
    if content:
        try:
            set_policy_progress(db, policy_id, 45, "Chunking document")
            chunks = chunk_text(content)
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
):
    from sqlalchemy import text as _t

    # Latest compliance result per framework
    rows = db.execute(_t("""
        SELECT DISTINCT ON (f.name)
               f.name, cr.compliance_score,
               cr.controls_covered, cr.controls_partial, cr.controls_missing
        FROM compliance_results cr
        LEFT JOIN frameworks f ON cr.framework_id = f.id
        ORDER BY f.name, cr.analyzed_at DESC
    """)).fetchall()

    framework_scores = [
        {"framework": r[0] or "Unknown", "score": round(r[1] or 0, 1),
         "covered": r[2] or 0, "partial": r[3] or 0, "missing": r[4] or 0}
        for r in rows
    ]
    security_score = (
        round(sum(r[1] or 0 for r in rows) / len(rows), 1) if rows else 0
    )

    # Open gaps
    open_gaps = db.execute(_t(
        "SELECT COUNT(*) FROM gaps WHERE status='Open'"
    )).fetchone()[0]

    # Severity distribution
    sev_rows = db.execute(_t(
        "SELECT severity, COUNT(*) FROM gaps WHERE status='Open' "
        "GROUP BY severity"
    )).fetchall()
    severity_distribution = {r[0]: r[1] for r in sev_rows}

    # Controls mapped
    controls_mapped = sum(r[2] or 0 for r in rows)

    # Status overview
    status_overview = {
        "compliant": sum(r[2] or 0 for r in rows),
        "partial": sum(r[3] or 0 for r in rows),
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

    rich_with_empty = """
        SELECT f.id, f.name, f.description, f.version,
               f.original_file_name, f.file_url, f.file_type, f.file_size,
               f.uploaded_at, u.email AS uploaded_by,
               COALESCE(c.chunks, 0) AS chunks
        FROM frameworks f
        LEFT JOIN users u ON u.id = f.uploaded_by
        LEFT JOIN (
            SELECT framework_id, COUNT(*) AS chunks
            FROM framework_chunks
            GROUP BY framework_id
        ) c ON c.framework_id = f.id
        ORDER BY f.name ASC
    """
    rich_loaded_only = """
        SELECT f.id, f.name, f.description, f.version,
               f.original_file_name, f.file_url, f.file_type, f.file_size,
               f.uploaded_at, u.email AS uploaded_by,
               COUNT(fc.*) AS chunks
        FROM frameworks f
        LEFT JOIN users u ON u.id = f.uploaded_by
        JOIN framework_chunks fc ON fc.framework_id = f.id
        GROUP BY f.id, u.email
        HAVING COUNT(fc.*) > 0
        ORDER BY f.name ASC
    """
    basic_with_empty = """
        SELECT f.id, f.name, f.description,
               COALESCE(c.chunks, 0) AS chunks
        FROM frameworks f
        LEFT JOIN (
            SELECT framework_id, COUNT(*) AS chunks
            FROM framework_chunks GROUP BY framework_id
        ) c ON c.framework_id = f.id
        ORDER BY f.name ASC
    """
    basic_loaded_only = """
        SELECT f.id, f.name, f.description, COUNT(fc.*) AS chunks
        FROM frameworks f
        JOIN framework_chunks fc ON fc.framework_id = f.id
        GROUP BY f.id, f.name, f.description
        HAVING COUNT(fc.*) > 0
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

    where = "WHERE p.status = :st" if status_filter else ""

    # Defensive: progress columns are added by setup_policy_progress_columns
    # at startup, but if the migration didn't apply we still want this query
    # to succeed. Fall back to a basic SELECT in that case.
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

    rich = True
    try:
        rows = db.execute(_t(rich_sql), {"lim": limit, "st": status_filter}).fetchall()
    except Exception as e:
        print(f"[get_policies] rich query failed, falling back: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        rich = False
        rows = db.execute(_t(basic_sql), {"lim": limit, "st": status_filter}).fetchall()

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
    where = "WHERE cr.policy_id = :pid" if policy_id else ""
    rows = db.execute(_t(f"""
        SELECT cr.id, cr.policy_id, f.name AS framework,
               cr.compliance_score, cr.controls_covered,
               cr.controls_partial, cr.controls_missing,
               cr.status, cr.analyzed_at, cr.analysis_duration,
               cr.details::text AS details
        FROM compliance_results cr
        LEFT JOIN frameworks f ON cr.framework_id = f.id
        {where}
        ORDER BY cr.analyzed_at DESC
        LIMIT :lim
    """), {"lim": limit, "pid": policy_id}).fetchall()
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
    where_parts = []
    if policy_id:
        where_parts.append("g.policy_id = :pid")
    if status_filter:
        where_parts.append("g.status = :st")
    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    rows = db.execute(_t(f"""
        SELECT g.id, g.policy_id, f.name AS framework,
               cl.control_code AS control_id, g.control_name,
               g.severity, g.status, g.description, g.remediation,
               g.created_at
        FROM gaps g
        LEFT JOIN frameworks f ON g.framework_id = f.id
        LEFT JOIN control_library cl ON g.control_id = cl.id
        {where}
        ORDER BY g.created_at DESC
        LIMIT :lim
    """), {"lim": limit, "pid": policy_id, "st": status_filter}).fetchall()
    return [
        {"id": r[0], "policy_id": r[1], "framework": r[2] or "Unknown",
         "control_id": r[3] or "", "control_name": r[4],
         "severity": r[5], "status": r[6],
         "description": r[7], "remediation": r[8],
         "created_at": r[9].isoformat() if r[9] else None}
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
    where = "WHERE mr.policy_id = :pid" if policy_id else ""
    rows = db.execute(_t(f"""
        SELECT mr.id, mr.policy_id, f.name AS framework,
               cl.control_code AS control_id,
               mr.evidence_snippet, mr.confidence_score,
               mr.ai_rationale, mr.decision, mr.review_notes,
               mr.reviewed_at, mr.created_at
        FROM mapping_reviews mr
        LEFT JOIN frameworks f ON mr.framework_id = f.id
        LEFT JOIN control_library cl ON mr.control_id = cl.id
        {where}
        ORDER BY mr.created_at DESC
        LIMIT :lim
    """), {"lim": limit, "pid": policy_id}).fetchall()
    return [
        {"id": r[0], "policy_id": r[1], "framework": r[2] or "Unknown",
         "control_id": r[3] or "", "evidence_snippet": r[4],
         "confidence_score": r[5], "ai_rationale": r[6],
         "decision": r[7], "review_notes": r[8],
         "reviewed_at": r[9].isoformat() if r[9] else None,
         "created_at": r[10].isoformat() if r[10] else None}
        for r in rows
    ]


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
        results = await run_checkpoint_analysis(
            db, request.policy_id, request.frameworks,
            progress_cb=_progress_cb, resume=resume,
        )
        if isinstance(results, dict) and results.get("paused"):
            return {"success": True, "paused": True, "results": results.get("results", {})}
        set_policy_progress(db, policy.id, 100, "Completed")
    except Exception as e:
        try:
            db.execute(
                _t("UPDATE policies SET status='failed', progress=0, "
                   "progress_stage='Analysis failed' WHERE id=:pid"),
                {"pid": policy.id},
            )
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    return {"success": True, "results": results}


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
            set_policy_progress(db, policy_id, 100, "Completed")
    except Exception as e:
        try:
            db.execute(_t(
                "UPDATE policies SET status='failed', progress=0, "
                "progress_stage='Analysis failed' WHERE id = :pid"
            ), {"pid": policy_id})
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
async def chat_assistant(payload: Dict[str, Any], db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    message = payload.get("message") or ""
    policy_id = payload.get("policy_id")
    response = await chat_with_context(db, message, policy_id=policy_id)
    return {"response": response, "timestamp": datetime.now(timezone.utc).isoformat()}


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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Upload a framework reference document.

    Admin-only. Persists the file under /uploads/frameworks/<timestamped>
    so re-uploads don't overwrite previous files, and writes the file
    metadata (name, version, file_url, uploaded_at, uploaded_by) onto the
    framework row so the framework is treated as a real database-backed
    uploaded document — not just a static name.
    """
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

    fw_dir = UPLOAD_DIR / "frameworks"
    fw_dir.mkdir(exist_ok=True)
    stored_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{original_name}"
    file_path = fw_dir / stored_name
    file_path.write_bytes(raw)

    from backend.framework_loader import load_framework_document

    result = await load_framework_document(db, str(file_path), framework, original_name)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Update framework row with the file metadata so the UI can show the
    # real uploaded document and the Replace flow works cleanly.
    try:
        db.execute(_sql("""
            UPDATE frameworks
               SET original_file_name = :ofn,
                   file_url    = :furl,
                   file_type   = :ft,
                   file_size   = :fs,
                   uploaded_at = :at,
                   uploaded_by = :uby,
                   version     = COALESCE(NULLIF(:ver, ''), version),
                   description = COALESCE(NULLIF(:desc, ''), description)
             WHERE name = :name
        """), {
            "ofn":  original_name,
            "furl": f"/uploads/frameworks/{stored_name}",
            "ft":   ext.replace(".", "").upper(),
            "fs":   len(raw),
            "at":   datetime.now(timezone.utc),
            "uby":  str(current_user.id) if hasattr(current_user, "id") else None,
            "ver":  (version or "").strip(),
            "desc": (description or "").strip(),
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

        # Add lockout columns to users (idempotent)
        db.execute(_t("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0
        """))
        db.execute(_t("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ DEFAULT NULL
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

