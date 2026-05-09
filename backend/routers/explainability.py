"""
routers/explainability.py

GET  /api/mapping-reviews                              — explainability rows
                                                          joining policy_ecc_assessments
                                                          + ecc_framework for both
                                                          ECC-2 and SACS-002.
GET  /api/mapping-reviews/frameworks                   — frameworks that have analysis
                                                          rows for the given policy.
GET  /api/policy-versions                              — list versions for a policy.
POST /api/policy-versions/generate                     — generate a new ai_remediated
                                                          PolicyVersion addressing all
                                                          partial / non-compliant
                                                          controls in latest analysis.
GET  /api/policy-versions/{version_id}                 — one version (content + meta).
GET  /api/policies/{policy_id}/versions/{version_id}/download/pdf
                                                       — stream a PDF rendering of
                                                          the stored version content.
POST /api/policies/{policy_id}/versions/{version_id}/reanalyze
                                                       — re-run compliance analysis
                                                          using the version's content
                                                          (original file untouched).
"""
import io
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from backend import auth, models
from backend.database import get_db
from backend.pdf_export import build_policy_version_pdf
from backend.remediation_engine import (
    _next_version_number,
    generate_remediation_draft,
)


router = APIRouter(tags=["explainability"])

_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
ADMIN_EMAIL = "himayaadmin@gmail.com"


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


# ─── Helpers ─────────────────────────────────────────────────────────────────

# Status normalisation: assessments use lowercase enums; details JSON uses
# capitalised labels; UI uses Capitalised. Always emit lowercase to the client
# so a single switch works across both legacy and structured data.
_STATUS_FROM_DB = {
    "compliant": "compliant",
    "partial": "partial",
    "non_compliant": "non_compliant",
    "Compliant": "compliant",
    "Partial": "partial",
    "Non-Compliant": "non_compliant",
}


def _split_missing(gap_description: Optional[str]) -> list[str]:
    """
    The analyzers join unmet checkpoint requirements with '; '.
    Each requirement is pre-truncated to 120 chars before joining, so '; '
    is a reliable splitter. Empty input returns [].
    """
    if not gap_description:
        return []
    parts = [p.strip() for p in gap_description.split("; ")]
    return [p for p in parts if p]


def _build_recommended_fix(
    control_code: str,
    control_text: str,
    missing: list[str],
    status_norm: str,
) -> str:
    """
    Deterministic, no-LLM recommendation text. Matches the verdict to a
    concrete remediation pattern so the user can see what to add to the
    policy without paying for a per-row GPT call.
    """
    if status_norm == "compliant":
        return ""
    if status_norm == "partial":
        if not missing:
            return (
                f"Strengthen existing language for {control_code} so it "
                "specifies WHAT is required, WHO is responsible, and HOW it "
                "is enforced."
            )
        bullets = "\n".join(f"  - {m}" for m in missing[:5])
        return (
            f"Extend the relevant policy section so it explicitly addresses "
            f"the following sub-requirements of {control_code}:\n{bullets}"
        )
    # non_compliant
    if not control_text:
        return f"Add a new policy section that fully implements {control_code}."
    return (
        f"Add a new policy section that explicitly implements {control_code}: "
        f"{control_text[:240]}"
    )


def _build_reason(
    status_norm: str,
    confidence: float,
    has_evidence: bool,
    missing_count: int,
) -> str:
    """One-sentence verdict explanation, shown above the evidence card."""
    pct = f"{int(round((confidence or 0) * 100))}%"
    if status_norm == "compliant":
        return (
            f"Policy contains specific language implementing this control "
            f"(confidence {pct})."
        )
    if status_norm == "partial":
        if not has_evidence:
            return (
                f"Related language found but it is generic or incomplete "
                f"(confidence {pct}, {missing_count} sub-requirement(s) unmet)."
            )
        return (
            f"Policy partially implements this control — "
            f"{missing_count} sub-requirement(s) still unmet (confidence {pct})."
        )
    # non_compliant
    if has_evidence:
        return (
            f"Related language present but too vague to satisfy the control "
            f"(confidence {pct})."
        )
    return f"No relevant policy evidence found (confidence {pct})."


def _check_policy_access(
    db: Session, policy_id: str, user: models.User
) -> models.Policy:
    """
    Fetch the policy or raise 404. Non-admins only see their own policies.
    Mirrors the access-control pattern used in /api/entities/MappingReview.
    """
    policy = db.query(models.Policy).filter(models.Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found.")
    if user.email != ADMIN_EMAIL and str(policy.owner_id) != str(user.id):
        raise HTTPException(status_code=404, detail="Policy not found.")
    return policy


# ─── Mapping Reviews (explainability) ────────────────────────────────────────


class MappingReviewItem(BaseModel):
    policy_id: str
    framework_id: str
    framework_name: str
    control_code: str
    checkpoint_index: int = 1
    status: str                         # compliant | partial | non_compliant
    confidence: float
    framework_requirement: str          # L1 control_text from ecc_framework
    policy_evidence: str                # evidence_text from policy_ecc_assessments
    reason: str
    missing_requirements: list[str]
    recommended_fix: str
    source: dict                        # { chunk_id, page_number, section_title }
    control_type: Optional[str] = None
    domain_code: Optional[str] = None
    domain_name: Optional[str] = None
    subdomain_code: Optional[str] = None
    subdomain_name: Optional[str] = None
    assessed_at: Optional[str] = None


@router.get("/api/mapping-reviews/frameworks")
def list_frameworks_with_results(
    policy_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_get_current_user),
):
    """List the frameworks that have any analysis row for the given policy."""
    _check_policy_access(db, policy_id, current_user)
    rows = db.execute(sql_text("""
        SELECT DISTINCT framework_id
        FROM policy_ecc_assessments
        WHERE policy_id = CAST(:pid AS uuid)
    """), {"pid": policy_id}).fetchall()
    return [{"framework_id": r[0], "framework_name": r[0]} for r in rows]


@router.get("/api/mapping-reviews", response_model=List[MappingReviewItem])
def list_mapping_reviews(
    policy_id: str = Query(...),
    framework_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_get_current_user),
):
    """
    Return one explainability row per analysed control for the given policy.

    Source of truth is `policy_ecc_assessments` (written by both ECC-2 and
    SACS-002 analyzers). The framework requirement text and section labels
    come from `ecc_framework`.

    Status filter values: compliant | partial | non_compliant.
    """
    _check_policy_access(db, policy_id, current_user)

    where_parts = ["a.policy_id = CAST(:pid AS uuid)"]
    params = {"pid": policy_id}

    if framework_id:
        where_parts.append("a.framework_id = :fwid")
        params["fwid"] = framework_id

    if status_filter:
        normalized = _STATUS_FROM_DB.get(status_filter)
        if normalized is None:
            raise HTTPException(
                status_code=422,
                detail="status must be one of: compliant, partial, non_compliant.",
            )
        # The DB column uses lowercase compliance_status_enum values.
        where_parts.append("a.compliance_status::text = :st")
        params["st"] = normalized

    if min_confidence is not None:
        where_parts.append("COALESCE(a.confidence_score, 0) >= :mc")
        params["mc"] = float(min_confidence)

    where_sql = " AND ".join(where_parts)

    rows = db.execute(sql_text(f"""
        SELECT a.policy_id::text, a.framework_id, a.control_code,
               a.compliance_status::text AS status,
               a.evidence_text, a.gap_description, a.confidence_score,
               a.assessed_at,
               f.control_text, f.control_type,
               f.domain_code, f.domain_name,
               f.subdomain_code, f.subdomain_name
        FROM policy_ecc_assessments a
        LEFT JOIN ecc_framework f
          ON  f.framework_id = a.framework_id
          AND f.control_code = a.control_code
        WHERE {where_sql}
        ORDER BY a.framework_id, a.control_code
    """), params).fetchall()

    items: list[MappingReviewItem] = []
    for r in rows:
        status_norm = _STATUS_FROM_DB.get(r[3], r[3])
        evidence = (r[4] or "").strip()
        missing = _split_missing(r[5])
        confidence = float(r[6] or 0.0)
        section_title = r[13] or r[12] or ""  # subdomain_name or subdomain_code

        items.append(MappingReviewItem(
            policy_id=r[0],
            framework_id=r[1],
            framework_name=r[1],
            control_code=r[2],
            checkpoint_index=1,
            status=status_norm,
            confidence=round(confidence, 3),
            framework_requirement=r[8] or "",
            policy_evidence=evidence,
            reason=_build_reason(
                status_norm, confidence,
                has_evidence=bool(evidence and evidence != "No direct evidence found"),
                missing_count=len(missing),
            ),
            missing_requirements=missing,
            recommended_fix=_build_recommended_fix(
                r[2], r[8] or "", missing, status_norm,
            ),
            source={
                "chunk_id": None,
                "page_number": None,
                "section_title": section_title,
            },
            control_type=r[9],
            domain_code=r[10],
            domain_name=r[11],
            subdomain_code=r[12],
            subdomain_name=r[13],
            assessed_at=r[7].isoformat() if r[7] else None,
        ))
    return items


# ─── Policy Versions ─────────────────────────────────────────────────────────


class PolicyVersionSummary(BaseModel):
    id: str
    policy_id: str
    version_number: int
    version_type: str
    compliance_score: Optional[float]
    change_summary: Optional[str]
    created_by: Optional[str]
    created_at: Optional[str]
    has_content: bool


class PolicyVersionDetail(PolicyVersionSummary):
    content: str
    framework_id: Optional[str]
    target_framework_name: Optional[str]


class GenerateImprovedRequest(BaseModel):
    policy_id: str
    framework_id: Optional[str] = None       # None → improve against all analysed frameworks


class GenerateImprovedResponse(BaseModel):
    version_id: str
    policy_id: str
    version_number: int
    version_type: str
    framework_id: Optional[str]
    addressed_controls: list[str]
    estimated_improvement: float
    change_summary: str


def _get_full_policy_text(db: Session, policy_id: str) -> str:
    """Concatenate ordered policy_chunks; fall back to content_preview."""
    rows = db.execute(sql_text(
        "SELECT chunk_text FROM policy_chunks "
        "WHERE policy_id = :pid ORDER BY chunk_index"
    ), {"pid": policy_id}).fetchall()
    text = "\n\n".join(r[0] for r in rows if r[0])
    if text:
        return text
    preview = db.execute(sql_text(
        "SELECT content_preview FROM policies WHERE id = :pid"
    ), {"pid": policy_id}).fetchone()
    return (preview[0] or "") if preview else ""


def _latest_compliance_score(
    db: Session, policy_id: str, framework_id: Optional[str]
) -> Optional[float]:
    """Most recent compliance_score for this policy (optionally per-framework)."""
    if framework_id:
        row = db.execute(sql_text("""
            SELECT compliance_score FROM compliance_results
            WHERE policy_id = :pid AND framework_id = :fwid
            ORDER BY analyzed_at DESC LIMIT 1
        """), {"pid": policy_id, "fwid": framework_id}).fetchone()
    else:
        row = db.execute(sql_text("""
            SELECT compliance_score FROM compliance_results
            WHERE policy_id = :pid
            ORDER BY analyzed_at DESC LIMIT 1
        """), {"pid": policy_id}).fetchone()
    return float(row[0]) if row and row[0] is not None else None


@router.get("/api/policy-versions", response_model=List[PolicyVersionSummary])
def list_policy_versions(
    policy_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_get_current_user),
):
    _check_policy_access(db, policy_id, current_user)
    rows = db.execute(sql_text("""
        SELECT pv.id, pv.policy_id, pv.version_number, pv.version_type,
               pv.compliance_score, pv.change_summary, pv.created_by,
               pv.created_at,
               LENGTH(COALESCE(pv.content, '')) AS content_len
        FROM policy_versions pv
        WHERE pv.policy_id = :pid
        ORDER BY pv.version_number DESC
    """), {"pid": policy_id}).fetchall()
    return [
        PolicyVersionSummary(
            id=r[0],
            policy_id=r[1],
            version_number=int(r[2]),
            version_type=r[3],
            compliance_score=float(r[4]) if r[4] is not None else None,
            change_summary=r[5],
            created_by=str(r[6]) if r[6] else None,
            created_at=r[7].isoformat() if r[7] else None,
            has_content=bool(r[8] and int(r[8]) > 0),
        )
        for r in rows
    ]


@router.get("/api/policy-versions/{version_id}", response_model=PolicyVersionDetail)
def get_policy_version(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_get_current_user),
):
    row = db.execute(sql_text("""
        SELECT pv.id, pv.policy_id, pv.version_number, pv.version_type,
               pv.compliance_score, pv.change_summary, pv.created_by,
               pv.created_at, pv.content
        FROM policy_versions pv
        WHERE pv.id = :vid
    """), {"vid": version_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Version not found.")

    _check_policy_access(db, row[1], current_user)

    return PolicyVersionDetail(
        id=row[0],
        policy_id=row[1],
        version_number=int(row[2]),
        version_type=row[3],
        compliance_score=float(row[4]) if row[4] is not None else None,
        change_summary=row[5],
        created_by=str(row[6]) if row[6] else None,
        created_at=row[7].isoformat() if row[7] else None,
        has_content=bool(row[8]),
        content=row[8] or "",
        framework_id=None,
        target_framework_name=None,
    )


@router.post(
    "/api/policy-versions/generate",
    response_model=GenerateImprovedResponse,
)
def generate_improved_version(
    body: GenerateImprovedRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_get_current_user),
):
    """
    Build a new `ai_remediated` PolicyVersion that addresses every partial
    and non_compliant control in the latest analysis.

    Pipeline:
      1. Validate access + load policy text.
      2. Pull all (control_code, status, gap_description, control_text) rows
         from policy_ecc_assessments where status ∈ {partial, non_compliant}.
      3. Build a single consolidated missing-requirements list (with control
         codes) and call generate_remediation_draft once.
      4. Append the generated additive sections to the original policy text
         (the original policy file is NEVER modified).
      5. Persist as PolicyVersion(version_type='ai_remediated').
    """
    policy = _check_policy_access(db, body.policy_id, current_user)

    # 1. Original policy text. Refuse if empty — there is nothing to improve.
    policy_text = _get_full_policy_text(db, policy.id)
    if not policy_text.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "Policy has no extracted text yet. Re-upload the policy and "
                "run analysis first."
            ),
        )

    # 2. Pull failing controls. JOIN to ecc_framework so we have the
    # canonical requirement text alongside the assessor's gap_description.
    where_parts = [
        "a.policy_id = CAST(:pid AS uuid)",
        "a.compliance_status::text IN ('partial', 'non_compliant')",
    ]
    params = {"pid": policy.id}
    if body.framework_id:
        where_parts.append("a.framework_id = :fwid")
        params["fwid"] = body.framework_id

    rows = db.execute(sql_text(f"""
        SELECT a.framework_id, a.control_code, a.compliance_status::text,
               a.gap_description, a.evidence_text, a.confidence_score,
               f.control_text
        FROM policy_ecc_assessments a
        LEFT JOIN ecc_framework f
          ON f.framework_id = a.framework_id
          AND f.control_code = a.control_code
        WHERE {' AND '.join(where_parts)}
        ORDER BY a.framework_id, a.control_code
    """), params).fetchall()

    if not rows:
        raise HTTPException(
            status_code=422,
            detail=(
                "No partial or non-compliant controls found. Run an analysis "
                "first, or this policy is already compliant."
            ),
        )

    # 3. Consolidated missing-requirements list. Each entry is prefixed with
    # the control code so the AI's output is traceable per control. Cap total
    # length so the GPT prompt stays well under model context.
    missing_lines: list[str] = []
    addressed_controls: list[str] = []
    total_chars = 0
    MAX_CHARS = 8000     # ~2k tokens worth of missing requirements
    for r in rows:
        framework_id, control_code, status_db, gap, _ev, _conf, ctrl_text = r
        gap_parts = _split_missing(gap)
        if not gap_parts and ctrl_text:
            # Fallback: non_compliant rows often have no per-checkpoint gap
            # description, so use the L1 requirement text directly.
            gap_parts = [ctrl_text[:240]]
        if not gap_parts:
            continue
        for part in gap_parts:
            line = f"[{framework_id} {control_code}] {part}"
            if total_chars + len(line) > MAX_CHARS:
                break
            missing_lines.append(line)
            total_chars += len(line)
        addressed_controls.append(f"{framework_id} {control_code}")
        if total_chars >= MAX_CHARS:
            break

    if not missing_lines:
        raise HTTPException(
            status_code=422,
            detail="Could not derive any missing requirements from analysis.",
        )

    # Prefer a single descriptive framework label for the prompt context.
    framework_label = body.framework_id or rows[0][0]
    representative_control_code = rows[0][1]

    # 4. Single LLM call producing the consolidated additive text.
    try:
        draft = generate_remediation_draft(
            db=db,
            policy_id=policy.id,
            policy_text=policy_text,
            control={
                "framework_name": framework_label,
                "framework_id": None,            # null FK — multi-control draft
                "control_id": None,
                "control_code": representative_control_code,
                "control_title": "Multiple controls (consolidated remediation)",
            },
            ai_rationale=(
                f"Consolidated remediation for {len(addressed_controls)} "
                f"control(s) flagged partial or non-compliant in the latest "
                f"analysis."
            ),
            missing_checkpoints=missing_lines,
            mapping_review_id=None,
            created_by_id=str(current_user.id),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:                                 # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Improved-version generation failed: {type(e).__name__}: {e}",
        )

    # 5. Build the merged content and persist as a new PolicyVersion.
    # The original policy file on disk is never touched. The merged text is a
    # logical "appended" view: original text + clearly-marked AI section.
    merged_content = (
        f"{policy_text.rstrip()}\n\n"
        f"================================================================\n"
        f"AI-REMEDIATED ADDITIONS — generated {datetime.now(timezone.utc).date()}\n"
        f"Targets: {', '.join(addressed_controls[:20])}"
        f"{' …' if len(addressed_controls) > 20 else ''}\n"
        f"================================================================\n\n"
        f"{draft.suggested_policy_text}"
    )

    # Snapshot the original policy as version 1 if no original row exists yet —
    # otherwise the new version_number could collide and audit history would
    # have a gap.
    has_original = db.execute(sql_text(
        "SELECT 1 FROM policy_versions "
        "WHERE policy_id = :pid AND version_type = 'original' LIMIT 1"
    ), {"pid": policy.id}).fetchone()
    if not has_original:
        original_version = models.PolicyVersion(
            policy_id=policy.id,
            version_number=_next_version_number(db, policy.id),
            version_type="original",
            content=policy_text,
            compliance_score=_latest_compliance_score(db, policy.id, body.framework_id),
            remediation_draft_id=None,
            change_summary="Original upload (auto-snapshot before AI remediation).",
            created_by=current_user.id,
        )
        db.add(original_version)
        db.flush()

    old_score = _latest_compliance_score(db, policy.id, body.framework_id) or 0.0
    estimated_improvement = round(
        min(100.0, old_score + 10.0 * (len(addressed_controls) ** 0.5)),
        1,
    )
    change_summary = (
        f"AI-remediated version addressing {len(addressed_controls)} "
        f"control(s) flagged partial or non-compliant. "
        f"Estimated post-remediation score (subject to re-analysis): "
        f"{estimated_improvement}% (was {round(old_score, 1)}%)."
    )

    new_version = models.PolicyVersion(
        policy_id=policy.id,
        version_number=_next_version_number(db, policy.id),
        version_type="ai_remediated",
        content=merged_content,
        compliance_score=estimated_improvement,
        remediation_draft_id=draft.id,
        change_summary=change_summary,
        created_by=current_user.id,
    )
    db.add(new_version)

    try:
        db.commit()
        db.refresh(new_version)
    except Exception as e:                                 # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Persist failed: {e}")

    return GenerateImprovedResponse(
        version_id=new_version.id,
        policy_id=policy.id,
        version_number=new_version.version_number,
        version_type=new_version.version_type,
        framework_id=body.framework_id,
        addressed_controls=addressed_controls,
        estimated_improvement=estimated_improvement,
        change_summary=change_summary,
    )


# ─── PDF download for a version ──────────────────────────────────────────────


def _load_version_for_user(
    db: Session,
    policy_id: str,
    version_id: str,
    user: models.User,
) -> tuple[models.Policy, models.PolicyVersion]:
    """Validate path params + access, return the policy and version rows."""
    policy = _check_policy_access(db, policy_id, user)
    version = (
        db.query(models.PolicyVersion)
        .filter(models.PolicyVersion.id == version_id)
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Version not found.")
    if version.policy_id != policy.id:
        raise HTTPException(
            status_code=400,
            detail="Version does not belong to this policy.",
        )
    return policy, version


@router.get("/api/policies/{policy_id}/versions/{version_id}/download/pdf")
def download_version_pdf(
    policy_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_get_current_user),
):
    """
    Stream a PDF rendering of a stored PolicyVersion.

    Filename pattern matches the spec: ai_remediated_policy_v{N}.pdf for
    AI-remediated versions, otherwise policy_v{N}_{type}.pdf.
    """
    policy, version = _load_version_for_user(db, policy_id, version_id, current_user)

    if not version.content or not version.content.strip():
        raise HTTPException(
            status_code=422,
            detail="This version has no content to render.",
        )

    try:
        pdf_bytes = build_policy_version_pdf(
            content=version.content,
            policy_name=policy.file_name or "Policy Document",
            version_number=version.version_number,
            version_type=version.version_type,
            change_summary=version.change_summary,
            compliance_score=version.compliance_score,
        )
    except Exception as e:                                 # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {type(e).__name__}: {e}",
        )

    if version.version_type == "ai_remediated":
        filename = f"ai_remediated_policy_v{version.version_number}.pdf"
    else:
        filename = f"policy_v{version.version_number}_{version.version_type}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


# ─── Re-analyze a stored version ─────────────────────────────────────────────


class ReanalyzeRequest(BaseModel):
    # Optional override; if omitted the endpoint reuses whichever frameworks
    # the policy was last analysed against (or both ECC-2 + SACS-002 as a
    # default for a never-analysed policy).
    frameworks: Optional[List[str]] = None


class FrameworkSummary(BaseModel):
    framework_id: str
    score: float
    compliant: int
    partial: int
    non_compliant: int


class ReanalyzeResponse(BaseModel):
    policy_id: str
    version_id: str
    version_number: int
    overall_score: float
    previous_score: Optional[float]
    delta: Optional[float]
    frameworks: List[FrameworkSummary]
    duration_seconds: float


def _frameworks_previously_used(db: Session, policy_id: str) -> list[str]:
    """Distinct framework_ids found in policy_ecc_assessments for the policy."""
    rows = db.execute(sql_text("""
        SELECT DISTINCT framework_id
        FROM policy_ecc_assessments
        WHERE policy_id = CAST(:pid AS uuid)
    """), {"pid": policy_id}).fetchall()
    return [r[0] for r in rows]


@router.post(
    "/api/policies/{policy_id}/versions/{version_id}/reanalyze",
    response_model=ReanalyzeResponse,
)
async def reanalyze_version(
    policy_id: str,
    version_id: str,
    body: ReanalyzeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_get_current_user),
):
    """
    Re-run compliance analysis using the **stored version content** as the
    policy text, leaving the original uploaded file untouched.

    Pipeline:
      1. Load the version, verify ownership and that it has content.
      2. Determine which frameworks to analyse against:
           - body.frameworks if provided
           - else distinct frameworks found in policy_ecc_assessments for
             this policy (i.e. whatever it was previously analysed against)
           - else default to ECC-2:2024 + SACS-002.
      3. Wipe stale analysis rows for this policy and replace policy_chunks
         with chunks of the version's content (the analyzers read from
         policy_chunks, not from a parameter).
      4. Run the appropriate analyzers in sequence.
      5. Persist the new overall score back onto the version row so
         subsequent listings show the post-remediation score.
    """
    import time

    from backend.chunker import chunk_text
    from backend.ecc2_analyzer import run_ecc2_analysis
    from backend.sacs002_analyzer import run_sacs002_analysis
    from backend.vector_store import (
        delete_policy_chunks,
        get_embeddings,
        store_chunks_with_embeddings,
    )

    policy, version = _load_version_for_user(db, policy_id, version_id, current_user)

    content = (version.content or "").strip()
    if not content:
        raise HTTPException(
            status_code=422,
            detail="Cannot re-analyse: this version has no content.",
        )

    # Resolve target frameworks. Lower-priority defaults preserve the user's
    # intent without surfacing a UI question.
    if body.frameworks:
        frameworks = list(body.frameworks)
    else:
        frameworks = _frameworks_previously_used(db, policy.id)
    if not frameworks:
        frameworks = ["ECC-2:2024", "SACS-002"]

    previous_score = _latest_compliance_score(db, policy.id, None)

    # ── Stale-row cleanup. Mirrors the wipe inside /api/functions/analyze_policy
    # so the UI shows clean post-remediation findings rather than a mix.
    try:
        db.query(models.AIInsight).filter(
            models.AIInsight.policy_id == policy.id
        ).delete()
        db.query(models.Gap).filter(
            models.Gap.policy_id == policy.id
        ).delete()
        db.query(models.MappingReview).filter(
            models.MappingReview.policy_id == policy.id
        ).delete()
        db.query(models.ComplianceResult).filter(
            models.ComplianceResult.policy_id == policy.id
        ).delete()
        # policy_ecc_assessments uses the same UNIQUE (policy_id, control_code)
        # ON CONFLICT semantics, so analyzers will overwrite rows. We still
        # delete them here so the count is accurate even if a control no
        # longer maps to the new content.
        db.execute(sql_text(
            "DELETE FROM policy_ecc_assessments WHERE policy_id = CAST(:pid AS uuid)"
        ), {"pid": policy.id})
        db.commit()
    except Exception as e:                                 # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear previous analysis rows: {e}",
        )

    # ── Replace policy_chunks with chunks of the version content. The
    # analyzers read from this table, so this is what feeds them the
    # remediated text without modifying the original uploaded file.
    try:
        delete_policy_chunks(db, policy.id)
        chunks = chunk_text(content)
        if not chunks:
            raise HTTPException(
                status_code=422,
                detail="Version content could not be chunked.",
            )
        embeddings = await get_embeddings([c["text"] for c in chunks])
        store_chunks_with_embeddings(db, policy.id, chunks, embeddings)
    except HTTPException:
        raise
    except Exception as e:                                 # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to embed version content: {type(e).__name__}: {e}",
        )

    t0 = time.time()
    fw_summaries: list[FrameworkSummary] = []

    try:
        if "ECC-2:2024" in frameworks:
            res = await run_ecc2_analysis(db, policy.id, progress_cb=None)
            payload = res.get("ECC-2:2024") or {}
            if "error" in payload:
                raise HTTPException(status_code=503, detail=payload["error"])
            fw_summaries.append(FrameworkSummary(
                framework_id="ECC-2:2024",
                score=float(payload.get("score") or 0.0),
                compliant=int(payload.get("compliant") or 0),
                partial=int(payload.get("partial") or 0),
                non_compliant=int(payload.get("non_compliant") or 0),
            ))
        if "SACS-002" in frameworks:
            res = await run_sacs002_analysis(db, policy.id, progress_cb=None)
            payload = res.get("SACS-002") or {}
            if "error" in payload:
                raise HTTPException(status_code=503, detail=payload["error"])
            fw_summaries.append(FrameworkSummary(
                framework_id="SACS-002",
                score=float(payload.get("compliance_score") or 0.0),
                compliant=int(payload.get("compliant") or 0),
                partial=int(payload.get("partial") or 0),
                non_compliant=int(payload.get("non_compliant") or 0),
            ))
    except HTTPException:
        raise
    except Exception as e:                                 # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Re-analysis failed: {type(e).__name__}: {e}",
        )

    duration = round(time.time() - t0, 1)

    # Overall score = average of the framework scores we ran (matches the
    # convention used by the rest of the UI when multiple frameworks are
    # active for one policy).
    overall_score = (
        round(sum(f.score for f in fw_summaries) / len(fw_summaries), 1)
        if fw_summaries
        else 0.0
    )

    # Persist the new score back onto the version so the version-history
    # list shows the validated, post-remediation number.
    try:
        version.compliance_score = overall_score
        db.execute(sql_text(
            "UPDATE policies SET status='analyzed', last_analyzed_at=:ts "
            "WHERE id = :pid"
        ), {"ts": datetime.now(timezone.utc), "pid": policy.id})
        db.commit()
    except Exception:
        db.rollback()

    delta = (
        round(overall_score - previous_score, 1)
        if previous_score is not None
        else None
    )

    return ReanalyzeResponse(
        policy_id=policy.id,
        version_id=version.id,
        version_number=version.version_number,
        overall_score=overall_score,
        previous_score=round(previous_score, 1) if previous_score is not None else None,
        delta=delta,
        frameworks=fw_summaries,
        duration_seconds=duration,
    )
