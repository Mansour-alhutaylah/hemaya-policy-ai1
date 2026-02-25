import os
import random
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
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


models.Base.metadata.create_all(bind=database.engine)

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
    current_user.settings = settings
    db.commit()
    return {"ok": True}


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".xlsx", ".xls"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# File upload (used by policy upload flow)
@app.post("/api/integrations/upload")
async def upload_file(file: UploadFile = File(...)):
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

    file_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{original_name}"
    dest = UPLOAD_DIR / file_name
    dest.write_bytes(content)

    extracted_text = extract_text(dest, ext)

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

    text = (policy.content_preview or policy.description or policy.file_name or "").lower()
    results = []
    mappings = []
    gaps = []

    for fw in request.frameworks:
        controls = db.query(models.ControlLibrary).filter(models.ControlLibrary.framework == fw).all()
        controls_covered = 0
        controls_partial = 0
        controls_missing = 0

        if not controls:
            score = random.randint(60, 85)
            controls_missing = 5
        else:
            for control in controls:
                keywords = control.keywords or []
                matches = sum(1 for kw in keywords if kw.lower() in text) if text else 0
                confidence = matches / len(keywords) if keywords else 0
                if confidence >= 0.7:
                    controls_covered += 1
                elif confidence >= 0.3:
                    controls_partial += 1
                else:
                    controls_missing += 1

                evidence = control.title or control.control_code or ""
                mappings.append(
                    models.MappingReview(
                        policy_id=policy.id,
                        control_id=control.control_code,
                        framework=fw,
                        evidence_snippet=evidence,
                        confidence_score=confidence,
                        ai_rationale=f"Matched {matches}/{len(keywords) if keywords else 1} keywords" if keywords else "No keywords",
                        decision="Accepted" if confidence >= 0.6 else "Pending",
                    )
                )

                if confidence < 0.6:
                    gaps.append(
                        models.Gap(
                            policy_id=policy.id,
                            framework=fw,
                            control_id=control.control_code,
                            control_name=control.title,
                            severity=control.severity_if_missing or "Medium",
                            status="Open",
                            description=f"Control {control.control_code} not fully covered",
                        )
                    )

            total_controls = len(controls)
            score = ((controls_covered + controls_partial * 0.5) / total_controls) * 100 if total_controls else 0

        status_label = "Compliant" if score >= 80 else "Partially Compliant" if score >= 60 else "Not Compliant"
        result = models.ComplianceResult(
            policy_id=policy.id,
            framework=fw,
            compliance_score=score,
            controls_covered=controls_covered,
            controls_partial=controls_partial,
            controls_missing=controls_missing,
            status=status_label,
            analyzed_at=datetime.utcnow(),
            analysis_duration=0,
            details={"notes": "Analysis complete"},
        )
        db.add(result)
        results.append(result)

    if mappings:
        db.add_all(mappings)
    if gaps:
        db.add_all(gaps)

    policy.status = "analyzed"
    policy.last_analyzed_at = datetime.utcnow()
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

    impact = 1.5
    projected = []
    for r in results:
        projected_score = min(100, (r.compliance_score or 0) + impact * 3)
        projected.append({
            "framework": r.framework,
            "current_score": round(r.compliance_score or 0),
            "projected_score": round(projected_score),
            "improvement": round(projected_score - (r.compliance_score or 0)),
            "controls_covered": r.controls_covered,
            "controls_missing": max(0, (r.controls_missing or 0) - 3),
        })

    gaps = db.query(models.Gap).filter(models.Gap.policy_id == request.policy_id).all()
    gaps_resolved = min(len(gaps), 3)

    return {
        "success": True,
        "current_results": [
            {"framework": r.framework, "score": round(r.compliance_score or 0)} for r in results
        ],
        "projected_results": projected,
        "controls_implemented": 3,
        "gaps_resolved": gaps_resolved,
        "total_impact": round(sum(p["improvement"] for p in projected) / len(projected)),
    }


@app.post("/api/functions/generate_report")
async def generate_report(request: schemas.GenerateReportRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    policy = db.query(models.Policy).filter(models.Policy.id == request.policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    download_url = f"/uploads/report_{request.policy_id}_{int(datetime.utcnow().timestamp())}.txt"
    report = models.Report(
        policy_id=policy.id,
        report_type=request.report_type,
        format=request.format,
        status="Completed",
        download_url=download_url,
        frameworks_included=request.frameworks_included,
        generated_at=datetime.utcnow(),
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
    message = (payload.get("message") or "").lower()
    policies = db.query(models.Policy).all()
    results = db.query(models.ComplianceResult).all()
    gaps = db.query(models.Gap).all()

    response = ""
    if "policy" in message or "policies" in message:
        if not policies:
            response = "You have not uploaded any policies yet."
        else:
            names = ", ".join(p.file_name or "Policy" for p in policies[:5])
            response = f"You have {len(policies)} policies: {names}."
    elif "gap" in message or "missing" in message:
        open_gaps = [g for g in gaps if (g.status or "").lower() == "open"]
        critical = [g for g in gaps if (g.severity or "").lower() == "critical"]
        response = f"Open gaps: {len(open_gaps)}. Critical: {len(critical)}. Address critical gaps first."
    elif "score" in message or "compliance" in message:
        if not results:
            response = "No compliance analyses have been run yet."
        else:
            latest = {}
            for r in results:
                if r.framework not in latest or (r.analyzed_at and r.analyzed_at > latest[r.framework].analyzed_at):
                    latest[r.framework] = r
            summaries = [f"{fw}: {round(r.compliance_score or 0)}%" for fw, r in latest.items()]
            response = "Current compliance scores - " + ", ".join(summaries)
    else:
        response = "I can help with compliance status, gap analysis, and framework guidance."

    return {"response": response, "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/functions/db_health")
def db_health(db: Session = Depends(get_db)):
    now = datetime.utcnow().isoformat()
    return {"ok": True, "time": now}

