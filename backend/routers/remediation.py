"""
routers/remediation.py

POST /api/remediation/generate  — triggered when a user accepts a Non-Compliant
                                   mapping; generates an AI draft and scores it.
GET  /api/remediation/drafts    — list remediation drafts for a policy.
PATCH /api/remediation/drafts/{draft_id} — update draft status (approve/reject).
"""
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from backend import auth, models
from backend.database import get_db
from backend.checkpoint_analyzer import score_remediation_draft
from backend.remediation_engine import generate_remediation_draft

router = APIRouter(prefix="/api/remediation", tags=["remediation"])

# ── Auth dependency (mirrors main.py; extracted here to avoid circular import) ─

_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _get_current_user(
    token: str = Depends(_oauth2),
    db: Session = Depends(get_db),
) -> models.User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise exc
    except JWTError:
        raise exc
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise exc
    return user


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class GenerateRemediationRequest(BaseModel):
    mapping_review_id: str
    policy_id: str


class CheckpointDiff(BaseModel):
    requirement: str
    was_met: Optional[bool]
    is_now_met: bool
    confidence: float
    evidence: str


class GenerateRemediationResponse(BaseModel):
    draft_id: str
    policy_id: str
    control_code: str
    control_title: str
    framework_name: str
    suggested_policy_text: str
    section_headers: List[str]
    missing_requirements: List[str]
    remediation_status: str
    old_score: float
    new_score: float
    improvement_pct: float
    checkpoints_fixed: int
    checkpoints_total: int
    checkpoint_details: List[CheckpointDiff]


class UpdateDraftRequest(BaseModel):
    remediation_status: str          # approved | rejected | under_review
    review_notes: Optional[str] = None


class DraftSummary(BaseModel):
    id: str
    policy_id: str
    control_code: Optional[str]
    control_title: Optional[str]
    framework_name: Optional[str]
    remediation_status: str
    missing_requirements: List[str]
    section_headers: Optional[List[str]]
    created_at: str
    updated_at: Optional[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_policy_text(db: Session, policy_id: str, fallback_preview: str) -> str:
    """Concatenate ordered policy chunks; fall back to content_preview."""
    rows = db.execute(sql_text(
        "SELECT chunk_text FROM policy_chunks "
        "WHERE policy_id = :pid ORDER BY chunk_index"
    ), {"pid": policy_id}).fetchall()
    text = "\n\n".join(r[0] for r in rows if r[0])
    return text if text else (fallback_preview or "")


def _load_checkpoints(db: Session, framework_id: str, control_code: str,
                      framework_name: str) -> list:
    """Load and normalise control_checkpoints rows for one control."""
    rows = db.execute(sql_text(
        "SELECT id, control_code, checkpoint_index, requirement, keywords, weight "
        "FROM control_checkpoints "
        "WHERE framework = :fwid AND control_code = :cc "
        "ORDER BY checkpoint_index"
    ), {"fwid": framework_id, "cc": control_code}).fetchall()

    checkpoints = []
    for r in rows:
        kw = r[4]
        if isinstance(kw, str):
            try:
                kw = json.loads(kw)
            except (ValueError, TypeError):
                kw = []
        checkpoints.append({
            "checkpoint_id": r[0],
            "control_code": r[1],
            "checkpoint_index": r[2],
            "requirement": r[3],
            "keywords": kw or [],
            "weight": float(r[5] or 1.0),
            "framework": framework_name,
        })
    return checkpoints


def _extract_stored_verdicts(
    db: Session, policy_id: str, framework_id: str, control_code: str
) -> tuple:
    """
    Pull old_score and the set of failing requirements from the most recent
    compliance_results row.

    Returns (old_score: float | None, failing_reqs: set[str]).
    """
    row = db.execute(sql_text(
        "SELECT compliance_score, details FROM compliance_results "
        "WHERE policy_id = :pid AND framework_id = :fwid "
        "ORDER BY analyzed_at DESC LIMIT 1"
    ), {"pid": policy_id, "fwid": framework_id}).fetchone()

    if not row:
        return None, set()

    # details is stored as JSON; psycopg2 may return dict/list or a string.
    raw = row[1]
    if raw is None:
        return float(row[0]) if row[0] is not None else None, set()

    try:
        details = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return float(row[0]) if row[0] is not None else None, set()

    if not isinstance(details, list):
        return float(row[0]) if row[0] is not None else None, set()

    for ctrl in details:
        if ctrl.get("control_code") == control_code:
            old_score = float(ctrl.get("score", 0.0))
            failing = {
                sr["requirement"]
                for sr in ctrl.get("sub_requirements", [])
                if sr.get("status") == "Not Met"
            }
            return old_score, failing

    # Control found in results but not in details list — use aggregate score.
    return float(row[0]) if row[0] is not None else None, set()


def _open_gap(db: Session, policy_id: str, control_id: str, draft_id: str) -> None:
    """Mark the most recent open gap for this control as In Progress."""
    db.execute(sql_text("""
        UPDATE gaps SET status = 'In Progress',
                        remediation_notes = :note
        WHERE id = (
            SELECT id FROM gaps
            WHERE policy_id = :pid
              AND control_id = :cid
              AND status = 'Open'
            ORDER BY created_at DESC
            LIMIT 1
        )
    """), {
        "note": f"AI remediation draft created (draft_id={draft_id})",
        "pid": policy_id,
        "cid": control_id,
    })


def _write_audit(db: Session, actor_id: str, draft_id: str, policy_id: str,
                 action: str, detail: dict) -> None:
    try:
        db.execute(sql_text("""
            INSERT INTO audit_logs
            (id, actor_id, action, target_type, target_id, details, timestamp)
            VALUES (:id, :actor, :action, 'remediation_draft', :tid, :det, :ts)
        """), {
            "id": str(uuid.uuid4()),
            "actor": actor_id,
            "action": action,
            "tid": draft_id,
            "det": json.dumps({**detail, "policy_id": policy_id}),
            "ts": datetime.now(timezone.utc),
        })
    except Exception as e:
        print(f"[audit] write failed: {e}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=GenerateRemediationResponse)
async def generate_remediation(
    body: GenerateRemediationRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_get_current_user),
):
    """
    Accept a Non-Compliant mapping and generate an AI remediation draft.

    Workflow:
    1. Resolve the mapping review → control → framework → policy.
    2. Reconstruct full policy text from stored chunks.
    3. Extract old compliance score and failing checkpoints from stored results.
    4. Call generate_remediation_draft() — produces the additive-only text.
    5. Call score_remediation_draft()    — verifies the merged text via GPT.
    6. Mark the related gap as "In Progress".
    7. Return draft text + before/after scores to the frontend.
    """
    # ── 1. Load and validate MappingReview ───────────────────────────────────
    review = (
        db.query(models.MappingReview)
        .filter(models.MappingReview.id == body.mapping_review_id)
        .first()
    )
    if not review:
        raise HTTPException(status_code=404, detail="Mapping review not found.")
    if review.policy_id != body.policy_id:
        raise HTTPException(status_code=400, detail="mapping_review_id does not belong to this policy.")

    # ── 2. Load Policy ────────────────────────────────────────────────────────
    policy = db.query(models.Policy).filter(models.Policy.id == body.policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found.")

    # ── 3. Load Framework ─────────────────────────────────────────────────────
    framework = (
        db.query(models.Framework)
        .filter(models.Framework.id == str(review.framework_id))
        .first()
    ) if review.framework_id else None
    framework_name = framework.name if framework else "Unknown Framework"
    # Use None (not "") so FK columns receive NULL rather than a non-existent ID.
    framework_id = str(review.framework_id) if review.framework_id else None

    # ── 4. Load ControlLibrary ────────────────────────────────────────────────
    ctrl = (
        db.query(models.ControlLibrary)
        .filter(models.ControlLibrary.id == str(review.control_id))
        .first()
    ) if review.control_id else None
    control_code = ctrl.control_code if ctrl else ""
    control_title = ctrl.title if ctrl else ""

    # ── 5. Reconstruct full policy text ───────────────────────────────────────
    policy_text = _get_policy_text(db, policy.id, policy.content_preview or "")
    if not policy_text.strip():
        raise HTTPException(
            status_code=422,
            detail="Policy text is empty. Re-upload the document and run analysis first.",
        )

    # ── 6. Load checkpoints from DB ───────────────────────────────────────────
    checkpoints = _load_checkpoints(db, framework_id, control_code, framework_name)

    # ── 7. Get old score + failing requirements from stored results ────────────
    old_score, failing_reqs = _extract_stored_verdicts(
        db, policy.id, framework_id, control_code
    )

    # Determine missing requirement strings for the draft generator.
    # Priority: stored failing reqs → all checkpoints → ai_rationale fallback.
    if failing_reqs:
        missing_checkpoint_texts = list(failing_reqs)
    elif checkpoints:
        missing_checkpoint_texts = [cp["requirement"] for cp in checkpoints]
    else:
        # No checkpoint table rows at all — extract from rationale as last resort.
        missing_checkpoint_texts = [
            line.strip("- •").strip()
            for line in (review.ai_rationale or "").split("\n")
            if line.strip() and len(line.strip()) > 20
        ][:10]

    if not missing_checkpoint_texts:
        raise HTTPException(
            status_code=422,
            detail="Cannot determine missing requirements. Run compliance analysis first.",
        )

    # If control_checkpoints table had no rows, build synthetic checkpoints
    # from the missing texts so score_remediation_draft can still run GPT verification.
    if not checkpoints:
        checkpoints = [
            {
                "checkpoint_id": f"synthetic-{i}",
                "control_code": control_code,
                "checkpoint_index": i + 1,
                "requirement": req,
                "keywords": [],
                "weight": 1.0,
                "framework": framework_name,
            }
            for i, req in enumerate(missing_checkpoint_texts)
        ]

    # ── 8. Generate the AI draft ──────────────────────────────────────────────
    try:
        draft = generate_remediation_draft(
            db=db,
            policy_id=policy.id,
            policy_text=policy_text,
            control={
                "framework_name": framework_name,
                "framework_id": framework_id,        # already None-safe (fixed above)
                "control_id": str(review.control_id) if review.control_id else None,
                "control_code": control_code,
                "control_title": control_title,
            },
            ai_rationale=review.ai_rationale or "",
            missing_checkpoints=missing_checkpoint_texts,
            mapping_review_id=review.id,
            created_by_id=str(current_user.id),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Draft generation failed: {type(e).__name__}: {e}")

    # ── 9. Re-analyse merged text to measure improvement ─────────────────────
    try:
        score_result = await score_remediation_draft(
            db=db,
            original_policy_text=policy_text,
            draft_addition_text=draft.suggested_policy_text,
            checkpoints=checkpoints,
            old_score_override=old_score,
            previously_failing_requirements=failing_reqs,
        )
    except Exception as e:
        # Scoring failure must not block the draft — return zero-delta scores.
        print(f"[remediation] score_remediation_draft failed: {e}")
        score_result = {
            "old_score": round(old_score, 1) if old_score is not None else 0.0,
            "new_score": round(old_score, 1) if old_score is not None else 0.0,
            "improvement_pct": 0.0,
            "checkpoints_fixed": 0,
            "checkpoints_total": len(checkpoints),
            "checkpoint_details": [],
        }

    # ── 10. Mark related gap as In Progress ───────────────────────────────────
    try:
        _open_gap(db, policy.id, str(review.control_id) if review.control_id else "", draft.id)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[remediation] gap update failed (non-fatal): {e}")

    # ── 10.5. Mark the mapping review as Accepted ─────────────────────────────
    # This is the write that persists across page refreshes. Without it the
    # mapping_reviews row keeps decision="Pending"/"Flagged" and the frontend
    # reverts to that value on next load even though a draft was created.
    try:
        review.decision    = "Accepted"
        review.reviewer_id = current_user.id
        review.reviewed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[remediation] mapping review status update failed (non-fatal): {e}")

    # ── 11. Audit log ─────────────────────────────────────────────────────────
    _write_audit(db, str(current_user.id), draft.id, policy.id,
                 "generate_remediation_draft", {
                     "control_code": control_code,
                     "framework": framework_name,
                     "old_score": score_result["old_score"],
                     "new_score": score_result["new_score"],
                 })
    try:
        db.commit()
    except Exception:
        db.rollback()

    return GenerateRemediationResponse(
        draft_id=draft.id,
        policy_id=policy.id,
        control_code=control_code,
        control_title=control_title,
        framework_name=framework_name,
        suggested_policy_text=draft.suggested_policy_text,
        section_headers=draft.section_headers or [],
        missing_requirements=draft.missing_requirements or [],
        remediation_status=draft.remediation_status,
        **score_result,
    )


@router.get("/drafts/{draft_id}")
def get_draft(
    draft_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_get_current_user),
):
    """Full detail of one remediation draft, including original policy text for diffing."""
    row = db.execute(sql_text("""
        SELECT rd.id, rd.policy_id, rd.suggested_policy_text,
               rd.missing_requirements, rd.section_headers,
               rd.remediation_status, rd.ai_rationale, rd.review_notes,
               cl.control_code, cl.title,
               f.name,
               rd.created_at, rd.updated_at
        FROM remediation_drafts rd
        LEFT JOIN control_library cl ON rd.control_id = cl.id::text
        LEFT JOIN frameworks f       ON rd.framework_id = f.id
        WHERE rd.id = :did
    """), {"did": draft_id}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Draft not found.")

    def _j(val):
        if val is None: return []
        if isinstance(val, (list, dict)): return val
        try: return json.loads(val)
        except (ValueError, TypeError): return []

    # Concatenate policy chunks so the frontend can build the diff.
    chunk_rows = db.execute(sql_text(
        "SELECT chunk_text FROM policy_chunks "
        "WHERE policy_id = :pid ORDER BY chunk_index"
    ), {"pid": row[1]}).fetchall()
    original_text = "\n\n".join(r[0] for r in chunk_rows if r[0])

    return {
        "id": row[0],
        "policy_id": row[1],
        "suggested_policy_text": row[2] or "",
        "missing_requirements": _j(row[3]),
        "section_headers": _j(row[4]),
        "remediation_status": row[5],
        "ai_rationale": row[6],
        "review_notes": row[7],
        "control_code": row[8],
        "control_title": row[9],
        "framework_name": row[10],
        "created_at": row[11].isoformat() if row[11] else None,
        "updated_at": row[12].isoformat() if row[12] else None,
        "original_policy_text": original_text,
    }


@router.get("/drafts", response_model=List[DraftSummary])
def list_drafts(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_get_current_user),
):
    """Return all remediation drafts for a policy, newest first."""
    rows = db.execute(sql_text("""
        SELECT rd.id, rd.policy_id, cl.control_code, cl.title,
               f.name AS framework_name,
               rd.remediation_status, rd.missing_requirements,
               rd.section_headers, rd.created_at, rd.updated_at
        FROM remediation_drafts rd
        LEFT JOIN control_library cl ON rd.control_id = cl.id::text
        LEFT JOIN frameworks f       ON rd.framework_id = f.id
        WHERE rd.policy_id = :pid
        ORDER BY rd.created_at DESC
    """), {"pid": policy_id}).fetchall()

    result = []
    for r in rows:
        def _parse_json(val):
            if val is None:
                return []
            if isinstance(val, (list, dict)):
                return val
            try:
                return json.loads(val)
            except (ValueError, TypeError):
                return []

        result.append(DraftSummary(
            id=r[0],
            policy_id=r[1],
            control_code=r[2],
            control_title=r[3],
            framework_name=r[4],
            remediation_status=r[5],
            missing_requirements=_parse_json(r[6]),
            section_headers=_parse_json(r[7]),
            created_at=r[8].isoformat() if r[8] else "",
            updated_at=r[9].isoformat() if r[9] else None,
        ))
    return result


@router.get("/policies/{policy_id}/drafts", response_model=List[DraftSummary])
def list_drafts_by_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_get_current_user),
):
    """
    Path-parameter version of the draft list endpoint.

    WHY THIS EXISTS AS A SEPARATE ROUTE:
      GET /api/remediation/drafts/{policy_id}  would collide with
      GET /api/remediation/drafts/{draft_id}  — both are UUID path segments
      and FastAPI cannot distinguish them by type alone.  The non-ambiguous
      canonical URL is therefore /api/remediation/policies/{policy_id}/drafts.
      The query-parameter form (/api/remediation/drafts?policy_id=...) also
      remains available for existing clients.

    Returns all remediation drafts for a policy, newest first.
    """
    rows = db.execute(sql_text("""
        SELECT rd.id, rd.policy_id, cl.control_code, cl.title,
               f.name  AS framework_name,
               rd.remediation_status, rd.missing_requirements,
               rd.section_headers, rd.created_at, rd.updated_at
        FROM   remediation_drafts rd
        LEFT JOIN control_library cl ON rd.control_id   = cl.id::text
        LEFT JOIN frameworks      f  ON rd.framework_id = f.id
        WHERE  rd.policy_id = :pid
        ORDER  BY rd.created_at DESC
    """), {"pid": policy_id}).fetchall()

    def _j(val):
        if val is None:                    return []
        if isinstance(val, (list, dict)):  return val
        try:                               return json.loads(val)
        except (ValueError, TypeError):    return []

    return [
        DraftSummary(
            id=r[0], policy_id=r[1], control_code=r[2], control_title=r[3],
            framework_name=r[4], remediation_status=r[5],
            missing_requirements=_j(r[6]), section_headers=_j(r[7]),
            created_at=r[8].isoformat() if r[8] else "",
            updated_at=r[9].isoformat() if r[9] else None,
        )
        for r in rows
    ]


@router.patch("/drafts/{draft_id}")
def update_draft_status(
    draft_id: str,
    body: UpdateDraftRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_get_current_user),
):
    """
    Advance a draft through the review lifecycle.
    Valid transitions: draft → under_review → approved | rejected.
    Approving a draft promotes the ai_draft PolicyVersion to a final snapshot.
    """
    allowed = models.REMEDIATION_STATUSES
    if body.remediation_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"remediation_status must be one of: {sorted(allowed)}",
        )

    draft = (
        db.query(models.RemediationDraft)
        .filter(models.RemediationDraft.id == draft_id)
        .first()
    )
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")

    draft.remediation_status = body.remediation_status
    draft.review_notes = body.review_notes or draft.review_notes
    draft.reviewed_by = current_user.id
    draft.reviewed_at = datetime.now(timezone.utc)

    # On approval: snapshot as a "final" PolicyVersion for the audit trail.
    if body.remediation_status == "approved":
        from backend.remediation_engine import _next_version_number
        final_version = models.PolicyVersion(
            policy_id=draft.policy_id,
            version_number=_next_version_number(db, draft.policy_id),
            version_type="final",
            content=draft.suggested_policy_text,
            compliance_score=None,
            remediation_draft_id=draft.id,
            change_summary=f"Approved by {current_user.email}. {body.review_notes or ''}".strip(),
            created_by=current_user.id,
        )
        db.add(final_version)

    try:
        db.commit()
        db.refresh(draft)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")

    _write_audit(db, str(current_user.id), draft.id, draft.policy_id,
                 f"remediation_draft_{body.remediation_status}", {
                     "review_notes": body.review_notes,
                 })
    try:
        db.commit()
    except Exception:
        db.rollback()

    return {"id": draft.id, "remediation_status": draft.remediation_status}
