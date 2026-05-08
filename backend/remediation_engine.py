"""
remediation_engine.py

Generates AI-drafted policy ADDITIONS for specific compliance gaps.
The engine is intentionally additive-only: it produces the minimal new
sections required to achieve compliance and never rewrites existing content.
"""
import json
import os
import re
from typing import Optional

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend import models

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_MODEL = "gpt-4o-mini"

# ── Prompts ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an enterprise compliance policy writer. Your only job is to draft the
specific policy sections that are MISSING from an existing policy document.

HARD RULES — violating any rule makes your output unusable:
1. Generate ONLY the new text that needs to be appended to the existing policy.
2. Do NOT reproduce, paraphrase, or summarise any content already in the policy.
3. Do NOT write a preamble, executive summary, or full-policy rewrite.
4. Every sentence you write must directly address one of the listed missing requirements.
5. Use formal policy language: imperative mood, numbered sections and sub-sections
   (e.g. "3. Incident Response" → "3.1 Detection and Reporting").
6. After the policy text, append a single JSON block delimited by ```json … ``` with:
   {
     "section_headers": ["<top-level title 1>", ...],
     "requirements_addressed": ["<requirement text or ID>", ...]
   }
"""

_USER_TEMPLATE = """\
=== EXISTING POLICY (read-only — do NOT reproduce this) ===
{policy_excerpt}
=== END OF EXISTING POLICY ===

CONTROL BEING REMEDIATED
  Framework : {framework_name}
  Control   : {control_code} — {control_title}

WHY THE GAP EXISTS (AI rationale)
{ai_rationale}

MISSING REQUIREMENTS — write policy text for THESE ONLY:
{missing_block}

OUTPUT INSTRUCTIONS
Write only the new policy sections that fill the above gaps.
Do not include anything already covered by the existing policy shown above.
"""

# ── Internal helpers ──────────────────────────────────────────────────────────

def _call_openai(messages: list[dict]) -> str:
    payload = {
        "model": _MODEL,
        "messages": messages,
        "temperature": 0.2,   # low → deterministic, formal language
        "max_tokens": 2048,
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(_OPENAI_URL, headers=headers, json=payload)
        resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _extract_metadata(raw: str) -> dict:
    """Pull the trailing ```json ... ``` block the model appends."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return {}


def _strip_metadata_block(raw: str) -> str:
    """Remove the ```json ... ``` block from the suggested text."""
    return re.sub(r"```json\s*\{.*?\}\s*```", "", raw, flags=re.DOTALL).strip()


def _next_version_number(db: Session, policy_id: str) -> int:
    """Return max(version_number) + 1 for the given policy, or 1 if none exist."""
    current_max = (
        db.query(func.max(models.PolicyVersion.version_number))
        .filter(models.PolicyVersion.policy_id == policy_id)
        .scalar()
    )
    return (current_max or 0) + 1


# ── Public API ────────────────────────────────────────────────────────────────

def generate_remediation_draft(
    *,
    db: Session,
    policy_id: str,
    policy_text: str,
    control: dict,
    ai_rationale: str,
    missing_checkpoints: list[str],
    mapping_review_id: Optional[str] = None,
    created_by_id: Optional[str] = None,
) -> models.RemediationDraft:
    """
    Generate and persist a draft of ONLY the policy sections needed to close
    a specific compliance gap.

    Args:
        db:                  SQLAlchemy session (caller owns commit/rollback).
        policy_id:           ID of the policy being remediated.
        policy_text:         Full text of the existing policy (never modified).
        control:             Dict with keys:
                               framework_name, framework_id,
                               control_id, control_code, control_title.
        ai_rationale:        Explanation of why the gap exists (from prior analysis).
        missing_checkpoints: Non-empty list of the specific requirements that fail.
        mapping_review_id:   Optional FK to the MappingReview that triggered this.
        created_by_id:       Optional UUID string of the requesting user.

    Returns:
        Persisted RemediationDraft with status="draft".
        The suggested_policy_text field contains ONLY the additive sections.

    Raises:
        ValueError:               If missing_checkpoints is empty or policy_text is blank.
        httpx.HTTPStatusError:    On OpenAI API failure.
        httpx.TimeoutException:   If OpenAI does not respond within 60 s.
    """
    if not missing_checkpoints:
        raise ValueError("missing_checkpoints must not be empty.")
    if not policy_text or not policy_text.strip():
        raise ValueError("policy_text must not be blank.")

    # Send only the first 6 000 characters as context so the model understands
    # what already exists without blowing the token budget. This is enough for
    # the model to detect duplicate content.
    policy_excerpt = policy_text[:6000]
    if len(policy_text) > 6000:
        policy_excerpt += "\n[… policy continues — remaining content omitted for brevity …]"

    missing_block = "\n".join(
        f"  {i + 1}. {req}" for i, req in enumerate(missing_checkpoints)
    )

    user_message = _USER_TEMPLATE.format(
        policy_excerpt=policy_excerpt,
        framework_name=control.get("framework_name", "Unknown Framework"),
        control_code=control.get("control_code", ""),
        control_title=control.get("control_title", ""),
        ai_rationale=ai_rationale or "No rationale provided.",
        missing_block=missing_block,
    )

    raw = _call_openai([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ])

    metadata = _extract_metadata(raw)
    suggested_text = _strip_metadata_block(raw)

    draft = models.RemediationDraft(
        policy_id=policy_id,
        mapping_review_id=mapping_review_id or None,
        # `or None` converts "" → None so PostgreSQL receives NULL instead of a
        # non-existent FK string, which would raise an IntegrityError.
        control_id=control.get("control_id") or None,
        framework_id=control.get("framework_id") or None,
        missing_requirements=missing_checkpoints,
        ai_rationale=ai_rationale,
        suggested_policy_text=suggested_text,
        section_headers=metadata.get("section_headers", []),
        remediation_status="draft",
        created_by=created_by_id,
    )
    db.add(draft)
    db.flush()   # assign draft.id before creating the linked version row

    # Snapshot the additive-only content as an ai_draft PolicyVersion so the
    # audit trail is complete without touching the original version rows.
    version = models.PolicyVersion(
        policy_id=policy_id,
        version_number=_next_version_number(db, policy_id),
        version_type="ai_draft",
        content=suggested_text,
        compliance_score=None,   # scored separately after human review
        remediation_draft_id=draft.id,
        change_summary=(
            f"AI draft: addresses {len(missing_checkpoints)} missing requirement(s) "
            f"for {control.get('control_code', '')} — {control.get('control_title', '')}."
        ),
        created_by=created_by_id,
    )
    db.add(version)
    db.commit()
    db.refresh(draft)
    return draft


def snapshot_original_version(
    *,
    db: Session,
    policy_id: str,
    policy_text: str,
    created_by_id: Optional[str] = None,
) -> models.PolicyVersion:
    """
    Record the original policy text as version 1 ("original").
    Call once at upload time so every subsequent diff has a baseline.
    Safe to skip if a version_type="original" row already exists.
    """
    already_exists = (
        db.query(models.PolicyVersion)
        .filter(
            models.PolicyVersion.policy_id == policy_id,
            models.PolicyVersion.version_type == "original",
        )
        .first()
    )
    if already_exists:
        return already_exists

    version = models.PolicyVersion(
        policy_id=policy_id,
        version_number=1,
        version_type="original",
        content=policy_text,
        compliance_score=None,
        remediation_draft_id=None,
        change_summary="Original upload.",
        created_by=created_by_id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version
