import os
import random
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

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
from backend.text_extractor import extract_text
from backend.rag_engine import run_full_analysis, chat_with_context
from backend.vector_store import get_embeddings, store_chunks_with_embeddings, delete_policy_chunks
from backend.chunker import chunk_text


app = FastAPI()


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


def serialize(obj: Any):
    return jsonable_encoder(obj)


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
@app.post("/api/auth/register", response_model=schemas.User)
def register(user: schemas.RegisterRequest, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # bcrypt limit (72 bytes)
    if len(user.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be <= 72 bytes")

    hashed_password = auth.get_password_hash(user.password)

    new_user = models.User(
        email=user.email,
        password_hash=hashed_password,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user



@app.post("/api/auth/login")
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if not db_user or not auth.verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = auth.create_access_token(data={"sub": db_user.email})
    return {
    "token": access_token,
    "user": {
        "id": db_user.id,
        "email": db_user.email,
        "first_name": db_user.first_name,
        "last_name": db_user.last_name,
        "phone": db_user.phone,
    }
}



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

# File upload (used by policy upload flow)
@app.post("/api/integrations/upload")
async def upload_file(file: UploadFile = File(...), policy_id: Optional[str] = Form(None), current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    original_name = file.filename or "upload"
    ext = Path(original_name).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 50 MB limit")

    file_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{original_name}"
    dest = UPLOAD_DIR / file_name
    dest.write_bytes(content)

    extracted_text = extract_text(dest, ext)

    # Chunk and embed at upload time so analysis only needs to search, not re-embed.
    # policy_id must be passed as a form field by the caller once the Policy row exists.
    if extracted_text and not extracted_text.startswith("[Extraction error") and policy_id:
        chunks = chunk_text(extracted_text)
        embeddings = await get_embeddings([c["text"] for c in chunks])
        store_chunks_with_embeddings(db, policy_id, chunks, embeddings)

    return {
        "file_url": f"/uploads/{file_name}",
        "content_preview": extracted_text,
        "char_count": len(extracted_text),
    }


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


@app.post("/api/entities/{entity}")
def create_or_update_entity(entity: str, payload: Dict[str, Any], db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    model = ENTITY_MAP.get(entity)
    if not model:
        raise HTTPException(status_code=404, detail="Entity not found")

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


@app.delete("/api/entities/{entity}/{item_id}")
def delete_entity(entity: str, item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    model = ENTITY_MAP.get(entity)
    if not model:
        raise HTTPException(status_code=404, detail="Entity not found")
    item = db.query(model).filter(model.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


# Functions
@app.post("/api/functions/analyze_policy")
async def analyze_policy(request: schemas.AnalyzeRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    policy = db.query(models.Policy).filter(models.Policy.id == request.policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    policy.status = "processing"
    db.commit()

    # Remove previous analysis data for this policy to prevent duplicates on re-run
    db.query(models.Gap).filter(models.Gap.policy_id == policy.id).delete()
    db.query(models.MappingReview).filter(models.MappingReview.policy_id == policy.id).delete()
    db.query(models.ComplianceResult).filter(models.ComplianceResult.policy_id == policy.id).delete()
    db.commit()

    ai_results = await run_full_analysis(db, request.policy_id, request.frameworks)

    results = []
    mappings = []
    gaps = []

    for fw, fw_data in ai_results.items():
        for detail in fw_data["details"]:
            mappings.append(
                models.MappingReview(
                    policy_id=policy.id,
                    control_id=detail["control_code"],
                    framework=fw,
                    evidence_snippet=detail.get("evidence", ""),
                    confidence_score=detail.get("confidence", 0.0),
                    ai_rationale=detail.get("rationale", ""),
                    decision="Accepted" if detail["status"] == "Compliant" else "Pending",
                )
            )

            if detail["status"] != "Compliant":
                gaps.append(
                    models.Gap(
                        policy_id=policy.id,
                        framework=fw,
                        control_id=detail["control_code"],
                        control_name=detail.get("control_title", detail["control_code"]),
                        severity=detail.get("priority", detail.get("severity_if_missing", "Medium")),
                        status="Open",
                        description=detail.get("gaps", f"Control {detail['control_code']} gap identified"),
                        remediation=detail.get("recommendation", "Review and implement this control"),
                    )
                )

        score = fw_data["score"]
        status_label = "Compliant" if score >= 80 else "Partially Compliant" if score >= 60 else "Not Compliant"
        result = models.ComplianceResult(
            policy_id=policy.id,
            framework=fw,
            compliance_score=score,
            controls_covered=fw_data["compliant"],
            controls_partial=fw_data["partial"],
            controls_missing=fw_data["non_compliant"],
            status=status_label,
            analyzed_at=datetime.now(timezone.utc),
            analysis_duration=0,
            details={"per_control": fw_data["details"]},
        )
        db.add(result)
        results.append(result)

    if mappings:
        db.add_all(mappings)
    if gaps:
        db.add_all(gaps)

    policy.status = "analyzed"
    policy.last_analyzed_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "success": True,
        "results": serialize(results),
        "mappings_created": len(mappings),
        "gaps_created": len(gaps),
    }


@app.post("/api/functions/run_simulation")
async def run_simulation(request: schemas.RunSimulationRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    results = db.query(models.ComplianceResult).filter(models.ComplianceResult.policy_id == request.policy_id).all()
    if not results:
        return JSONResponse(status_code=404, content={"error": "No results to simulate"})

    controls_selected = len(request.control_ids or [])
    impact = 1.5 + controls_selected * 0.5
    controls_resolved = max(3, controls_selected)
    projected = []
    for r in results:
        projected_score = min(100, (r.compliance_score or 0) + impact * 3)
        projected.append({
            "framework": r.framework,
            "current_score": round(r.compliance_score or 0),
            "projected_score": round(projected_score),
            "improvement": round(projected_score - (r.compliance_score or 0)),
            "controls_covered": r.controls_covered,
            "controls_missing": max(0, (r.controls_missing or 0) - controls_resolved),
        })

    gaps = db.query(models.Gap).filter(models.Gap.policy_id == request.policy_id).all()
    gaps_resolved = min(len(gaps), controls_resolved)

    return {
        "success": True,
        "current_results": [
            {"framework": r.framework, "score": round(r.compliance_score or 0)} for r in results
        ],
        "projected_results": projected,
        "controls_implemented": controls_resolved,
        "gaps_resolved": gaps_resolved,
        "total_impact": round(sum(p["improvement"] for p in projected) / len(projected)),
    }


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

    audit = models.AuditLog(
        actor=current_user.email,
        action="report_generate",
        target_type="report",
        target_id=report.id,
        details={"report_type": request.report_type, "format": request.format},
    )
    db.add(audit)
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Upload a framework reference document (NCA ECC, ISO 27001, NIST 800-53)."""
    ext = Path(file.filename or "upload").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    fw_dir = UPLOAD_DIR / "frameworks"
    fw_dir.mkdir(exist_ok=True)
    file_path = fw_dir / (file.filename or "upload")

    content = await file.read()
    file_path.write_bytes(content)

    from backend.framework_loader import load_framework_document

    result = await load_framework_document(db, str(file_path), framework, file.filename or "")

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@app.get("/api/functions/framework_status")
def framework_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Check which frameworks have reference documents loaded."""
    from backend.framework_loader import get_framework_stats

    stats = get_framework_stats(db)

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

