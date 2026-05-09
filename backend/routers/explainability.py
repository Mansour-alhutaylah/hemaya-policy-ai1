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
from backend.database import get_db, set_user_context
from backend.pdf_export import build_policy_version_pdf
from backend.remediation_engine import (
    _next_version_number,
    _strip_metadata_block,
    generate_remediation_draft,
    generate_improved_policy_text_async,
)
from backend.security import is_admin


router = APIRouter(tags=["explainability"])

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
    # Phase 13: activate per-request RLS context. The other authenticated
    # entry points (main.get_current_user, remediation, reports_export)
    # already do this; explainability was the gap.
    set_user_context(db, user.id)
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
    if not is_admin(user) and str(policy.owner_id) != str(user.id):
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

    # Phase 11 source attribution (chunk_id, page_number, paragraph_index)
    # is already written to policy_ecc_assessments by the analyzers; we now
    # surface it on the API so the UI can render "[Page N · Para M]" chips.
    rows = db.execute(sql_text(f"""
        SELECT a.policy_id::text, a.framework_id, a.control_code,
               a.compliance_status::text AS status,
               a.evidence_text, a.gap_description, a.confidence_score,
               a.assessed_at,
               f.control_text, f.control_type,
               f.domain_code, f.domain_name,
               f.subdomain_code, f.subdomain_name,
               a.chunk_id, a.page_number, a.paragraph_index
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
                "chunk_id":        r[14],
                "page_number":     r[15],
                "paragraph_index": r[16],
                "section_title":   section_title,
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
    # Real scores from incremental re-analysis
    original_score: float
    new_score: float
    improvement_delta: float
    total_targeted: int
    fixed_controls: int
    still_partial: int
    still_non_compliant: int
    remediation_score: float       # fixed / targeted × 100
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
async def generate_improved_version(
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

    import hashlib
    from backend.chunker import chunk_text
    from backend.ecc2_analyzer import run_ecc2_analysis
    from backend.sacs002_analyzer import run_sacs002_analysis
    from backend.vector_store import (
        delete_policy_chunks, get_embeddings, store_chunks_with_embeddings,
    )
    # 3. Build per-control list for the prompt and for tracking.
    addressed_controls: list[str] = []
    failing_controls_for_prompt: list[dict] = []
    MAX_CONTROLS = 40   # cap so the prompt stays within model context
    for r in rows[:MAX_CONTROLS]:
        framework_id_r, control_code, status_db, gap, _ev, _conf, ctrl_text = r
        gap_parts = _split_missing(gap)
        addressed_controls.append(f"{framework_id_r} {control_code}")
        failing_controls_for_prompt.append({
            "framework_id":       framework_id_r,
            "control_code":       control_code,
            "control_text":       ctrl_text or "",
            "gap_description":    gap or "",
            "missing_requirements": gap_parts or ([ctrl_text[:200]] if ctrl_text else []),
        })

    if not failing_controls_for_prompt:
        raise HTTPException(422, "Could not derive any missing requirements from analysis.")

    print(f"[GENERATE] policy_id={policy.id} targeted={len(failing_controls_for_prompt)} controls")
    print(f"[GENERATE] Targets: {addressed_controls}")

    # ── 4. Capture baseline before touching any rows ───────────────────────
    frameworks_used = list({r[0] for r in rows})
    target_codes_by_fw: dict[str, set] = {}
    baseline_by_fw: dict[str, dict] = {}

    for fw in frameworks_used:
        target_codes_by_fw[fw] = {r[1] for r in rows if r[0] == fw}

    for fw in frameworks_used:
        brows = db.execute(sql_text("""
            SELECT compliance_status::text, COUNT(*)
            FROM policy_ecc_assessments
            WHERE policy_id = CAST(:pid AS uuid) AND framework_id = :fw
            GROUP BY compliance_status
        """), {"pid": policy.id, "fw": fw}).fetchall()
        c = {r[0]: int(r[1]) for r in brows}
        comp = c.get("compliant", 0)
        part = c.get("partial", 0)
        non_c = c.get("non_compliant", 0)
        total = comp + part + non_c
        baseline_by_fw[fw] = {
            "total": total, "compliant": comp, "partial": part,
            "non_compliant": non_c,
            "score": round(((comp + part * 0.5) / total * 100), 1) if total else 0.0,
        }

    original_score = (
        round(sum(v["score"] for v in baseline_by_fw.values()) / len(baseline_by_fw), 1)
        if baseline_by_fw else 0.0
    )
    original_hash = hashlib.sha256(policy_text.encode("utf-8")).hexdigest()[:16]
    print(f"[GENERATE] Original hash={original_hash} len={len(policy_text)}")

    # ── 5. Generate improved policy text via ASYNC LLM call ───────────────
    # Uses generate_improved_policy_text_async — fully async, NO db access,
    # NO asyncio.to_thread. This avoids the SQLAlchemy thread-safety bug.
    try:
        ai_text = await generate_improved_policy_text_async(
            policy_text=policy_text,
            failing_controls=failing_controls_for_prompt,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:                                 # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"AI policy generation failed: {type(e).__name__}: {e}",
        )

    ai_text_clean = _strip_metadata_block(ai_text)
    print(f"[GENERATE] AI generated {len(ai_text_clean)} chars of remediation text")

    # ── 6. Build merged content + hash safeguard ───────────────────────────
    merged_content = (
        f"{policy_text.rstrip()}\n\n"
        f"================================================================\n"
        f"AI-REMEDIATED ADDITIONS — {datetime.now(timezone.utc).date()}\n"
        f"Targets: {', '.join(addressed_controls[:20])}"
        f"{' …' if len(addressed_controls) > 20 else ''}\n"
        f"================================================================\n\n"
        f"{ai_text_clean}"
    )
    merged_hash = hashlib.sha256(merged_content.encode("utf-8")).hexdigest()[:16]
    print(f"[GENERATE] Merged hash={merged_hash} len={len(merged_content)}")

    if original_hash == merged_hash:
        raise HTTPException(
            status_code=422,
            detail=(
                "Improved policy content is identical to original. "
                "Remediation generation produced no new text."
            ),
        )
    if len(ai_text_clean) < 200:
        raise HTTPException(
            status_code=422,
            detail=(
                f"AI generated only {len(ai_text_clean)} chars — too short to be a valid "
                "remediation. Check the OpenAI response."
            ),
        )

    # ── 7. Snapshot original version if missing ────────────────────────────
    has_original = db.execute(sql_text(
        "SELECT 1 FROM policy_versions "
        "WHERE policy_id = :pid AND version_type = 'original' LIMIT 1"
    ), {"pid": policy.id}).fetchone()
    if not has_original:
        db.add(models.PolicyVersion(
            policy_id=policy.id,
            version_number=_next_version_number(db, policy.id),
            version_type="original",
            content=policy_text,
            compliance_score=original_score,
            remediation_draft_id=None,
            change_summary="Original upload (auto-snapshot before AI remediation).",
            created_by=current_user.id,
        ))
        db.flush()

    # ── 8. Persist the new ai_remediated version ───────────────────────────
    new_version = models.PolicyVersion(
        policy_id=policy.id,
        version_number=_next_version_number(db, policy.id),
        version_type="ai_remediated",
        content=merged_content,
        compliance_score=None,    # will be set after real re-analysis below
        remediation_draft_id=None,
        change_summary=(
            f"AI-remediated version addressing {len(addressed_controls)} control(s). "
            f"Original score: {original_score}% — re-analysis in progress."
        ),
        created_by=current_user.id,
    )
    db.add(new_version)
    try:
        db.commit()
        db.refresh(new_version)
    except Exception as e:                                 # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Persist failed: {e}")

    # ── 9. Incremental re-analysis on targeted controls only ───────────────
    # Delete partial/non-compliant rows so the analyzers write fresh results.
    try:
        for fw, codes in target_codes_by_fw.items():
            if codes:
                db.execute(sql_text(
                    "DELETE FROM policy_ecc_assessments "
                    "WHERE policy_id = CAST(:pid AS uuid) "
                    "AND framework_id = :fw "
                    "AND compliance_status IN ('non_compliant', 'partial')"
                ), {"pid": policy.id, "fw": fw})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Failed to prepare re-analysis rows: {e}")

    # Embed improved content linked to the specific version (not just policy_id).
    # This isolates improved chunks so the analyzer can never accidentally read
    # original policy chunks even if something else modifies the shared space.
    version_id_str = str(new_version.id)
    try:
        # Delete any previous chunks for THIS version (idempotent re-run safety).
        delete_policy_chunks(db, policy.id, policy_version_id=version_id_str)
        chunks = chunk_text(merged_content)
        if not chunks:
            raise HTTPException(422, "Merged content could not be chunked.")
        embeddings = await get_embeddings([c["text"] for c in chunks])
        # store_chunks_with_embeddings already calls db.commit() internally.
        store_chunks_with_embeddings(
            db, policy.id, chunks, embeddings,
            policy_version_id=version_id_str,
        )
        print(f"[GENERATE] version={version_id_str} "
              f"stored {len(chunks)} chunks hash={merged_hash}")
    except HTTPException:
        raise
    except Exception as e:                                 # noqa: BLE001
        db.rollback()
        raise HTTPException(500, f"Failed to embed improved content: {type(e).__name__}: {e}")

    try:
        for fw, codes in target_codes_by_fw.items():
            target = codes or None
            if fw == "ECC-2:2024":
                await run_ecc2_analysis(
                    db, policy.id,
                    progress_cb=None,
                    control_codes=target,
                    policy_version_id=version_id_str,
                )
            elif fw == "SACS-002":
                await run_sacs002_analysis(
                    db, policy.id,
                    progress_cb=None,
                    control_codes=target,
                    policy_version_id=version_id_str,
                )
    except Exception as e:                                 # noqa: BLE001
        raise HTTPException(503, f"Re-analysis failed: {type(e).__name__}: {e}")

    # ── 10. Compute real before/after scores ───────────────────────────────
    total_targeted = sum(len(c) for c in target_codes_by_fw.values())
    total_fixed = 0
    total_still_partial = 0
    total_still_nc = 0
    new_fw_scores: list[float] = []

    for fw, baseline in baseline_by_fw.items():
        codes = target_codes_by_fw.get(fw, set())
        outcome_rows = db.execute(sql_text("""
            SELECT control_code, compliance_status::text
            FROM policy_ecc_assessments
            WHERE policy_id = CAST(:pid AS uuid) AND framework_id = :fw
        """), {"pid": policy.id, "fw": fw}).fetchall()
        status_map = {r[0]: r[1] for r in outcome_rows}

        fixed      = sum(1 for cc in codes if status_map.get(cc) == "compliant")
        still_part = sum(1 for cc in codes if status_map.get(cc) == "partial")
        still_nc   = sum(1 for cc in codes if status_map.get(cc) == "non_compliant")
        total_fixed         += fixed
        total_still_partial += still_part
        total_still_nc      += still_nc

        new_comp  = baseline["compliant"] + fixed
        new_part  = still_part
        total     = baseline["total"]
        new_fw_scores.append(
            round(((new_comp + new_part * 0.5) / total * 100), 1) if total else 0.0
        )

    new_score = round(sum(new_fw_scores) / len(new_fw_scores), 1) if new_fw_scores else original_score
    improvement_delta = round(new_score - original_score, 1)
    rem_score = round(total_fixed / total_targeted * 100, 1) if total_targeted else 0.0

    # ── 11. Persist final scores ───────────────────────────────────────────
    change_summary = (
        f"AI-remediated version: {total_fixed}/{total_targeted} targeted controls fixed. "
        f"Score: {original_score}% → {new_score}% ({'+' if improvement_delta >= 0 else ''}{improvement_delta}%)."
    )
    try:
        new_version.compliance_score = new_score
        new_version.change_summary   = change_summary
        db.execute(sql_text(
            "UPDATE policies SET status='analyzed', last_analyzed_at=:ts WHERE id=:pid"
        ), {"ts": datetime.now(timezone.utc), "pid": policy.id})
        # Update compliance_results with the correct blended score
        for fw, baseline in baseline_by_fw.items():
            codes = target_codes_by_fw.get(fw, set())
            outcome_rows = db.execute(sql_text("""
                SELECT control_code, compliance_status::text
                FROM policy_ecc_assessments
                WHERE policy_id = CAST(:pid AS uuid) AND framework_id = :fw
            """), {"pid": policy.id, "fw": fw}).fetchall()
            status_map = {r[0]: r[1] for r in outcome_rows}
            fixed     = sum(1 for cc in codes if status_map.get(cc) == "compliant")
            still_p   = sum(1 for cc in codes if status_map.get(cc) == "partial")
            still_n   = sum(1 for cc in codes if status_map.get(cc) == "non_compliant")
            new_comp  = baseline["compliant"] + fixed
            total     = baseline["total"]
            fw_score  = round(((new_comp + still_p * 0.5) / total * 100), 1) if total else 0.0
            db.execute(sql_text("""
                UPDATE compliance_results
                SET compliance_score = :sc,
                    controls_covered = :cov,
                    controls_partial = :par,
                    controls_missing = :mis,
                    analyzed_at      = :ts
                WHERE policy_id   = :pid
                  AND framework_id = (SELECT id FROM frameworks WHERE name = :fw LIMIT 1)
            """), {
                "pid": policy.id, "fw": fw, "sc": fw_score,
                "cov": new_comp, "par": still_p, "mis": still_n,
                "ts": datetime.now(timezone.utc),
            })
        db.commit()
    except Exception:
        db.rollback()

    return GenerateImprovedResponse(
        version_id=new_version.id,
        policy_id=policy.id,
        version_number=new_version.version_number,
        version_type=new_version.version_type,
        framework_id=body.framework_id,
        addressed_controls=addressed_controls,
        original_score=original_score,
        new_score=new_score,
        improvement_delta=improvement_delta,
        total_targeted=total_targeted,
        fixed_controls=total_fixed,
        still_partial=total_still_partial,
        still_non_compliant=total_still_nc,
        remediation_score=rem_score,
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


class FrameworkRemediationSummary(BaseModel):
    framework_id: str
    # Original full-analysis baseline
    total_controls: int
    original_compliant: int
    original_partial: int
    original_non_compliant: int
    original_score: float
    # What was targeted (partial + non_compliant before)
    targeted_controls: int
    # Outcomes for targeted controls after re-analysis
    fixed_controls: int        # targeted → now compliant
    still_partial: int         # targeted → still partial
    still_non_compliant: int   # targeted → still non_compliant
    remediation_score: float   # fixed / targeted × 100
    # New overall (baseline compliant + fixed, weighted with still_partial)
    new_compliant: int
    new_partial: int
    new_non_compliant: int
    new_score: float           # weighted: (new_compliant + new_partial×0.5) / total × 100


class ReanalyzeResponse(BaseModel):
    policy_id: str
    version_id: str
    version_number: int
    # Overall compliance scores (based on full control set)
    original_overall_score: float
    new_overall_score: float
    overall_delta: float
    # Aggregate remediation stats
    total_controls: int
    targeted_controls: int     # partial + non_compliant before
    fixed_controls: int        # of targeted, now compliant
    still_partial: int
    still_non_compliant: int
    remediation_score: float   # fixed / targeted × 100
    # Per-framework detail
    frameworks: List[FrameworkRemediationSummary]
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

    # ── 1. Capture baseline counts from policy_ecc_assessments ───────────
    baseline_by_fw: dict[str, dict] = {}
    for fw in frameworks:
        rows = db.execute(sql_text("""
            SELECT compliance_status::text, COUNT(*)
            FROM policy_ecc_assessments
            WHERE policy_id = CAST(:pid AS uuid) AND framework_id = :fw
            GROUP BY compliance_status
        """), {"pid": policy.id, "fw": fw}).fetchall()
        c = {r[0]: int(r[1]) for r in rows}
        comp  = c.get("compliant", 0)
        part  = c.get("partial", 0)
        non_c = c.get("non_compliant", 0)
        total = comp + part + non_c
        baseline_by_fw[fw] = {
            "total": total,
            "compliant": comp,
            "partial": part,
            "non_compliant": non_c,
            "score": round(((comp + part * 0.5) / total * 100), 1) if total else 0.0,
        }

    # ── 2. Identify targeted control codes (partial + non_compliant only) ─
    target_codes_by_fw: dict[str, set] = {}
    for fw in frameworks:
        rows = db.execute(sql_text("""
            SELECT control_code
            FROM policy_ecc_assessments
            WHERE policy_id = CAST(:pid AS uuid) AND framework_id = :fw
              AND compliance_status IN ('non_compliant', 'partial')
        """), {"pid": policy.id, "fw": fw}).fetchall()
        target_codes_by_fw[fw] = {r[0] for r in rows}

    # ── 3. Stale-row cleanup (keep compliant rows intact) ─────────────────
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
        # Only delete targeted (partial + non_compliant) rows per framework.
        # Compliant rows are preserved so the overall score cannot regress.
        for fw, codes in target_codes_by_fw.items():
            if codes:
                db.execute(sql_text(
                    "DELETE FROM policy_ecc_assessments "
                    "WHERE policy_id = CAST(:pid AS uuid) "
                    "AND framework_id = :fw "
                    "AND compliance_status IN ('non_compliant', 'partial')"
                ), {"pid": policy.id, "fw": fw})
        db.commit()
    except Exception as e:                                 # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear previous analysis rows: {e}",
        )

    # ── 4. Re-embed version content (version-scoped) ──────────────────────
    reanalyze_version_id = str(version.id)
    try:
        # Delete only THIS version's chunks; other versions are unaffected.
        delete_policy_chunks(db, policy.id, policy_version_id=reanalyze_version_id)
        chunks = chunk_text(content)
        if not chunks:
            raise HTTPException(
                status_code=422,
                detail="Version content could not be chunked.",
            )
        import hashlib as _hl
        content_hash = _hl.sha256(content.encode("utf-8")).hexdigest()[:16]
        print(f"  [REANALYZE] version={reanalyze_version_id} "
              f"content_hash={content_hash} len={len(content)}")
        embeddings = await get_embeddings([c["text"] for c in chunks])
        # store_chunks_with_embeddings already commits internally.
        store_chunks_with_embeddings(
            db, policy.id, chunks, embeddings,
            policy_version_id=reanalyze_version_id,
        )
        print(f"  [REANALYZE] Stored {len(chunks)} version-scoped chunks")
    except HTTPException:
        raise
    except Exception as e:                                 # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to embed version content: {type(e).__name__}: {e}",
        )

    # ── 5. Re-analyze only targeted controls ──────────────────────────────
    t0 = time.time()
    try:
        if "ECC-2:2024" in frameworks:
            target = target_codes_by_fw.get("ECC-2:2024") or None
            res = await run_ecc2_analysis(
                db, policy.id, progress_cb=None,
                control_codes=target,
                policy_version_id=reanalyze_version_id,
            )
            payload = res.get("ECC-2:2024") or {}
            if "error" in payload:
                raise HTTPException(status_code=503, detail=payload["error"])
        if "SACS-002" in frameworks:
            target = target_codes_by_fw.get("SACS-002") or None
            res = await run_sacs002_analysis(
                db, policy.id, progress_cb=None,
                control_codes=target,
                policy_version_id=reanalyze_version_id,
            )
            payload = res.get("SACS-002") or {}
            if "error" in payload:
                raise HTTPException(status_code=503, detail=payload["error"])
    except HTTPException:
        raise
    except Exception as e:                                 # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Re-analysis failed: {type(e).__name__}: {e}",
        )

    duration = round(time.time() - t0, 1)

    # ── 6. Compute per-framework remediation stats + new overall score ────
    fw_summaries: list[FrameworkRemediationSummary] = []

    for fw in frameworks:
        baseline     = baseline_by_fw.get(fw, {"total": 0, "compliant": 0, "partial": 0, "non_compliant": 0, "score": 0.0})
        target_codes = target_codes_by_fw.get(fw, set())

        # Query all current rows for this framework (preserved + newly analyzed)
        all_rows = db.execute(sql_text("""
            SELECT control_code, compliance_status::text
            FROM policy_ecc_assessments
            WHERE policy_id = CAST(:pid AS uuid) AND framework_id = :fw
        """), {"pid": policy.id, "fw": fw}).fetchall()
        status_map = {r[0]: r[1] for r in all_rows}

        # What happened to the targeted controls?
        fixed      = sum(1 for cc in target_codes if status_map.get(cc) == "compliant")
        still_part = sum(1 for cc in target_codes if status_map.get(cc) == "partial")
        still_nc   = sum(1 for cc in target_codes if status_map.get(cc) == "non_compliant")
        n_targeted = len(target_codes)
        rem_score  = round(fixed / n_targeted * 100, 1) if n_targeted else 0.0

        # New overall: preserved compliant + newly fixed, blended with remaining partial
        total     = baseline["total"]
        new_comp  = baseline["compliant"] + fixed
        new_part  = still_part
        new_nc    = still_nc
        new_score = round(((new_comp + new_part * 0.5) / total * 100), 1) if total else 0.0

        fw_summaries.append(FrameworkRemediationSummary(
            framework_id=fw,
            total_controls=total,
            original_compliant=baseline["compliant"],
            original_partial=baseline["partial"],
            original_non_compliant=baseline["non_compliant"],
            original_score=baseline["score"],
            targeted_controls=n_targeted,
            fixed_controls=fixed,
            still_partial=still_part,
            still_non_compliant=still_nc,
            remediation_score=rem_score,
            new_compliant=new_comp,
            new_partial=new_part,
            new_non_compliant=new_nc,
            new_score=new_score,
        ))

    # Aggregate across all frameworks
    total_controls    = sum(f.total_controls for f in fw_summaries)
    targeted_controls = sum(f.targeted_controls for f in fw_summaries)
    fixed_controls    = sum(f.fixed_controls for f in fw_summaries)
    still_partial     = sum(f.still_partial for f in fw_summaries)
    still_nc          = sum(f.still_non_compliant for f in fw_summaries)
    rem_score         = round(fixed_controls / targeted_controls * 100, 1) if targeted_controls else 0.0

    original_overall = (
        round(sum(f.original_score for f in fw_summaries) / len(fw_summaries), 1)
        if fw_summaries else 0.0
    )
    new_overall = (
        round(sum(f.new_score for f in fw_summaries) / len(fw_summaries), 1)
        if fw_summaries else 0.0
    )
    overall_delta = round(new_overall - original_overall, 1)

    # ── 7. Persist the correct blended score everywhere ──────────────────
    try:
        # Version row — shown in version history list
        version.compliance_score = new_overall

        # Policy row — status + timestamp
        db.execute(sql_text(
            "UPDATE policies SET status='analyzed', last_analyzed_at=:ts "
            "WHERE id = :pid"
        ), {"ts": datetime.now(timezone.utc), "pid": policy.id})

        # compliance_results — what the Analyses page reads.
        # The analyzer wrote partial-only scores; overwrite with the correct
        # blended score for each framework.
        for fw_sum in fw_summaries:
            db.execute(sql_text("""
                UPDATE compliance_results
                SET compliance_score  = :sc,
                    controls_covered  = :cov,
                    controls_partial  = :par,
                    controls_missing  = :mis,
                    analyzed_at       = :ts
                WHERE policy_id   = :pid
                  AND framework_id = (
                      SELECT id FROM frameworks WHERE name = :fw LIMIT 1
                  )
            """), {
                "pid": policy.id,
                "fw":  fw_sum.framework_id,
                "sc":  fw_sum.new_score,
                "cov": fw_sum.new_compliant,
                "par": fw_sum.new_partial,
                "mis": fw_sum.new_non_compliant,
                "ts":  datetime.now(timezone.utc),
            })

        db.commit()
    except Exception:
        db.rollback()

    return ReanalyzeResponse(
        policy_id=policy.id,
        version_id=version.id,
        version_number=version.version_number,
        original_overall_score=original_overall,
        new_overall_score=new_overall,
        overall_delta=overall_delta,
        total_controls=total_controls,
        targeted_controls=targeted_controls,
        fixed_controls=fixed_controls,
        still_partial=still_partial,
        still_non_compliant=still_nc,
        remediation_score=rem_score,
        frameworks=fw_summaries,
        duration_seconds=duration,
    )
