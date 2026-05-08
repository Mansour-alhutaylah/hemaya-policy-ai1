"""
ecc2_analyzer.py
ECC-2:2024 structured compliance analysis engine.

Data sources (in priority order):
  L1 — ecc_framework:            Official NCA control text (source of truth)
  L2 — ecc_compliance_metadata:  Applicability, frequency, responsible party
  L3 — ecc_ai_checkpoints:       AI audit hints (never used as requirements)

Results written to:
  policy_ecc_assessments   — detailed per-control results (new table)
  compliance_results       — summary row (for existing frontend compatibility)
  gaps                     — non-compliant / partial controls
  mapping_reviews          — evidence snippets per control
"""

import hashlib
import json
import re
import time
import uuid
import asyncio
from datetime import datetime, timezone
from sqlalchemy import text as sql_text

from backend.checkpoint_analyzer import call_llm, _find_grounded_evidence
from backend.vector_store import get_embeddings, search_similar_chunks

FRAMEWORK_ID = "ECC-2:2024"
FRAMEWORK_DISPLAY = "Essential Cybersecurity Controls v2 (ECC-2:2024)"

# Phase 7 verification cache — cache_key invariants.
# Bump ECC2_PROMPT_VERSION whenever the verifier prompt, the grounding logic,
# or the post-processing of GPT results changes meaningfully. The bump
# invalidates all old cache rows because the new key won't match.
# ECC2_MODEL must match the model name used inside call_llm (or any future
# override), so changing models also invalidates the cache automatically.
ECC2_PROMPT_VERSION = "v1"
ECC2_MODEL = "gpt-4o-mini"

# ── Stricter verifier prompt for official regulatory controls ─────────────────
# Two-tier design:
#   CHECKPOINT 1 [L1_official] — the binding NCA regulatory requirement.
#     High bar: must be addressed SPECIFICALLY and SUBSTANTIVELY.
#   CHECKPOINT 2+ [L3_audit_hint] — supplementary audit guidance only.
#     Standard bar: checks if implementation depth is documented.
#     These NEVER create compliance when CHECKPOINT 1 is not met.
ECC2_VERIFIER_PROMPT = """You assess whether a policy document complies with ECC-2:2024 controls from Saudi Arabia's NCA.

CHECKPOINT TIERS — apply different standards:

CHECKPOINT 1 [L1_official] is the OFFICIAL REGULATORY REQUIREMENT.
  - met=true ONLY if the policy SPECIFICALLY implements this requirement with concrete language
  - Generic phrases ("we follow best practices", "security policies are in place", "we protect data") do NOT satisfy
  - "policies exist" without describing WHAT they require does NOT satisfy
  - The policy must state WHAT the control does, WHO is responsible, or HOW it is enforced
  - When in doubt about CHECKPOINT 1, set met=false
  - confidence scale for CHECKPOINT 1:
      0.85-1.0: Requirement explicitly and specifically stated with mandatory language (shall/must/required)
      0.65-0.84: Requirement addressed with reasonable specificity but minor details missing
      0.40-0.64: Topic mentioned with some substance but key implementation details absent
      0.00-0.39: Absent, vague, or only generic/boilerplate language

CHECKPOINTS 2+ [L3_audit_hint] are supplementary implementation depth questions.
  - Apply a normal assessment — these check if specific practices are documented
  - met=true if the policy describes the practice, even without mandatory language
  - These inform implementation depth only; they cannot compensate for a failed CHECKPOINT 1

EVIDENCE RULE (all checkpoints):
  - evidence: quote the EXACT verbatim text from the policy that satisfies the checkpoint
  - The quote must appear in the provided POLICY TEXT EVIDENCE — do not paraphrase
  - If met=false, set evidence to "No evidence found"

Return ONLY valid JSON (no markdown, no extra text):
{
  "checkpoints": [
    {"index": 1, "met": true, "confidence": 0.88, "evidence": "exact quote from policy"},
    {"index": 2, "met": false, "confidence": 0.15, "evidence": "No evidence found"}
  ]
}"""


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful terms from control text for BM25 matching."""
    stop = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "should",
        "may", "might", "must", "shall", "can", "could", "not", "no", "nor",
        "and", "or", "but", "of", "in", "on", "at", "to", "for", "with",
        "from", "by", "about", "as", "into", "through", "during", "before",
        "after", "above", "below", "between", "each", "all", "any", "both",
        "few", "more", "most", "other", "some", "such", "than", "too", "very",
        "that", "this", "these", "those", "its", "their", "they", "them",
        "which", "when", "where", "what", "who", "how", "if", "then", "also",
        "including", "ensure", "establish", "organization", "entity",
    }
    words = re.findall(r"[a-z]{4,}", text.lower())
    return [w for w in words if w not in stop][:20]


# ── Action verb detection for coverage analysis ───────────────────────────────
# Maps semantic category → stem variants to look for in evidence / control text.
ACTION_VERBS: dict[str, set[str]] = {
    "document":     {"document", "documented", "record", "recorded", "log", "logged", "maintain", "maintained"},
    "approve":      {"approv", "authoriz", "sign-off", "signed off"},
    "review":       {"review", "audit", "assess", "evaluat", "inspect", "periodic", "annual", "quarterly"},
    "test":         {"test", "tested", "testing", "verif", "validat", "exercise", "simulat"},
    "monitor":      {"monitor", "track", "surveil", "observ", "detect", "alert", "watch"},
    "implement":    {"implement", "enforc", "deploy", "appl", "operat", "activat", "install"},
    "classify":     {"classif", "categori", "label", "tier", "sensitiv"},
    "report":       {"report", "escalat", "notif", "communicat", "inform", "disclose"},
    "train":        {"train", "aware", "educat", "instruct"},
    "retain":       {"retain", "retent", "preserv", "archive", "stor"},
    "update":       {"update", "updat", "revis", "amend", "refresh"},
    "identify":     {"identif", "discover", "detect", "recogniz", "list", "inventori"},
}


def _extract_required_actions(control_text: str) -> set[str]:
    """Return which action categories appear in the L1 control requirement text."""
    t = control_text.lower()
    return {cat for cat, verbs in ACTION_VERBS.items() if any(v in t for v in verbs)}


def _compute_action_coverage(required: set[str], evidence: str) -> tuple[float, set[str], set[str]]:
    """
    Check which required action categories appear in the evidence text.
    Returns (coverage_ratio, covered_set, missing_set).
    """
    if not required:
        return 1.0, set(), set()
    ev = evidence.lower()
    covered = {cat for cat in required if any(v in ev for v in ACTION_VERBS[cat])}
    missing = required - covered
    ratio = len(covered) / len(required)
    return ratio, covered, missing


def _ensure_framework_row(db) -> str:
    """Ensure ECC-2:2024 exists in the frameworks table; return its UUID."""
    row = db.execute(sql_text(
        "SELECT id FROM frameworks WHERE name = :n"
    ), {"n": FRAMEWORK_ID}).fetchone()
    if row:
        return str(row[0])
    fwid = str(uuid.uuid4())
    db.execute(sql_text("""
        INSERT INTO frameworks (id, name, description, version)
        VALUES (:id, :name, :desc, :ver)
        ON CONFLICT (name) DO NOTHING
    """), {
        "id": fwid,
        "name": FRAMEWORK_ID,
        "desc": FRAMEWORK_DISPLAY,
        "ver": "2024",
    })
    db.commit()
    # Re-fetch in case of race
    row = db.execute(sql_text(
        "SELECT id FROM frameworks WHERE name = :n"
    ), {"n": FRAMEWORK_ID}).fetchone()
    return str(row[0])


def load_ecc2_controls(db) -> list[dict]:
    """
    Load all ECC-2:2024 controls joining L1 + L2 + L3.
    Returns a list of dicts with all three layers merged.
    """
    rows = db.execute(sql_text("""
        SELECT
            f.control_code,
            f.control_type,
            f.control_text,
            f.domain_code,
            f.domain_name,
            f.subdomain_code,
            f.subdomain_name,
            f.parent_control_code,
            f.is_ecc2_new,
            m.applicability,
            m.responsible_party,
            m.frequency,
            m.deleted_in_ecc2,
            c.audit_questions,
            c.suggested_evidence,
            c.possible_technical_evidence,
            c.indicators_of_implementation
        FROM ecc_framework f
        LEFT JOIN ecc_compliance_metadata m
            ON f.framework_id = m.framework_id AND f.control_code = m.control_code
        LEFT JOIN ecc_ai_checkpoints c
            ON f.framework_id = c.framework_id AND f.control_code = c.control_code
        WHERE f.framework_id = :fwid
        ORDER BY f.control_code
    """), {"fwid": FRAMEWORK_ID}).fetchall()

    controls = []
    for r in rows:
        def _parse_jsonb(val):
            if val is None:
                return []
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return []
            return list(val) if hasattr(val, "__iter__") else []

        audit_qs = _parse_jsonb(r[13])
        suggested_ev = _parse_jsonb(r[14])
        tech_ev = _parse_jsonb(r[15])
        indicators = _parse_jsonb(r[16])

        # Build keyword pool from L3 audit questions and suggested evidence
        kw_pool = _extract_keywords(r[2] or "")  # L1 control text
        for aq in audit_qs[:3]:
            kw_pool += _extract_keywords(aq)
        for se in suggested_ev[:3]:
            kw_pool += _extract_keywords(se)
        kw_pool = list(dict.fromkeys(kw_pool))[:30]  # dedup, cap at 30

        controls.append({
            "control_code": r[0],
            "control_type": str(r[1]) if r[1] else "main_control",
            "control_text": r[2] or "",
            "domain_code": r[3],
            "domain_name": r[4],
            "subdomain_code": r[5],
            "subdomain_name": r[6],
            "parent_control_code": r[7],
            "is_ecc2_new": bool(r[8]),
            "applicability": str(r[9]) if r[9] else "mandatory_all",
            "responsible_party": r[10],
            "frequency": r[11],
            "deleted_in_ecc2": bool(r[12]) if r[12] is not None else False,
            "audit_questions": audit_qs[:3],
            "suggested_evidence": suggested_ev[:4],
            "possible_technical_evidence": tech_ev[:3],
            "indicators_of_implementation": indicators[:3],
            "keywords": kw_pool,
            "l1_loaded": bool(r[2]),
            "l2_loaded": r[9] is not None,
            "l3_loaded": r[13] is not None,
        })

    return controls


async def _assess_control(
    control: dict,
    policy_chunks: list,
    policy_text: str,
    bm25_index=None,
    diag: bool = False,
    db=None,
    policy_hash: str | None = None,
) -> dict:
    """
    Assess one ECC-2 control against policy text.

    Verification items built from:
      - L1 control_text (weight 2.0) — the official regulatory requirement
      - L3 audit_questions[0:3] (weight 1.0 each) — AI guidance hints

    L3 items are labelled in the prompt so GPT knows they are auxiliary hints,
    not additional regulatory requirements.

    bm25_index: pre-built BM25Okapi over policy_chunks — pass from caller to
                avoid rebuilding the index 200× (one rebuild per control call).
    diag:       when True, print focused_text snippet and raw GPT response.
    db, policy_hash: when both provided, read/write the
                ecc2_verification_cache. Cache is keyed on
                (control_code, policy_hash, ECC2_PROMPT_VERSION, ECC2_MODEL).
                On cache hit: skip GPT call AND grounding (results are stored
                post-grounded). On miss: call GPT + ground as today, then
                write the post-grounded results back. Cache failures are
                swallowed and never block the analysis.
    """
    from backend.checkpoint_analyzer import _find_relevant_sections
    from rank_bm25 import BM25Okapi

    control_code = control["control_code"]
    control_text = control["control_text"]
    audit_qs = control["audit_questions"]
    keywords = control["keywords"]

    # Build BM25 index only if caller didn't provide one
    if bm25_index is None and policy_chunks:
        tokenized = [c["text"].lower().split() for c in policy_chunks]
        bm25_index = BM25Okapi(tokenized)

    # Find relevant policy sections using L1 text + L3 keywords
    focused_text, retrieval_quality = _find_relevant_sections(
        policy_chunks, control_text, keywords, bm25=bm25_index, offset=0
    )

    if diag:
        print(
            f"    [ECC2][DIAG][{control_code}] "
            f"focused_text={len(focused_text)} chars | "
            f"retrieval_quality={retrieval_quality:.3f}"
        )
        print(f"    [ECC2][DIAG][{control_code}] focused_text[:300]: {focused_text[:300]!r}")

    # Build verification checkpoints
    checkpoints = [
        {
            "checkpoint_index": 1,
            "checkpoint_id": f"{control_code}-L1",
            "requirement": control_text,
            "weight": 2.0,
            "source": "L1_official",
        }
    ]
    for i, aq in enumerate(audit_qs[:3], start=2):
        checkpoints.append({
            "checkpoint_index": i,
            "checkpoint_id": f"{control_code}-L3-{i}",
            "requirement": aq,
            "weight": 1.0,
            "source": "L3_audit_hint",
        })

    # ── Phase 7 cache lookup ─────────────────────────────────────────────────
    # Key invariants: control_code | policy_hash | prompt_version | model |
    #                 retrieval_min_score.
    # Any of those changing produces a cache miss; old rows become dormant.
    # Cached rows store POST-grounded results, so on hit we skip BOTH the GPT
    # call and the grounding pass. Downstream scoring runs identically.
    #
    # Phase 9 added retrieval_min_score to the key. The relevance floor in
    # _find_relevant_sections changes the focused_text passed to GPT, so a
    # verdict cached under one floor must not be served on a request using
    # a different floor. The value is read dynamically (not at import time)
    # so monkeypatching RAG_MIN_RELEVANCE_SCORE in tests reflects in the key.
    cache_key = None
    results = None  # populated from cache or from GPT
    if db is not None and policy_hash:
        from backend import checkpoint_analyzer as _ca
        retrieval_floor = getattr(_ca, "RAG_MIN_RELEVANCE_SCORE", 0.0)
        key_input = (
            f"ECC2|{control_code}|{policy_hash}|"
            f"{ECC2_PROMPT_VERSION}|{ECC2_MODEL}|"
            f"floor={retrieval_floor:.3f}"
        )
        cache_key = hashlib.sha256(key_input.encode("utf-8")).hexdigest()
        try:
            row = db.execute(sql_text(
                "SELECT result FROM ecc2_verification_cache WHERE cache_key = :ck"
            ), {"ck": cache_key}).fetchone()
            if row is not None:
                cached = row[0]
                if isinstance(cached, str):  # JSONB driver round-trip safety
                    cached = json.loads(cached)
                results = cached
                if diag:
                    print(f"    [ECC2][DIAG][{control_code}] CACHE HIT")
        except Exception as cache_read_err:
            # Cache failure must never block analysis.
            print(f"    [ECC2][{control_code}] cache read failed: {cache_read_err}")
            try:
                db.rollback()
            except Exception:
                pass

    if results is None:
        # ── Build GPT prompt and call (cache miss path) ──────────────────────
        cp_lines = "\n".join(
            f"CHECKPOINT {cp['checkpoint_index']} [source={cp['source']}]: {cp['requirement']}"
            for cp in checkpoints
        )
        user_msg = (
            f"Control: {control_code} ({control['control_type']})\n"
            f"Domain: {control['domain_code']} — {control['subdomain_code']}\n\n"
            f"{cp_lines}\n\n"
            f"POLICY TEXT EVIDENCE:\n{focused_text[:12000]}"
        )

        try:
            raw = await call_llm(ECC2_VERIFIER_PROMPT, user_msg)
            if diag:
                print(f"    [ECC2][DIAG][{control_code}] raw GPT response: {raw[:600]}")
            gpt_data = json.loads(raw)
            results = gpt_data.get("checkpoints", [])
        except Exception as e:
            print(f"    [ECC2][{control_code}] GPT error: {e}")
            results = [
                {
                    "index": cp["checkpoint_index"],
                    "met": False,
                    "confidence": 0.1,
                    "evidence": f"GPT error: {str(e)[:80]}",
                }
                for cp in checkpoints
            ]

        # Apply grounding check — reject evidence that can't be found in policy text
        for v in results:
            if v.get("met"):
                ev = v.get("evidence", "")
                if ev and ev.strip().lower() != "no evidence found":
                    grounded, actual, sim = _find_grounded_evidence(ev, policy_text)
                    if not grounded:
                        v["met"] = False
                        v["confidence"] = max(0.05, float(v.get("confidence", 0.5)) - 0.4)
                        v["evidence"] = "Evidence could not be grounded in policy text"
                        print(
                            f"    [ECC2][{control_code}] CP{v.get('index')} "
                            f"GROUNDING REJECTED (sim={sim:.2f})"
                        )
                    else:
                        v["evidence"] = actual

        # ── Cache write (post-grounded results) ──────────────────────────────
        # Best-effort: cache failures must not abort analysis. Don't cache the
        # synthetic GPT-error fallback; it would poison subsequent runs.
        is_gpt_error_fallback = (
            len(results) == len(checkpoints)
            and all(
                isinstance(v.get("evidence"), str) and v["evidence"].startswith("GPT error: ")
                for v in results
            )
        )
        if db is not None and cache_key is not None and not is_gpt_error_fallback:
            try:
                db.execute(sql_text("""
                    INSERT INTO ecc2_verification_cache
                      (cache_key, control_code, policy_hash, prompt_version, model, result)
                    VALUES
                      (:ck, :cc, :ph, :pv, :mdl, CAST(:res AS JSONB))
                    ON CONFLICT (cache_key) DO NOTHING
                """), {
                    "ck":  cache_key,
                    "cc":  control_code,
                    "ph":  policy_hash,
                    "pv":  ECC2_PROMPT_VERSION,
                    "mdl": ECC2_MODEL,
                    "res": json.dumps(results),
                })
                db.commit()
            except Exception as cache_write_err:
                print(f"    [ECC2][{control_code}] cache write failed: {cache_write_err}")
                try:
                    db.rollback()
                except Exception:
                    pass

    # ── Build result map ─────────────────────────────────────────────────────
    res_map = {v.get("index"): v for v in results}

    # L1 facts — grounding check already ran above; met=True only if grounding passed
    l1_r = res_map.get(1, {"met": False, "confidence": 0.1, "evidence": ""})
    l1_met = bool(l1_r.get("met", False))
    l1_conf = float(l1_r.get("confidence", 0.1))
    l1_ev = (l1_r.get("evidence") or "").strip()
    # "grounded evidence" means met=True (grounding passed) AND a real quote exists
    _ev_bad = ("no evidence found", "no result", "", "evidence could not be grounded in policy text")
    l1_has_grounded_evidence = l1_met and bool(l1_ev and l1_ev.lower() not in _ev_bad)

    # L3 depth ratio (supplementary, never drives status)
    l3_checkpoints = [cp for cp in checkpoints if cp["checkpoint_index"] > 1]
    l3_met_w = sum(
        cp["weight"]
        for cp in l3_checkpoints
        if res_map.get(cp["checkpoint_index"], {}).get("met", False)
    )
    l3_total_w = sum(cp["weight"] for cp in l3_checkpoints) or 1.0
    l3_ratio = l3_met_w / l3_total_w

    # Weighted score and confidence (for reporting, not status gating)
    met_weight = (2.0 if l1_met else 0.0) + l3_met_w
    total_weight = 2.0 + l3_total_w
    score = (met_weight / total_weight * 100) if total_weight > 0 else 0

    conf_sum = l1_conf * 2.0 + sum(
        float(res_map.get(cp["checkpoint_index"], {}).get("confidence", 0.1)) * cp["weight"]
        for cp in l3_checkpoints
    )
    avg_confidence = conf_sum / total_weight

    # Best evidence: L1 grounded quote first, then first passing L3
    best_evidence = l1_ev if l1_has_grounded_evidence else ""
    if not best_evidence:
        for cp in l3_checkpoints:
            r = res_map.get(cp["checkpoint_index"], {})
            if r.get("met"):
                ev = (r.get("evidence") or "").strip()
                if ev and ev.lower() not in ("no evidence found",):
                    best_evidence = ev
                    break

    # ── Action-verb coverage on L1 evidence ──────────────────────────────────
    # Extract which action categories the L1 control REQUIRES, then check
    # how many of those appear in the grounded evidence quote.
    required_actions = _extract_required_actions(control_text)
    if l1_has_grounded_evidence and required_actions:
        action_coverage, covered_actions, missing_actions = _compute_action_coverage(
            required_actions, l1_ev
        )
    elif l1_has_grounded_evidence and not required_actions:
        # No specific action verbs in control text → documentation-only control
        # Evidence is sufficient on its own if it's grounded
        action_coverage = 1.0
        covered_actions = set()
        missing_actions = set()
    else:
        action_coverage = 0.0
        covered_actions = set()
        missing_actions = required_actions

    # ── L1-GATED STATUS ASSIGNMENT ───────────────────────────────────────────
    # Rule: L3 audit hints CANNOT create compliance without grounded L1 evidence.
    #
    # IMPORTANT: GPT only says met=True when highly confident (due to "when in doubt
    # set met=false" instruction), so all met=True cases have conf ≥ ~0.80.
    # Therefore we must NOT use a bare "conf >= 0.85 → compliant" shortcut —
    # that would make partial unreachable. Instead, action_coverage is the
    # primary differentiator between compliant and partial.
    #
    # Compliant  — grounded evidence EXISTS + confidence ≥ 0.65 + actions covered
    # Partial    — grounded evidence EXISTS but actions incomplete or conf moderate
    # Non-compl  — no grounded L1 evidence, or evidence too vague (conf < 0.45)

    if not l1_has_grounded_evidence:
        status = "non_compliant"
        status_reason = (
            f"No grounded L1 evidence (l1_met={l1_met}, conf={l1_conf:.2f})"
        )
    elif l1_conf < 0.45:
        # Evidence exists but GPT was not convinced — likely generic/boilerplate
        status = "non_compliant"
        status_reason = f"L1 evidence too vague (conf={l1_conf:.2f} < 0.45)"
    elif l1_conf >= 0.65 and (action_coverage >= 0.50 or l3_ratio >= 0.67):
        # Solid evidence AND (action verbs substantially covered OR L3 depth confirms it)
        status = "compliant"
        status_reason = (
            f"L1 solid (conf={l1_conf:.2f}), "
            f"action_cov={action_coverage:.2f}, L3_ratio={l3_ratio:.2f}, "
            f"covered={covered_actions}"
        )
    else:
        # Has grounded evidence AND conf ≥ 0.45, but EITHER:
        #   - confidence only moderate (0.45–0.64)
        #   - confidence high but required actions not substantially covered
        #   - L3 depth too low
        status = "partial"
        status_reason = (
            f"L1 partial (conf={l1_conf:.2f}), "
            f"action_cov={action_coverage:.2f}, L3_ratio={l3_ratio:.2f}, "
            f"covered={covered_actions} missing={missing_actions}"
        )
        print(
            f"    [ECC2][PARTIAL_BRANCH_HIT] {control_code} "
            f"l1_conf={l1_conf:.2f} action_cov={action_coverage:.2f} "
            f"covered={covered_actions} missing={missing_actions} "
            f"evidence={l1_ev[:120]!r}"
        )

    # Gap description from unmet checkpoints
    gap_parts = []
    for cp in checkpoints:
        r = res_map.get(cp["checkpoint_index"], {"met": False})
        if not r.get("met"):
            gap_parts.append(cp["requirement"][:120])
    gap_desc = "; ".join(gap_parts) if gap_parts else ""

    print(
        f"    [ECC2][{control_code}] "
        f"L1_conf={l1_conf:.2f} grounded={'Y' if l1_has_grounded_evidence else 'N'} "
        f"action_cov={action_coverage:.2f} "
        f"covered={covered_actions or '-'} missing={missing_actions or '-'} "
        f"L3_ratio={l3_ratio:.2f} quality={retrieval_quality:.2f} "
        f"-> {status} | {status_reason}"
    )

    return {
        "control_code": control_code,
        "control_type": control["control_type"],
        "control_text": control_text,
        "domain_code": control["domain_code"],
        "subdomain_code": control["subdomain_code"],
        "compliance_status": status,
        "evidence_text": best_evidence or "No direct evidence found",
        "gap_description": gap_desc,
        "confidence_score": round(min(1.0, max(0.0, avg_confidence)), 3),
        "score": round(score, 1),
        "retrieval_quality": round(retrieval_quality, 3),
        "l1_loaded": control["l1_loaded"],
        "l2_loaded": control["l2_loaded"],
        "l3_loaded": control["l3_loaded"],
        "source_tables": "ecc_framework + ecc_compliance_metadata + ecc_ai_checkpoints",
        # Diagnostic fields (used for distribution stats in run_ecc2_analysis)
        "_l1_conf": l1_conf,
        "_l1_grounded": l1_has_grounded_evidence,
        "_action_cov": round(action_coverage, 2),
        "sub_results": [
            {
                "source": cp["source"],
                "requirement": cp["requirement"][:200],
                "met": bool(res_map.get(cp["checkpoint_index"], {}).get("met", False)),
                "evidence": res_map.get(cp["checkpoint_index"], {}).get("evidence", ""),
                "confidence": res_map.get(cp["checkpoint_index"], {}).get("confidence", 0.1),
            }
            for cp in checkpoints
        ],
    }


def _save_assessment_row(db, policy_id: str, result: dict, framework_id_legacy: str):
    """Write one control result to policy_ecc_assessments."""
    db.execute(sql_text("""
        INSERT INTO policy_ecc_assessments
            (id, policy_id, framework_id, control_code, compliance_status,
             evidence_text, gap_description, confidence_score, assessed_by, assessed_at)
        VALUES
            (:id, CAST(:pid AS uuid), :fwid, :cc, CAST(:cs AS compliance_status_enum),
             :ev, :gap, :conf, CAST('AI' AS assessed_by_enum), :at)
        ON CONFLICT (policy_id, control_code)
        DO UPDATE SET
            compliance_status = EXCLUDED.compliance_status,
            evidence_text     = EXCLUDED.evidence_text,
            gap_description   = EXCLUDED.gap_description,
            confidence_score  = EXCLUDED.confidence_score,
            assessed_at       = EXCLUDED.assessed_at
    """), {
        "id": str(uuid.uuid4()),
        "pid": str(policy_id),
        "fwid": FRAMEWORK_ID,
        "cc": result["control_code"],
        "cs": result["compliance_status"],
        "ev": (result.get("evidence_text") or "")[:4000],
        "gap": (result.get("gap_description") or "")[:2000],
        "conf": result["confidence_score"],
        "at": datetime.now(timezone.utc),
    })


async def run_ecc2_analysis(db, policy_id: str, progress_cb=None) -> dict:
    """
    Main entry point: analyze a policy against all 200 ECC-2:2024 controls.

    Returns a summary dict keyed by FRAMEWORK_ID, compatible with the format
    returned by run_checkpoint_analysis so main.py can merge results.
    """
    def _report(pct: int, stage: str):
        if progress_cb:
            try:
                progress_cb(pct, stage)
            except Exception:
                pass

    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"ECC-2:2024 STRUCTURED ANALYSIS STARTED — policy={policy_id}")
    print(f"{'='*60}")

    _report(12, "ECC-2: Checking policy chunks")

    # ── Auto-embed policy if chunks are missing ───────────────────────────
    n_chunks = db.execute(sql_text(
        "SELECT COUNT(*) FROM policy_chunks "
        "WHERE policy_id = :pid AND embedding IS NOT NULL"
    ), {"pid": policy_id}).fetchone()[0]

    if n_chunks == 0:
        print("  [ECC2] Auto-embedding policy chunks...")
        _report(15, "ECC-2: Embedding policy text")
        from backend.checkpoint_analyzer import _auto_embed
        embedded = await _auto_embed(db, policy_id)
        if embedded == 0:
            return {
                FRAMEWORK_ID: {"error": "No text found in policy. Re-upload the document."}
            }
        n_chunks = embedded

    print(f"  [ECC2] Policy has {n_chunks} embedded chunks")
    _report(18, "ECC-2: Loading structured controls")

    # ── Load all ECC-2 controls (L1 + L2 + L3) ───────────────────────────
    try:
        controls = load_ecc2_controls(db)
    except Exception as e:
        print(f"  [ECC2] ERROR loading controls: {e}")
        return {
            FRAMEWORK_ID: {
                "error": (
                    f"ECC-2 structured tables not loaded: {e}. "
                    "Run: python data/ecc2/ecc2_import.py --force"
                )
            }
        }

    if not controls:
        return {
            FRAMEWORK_ID: {
                "error": "ecc_framework is empty. Run ecc2_import.py to load data."
            }
        }

    # Skip deleted controls
    active_controls = [c for c in controls if not c["deleted_in_ecc2"]]
    deleted_count = len(controls) - len(active_controls)
    print(f"  [ECC2] {len(active_controls)} active controls "
          f"({deleted_count} deleted in ECC-2 — skipped)")
    _report(22, f"ECC-2: Analysing {len(active_controls)} controls")

    # ── Load policy chunks for BM25 retrieval ────────────────────────────
    try:
        chunk_rows = db.execute(sql_text(
            "SELECT chunk_text, COALESCE(classification, 'descriptive') "
            "FROM policy_chunks WHERE policy_id = :pid ORDER BY chunk_index"
        ), {"pid": policy_id}).fetchall()
        policy_chunks = [{"text": r[0], "classification": r[1]}
                         for r in chunk_rows if r[0]]
    except Exception:
        db.rollback()
        chunk_rows = db.execute(sql_text(
            "SELECT chunk_text FROM policy_chunks "
            "WHERE policy_id = :pid ORDER BY chunk_index"
        ), {"pid": policy_id}).fetchall()
        policy_chunks = [{"text": r[0], "classification": "descriptive"}
                         for r in chunk_rows if r[0]]

    policy_text = "\n\n".join(c["text"] for c in policy_chunks)
    # Phase 7 cache key invariant: hash the joined policy text once per run.
    # Truncated to 16 hex chars to match the legacy verification_cache pattern
    # (checkpoint_analyzer.py) so both caches behave consistently.
    policy_hash = hashlib.sha256(policy_text.encode("utf-8")).hexdigest()[:16]
    print(f"  [ECC2] Loaded {len(policy_chunks)} chunks "
          f"({len(policy_text)} chars total policy text, hash={policy_hash})")

    # ── Build BM25 index ONCE over the policy corpus ──────────────────────
    # Previously rebuilt inside _assess_control for every control (200×).
    # The index only depends on policy_chunks, not the control being assessed.
    from rank_bm25 import BM25Okapi
    if policy_chunks:
        _bm25_tokenized = [c["text"].lower().split() for c in policy_chunks]
        global_bm25 = BM25Okapi(_bm25_tokenized)
        print(f"  [ECC2] BM25 index built over {len(policy_chunks)} chunks")
    else:
        global_bm25 = None

    # ── Ensure legacy frameworks row exists (for compliance_results FK) ──
    legacy_fw_id = _ensure_framework_row(db)
    print(f"  [ECC2] Legacy framework row: {legacy_fw_id}")

    # ── Parallel analysis (semaphore 8) ───────────────────────────────────
    sem = asyncio.Semaphore(8)
    results_list: list[dict] = []

    async def _run_one(ctrl, ctrl_idx: int):
        async with sem:
            return await _assess_control(
                ctrl, policy_chunks, policy_text,
                bm25_index=global_bm25,
                diag=(ctrl_idx < 3),  # detailed logs for first 3 controls only
                db=db,
                policy_hash=policy_hash,
            )

    total_ctrl = len(active_controls)
    batch_size = 8
    for i in range(0, total_ctrl, batch_size):
        batch = active_controls[i:i + batch_size]
        t1 = time.time()
        batch_results = await asyncio.gather(
            *[_run_one(c, i + j) for j, c in enumerate(batch)]
        )
        results_list.extend(batch_results)
        done = min(i + batch_size, total_ctrl)
        elapsed = round(time.time() - t1, 1)
        pct = int(22 + (done / total_ctrl) * 65)
        print(f"  [ECC2] Controls {i+1}-{done}/{total_ctrl} in {elapsed}s")
        _report(pct, f"ECC-2: {done}/{total_ctrl} controls")

    # ── Diagnostic distribution (helps debug partial reachability) ───────────
    d_low  = [r for r in results_list if r["_l1_conf"] < 0.45]
    d_mid  = [r for r in results_list if 0.45 <= r["_l1_conf"] < 0.75]
    d_high = [r for r in results_list if r["_l1_conf"] >= 0.75]
    d_grounded = [r for r in results_list if r["_l1_grounded"]]
    d_partial_cands = [r for r in d_grounded if r["_l1_conf"] >= 0.45]
    print(f"\n  [ECC2] === CONFIDENCE DISTRIBUTION ({len(results_list)} controls) ===")
    print(f"    L1_conf 0.00–0.44 : {len(d_low):3d}  (all → non_compliant)")
    print(f"    L1_conf 0.45–0.74 : {len(d_mid):3d}  (grounded → partial candidates)")
    print(f"    L1_conf 0.75–1.00 : {len(d_high):3d}  (grounded → compliant/partial by action_cov)")
    print(f"    Grounded evidence  : {len(d_grounded):3d}")
    print(f"    Partial candidates : {len(d_partial_cands):3d}  (grounded + conf >= 0.45)")
    if d_partial_cands:
        cov_vals = [r["_action_cov"] for r in d_partial_cands]
        print(f"    action_cov range   : {min(cov_vals):.2f} – {max(cov_vals):.2f}  "
              f"(mean={sum(cov_vals)/len(cov_vals):.2f})")
        below_half = sum(1 for v in cov_vals if v < 0.50)
        print(f"    action_cov < 0.50  : {below_half:3d}  (→ partial)")
        print(f"    action_cov >= 0.50 : {len(cov_vals)-below_half:3d}  (→ compliant if conf >= 0.65)")
    print(f"  [ECC2] =====================================================\n")

    # ── Aggregate scores ──────────────────────────────────────────────────
    comp = sum(1 for r in results_list if r["compliance_status"] == "compliant")
    part = sum(1 for r in results_list if r["compliance_status"] == "partial")
    miss = sum(1 for r in results_list if r["compliance_status"] == "non_compliant")
    total = len(results_list)
    score = ((comp + part * 0.5) / total * 100) if total else 0
    duration = round(time.time() - t0, 1)

    print(f"\n  [ECC2] RESULT: {round(score, 1)}% "
          f"({comp} compliant, {part} partial, {miss} non-compliant) "
          f"in {duration}s")

    _report(88, "ECC-2: Saving results")

    # ── Save to policy_ecc_assessments (new structured table) ────────────
    try:
        for result in results_list:
            _save_assessment_row(db, policy_id, result, legacy_fw_id)
        db.commit()
        print(f"  [ECC2] Saved {len(results_list)} rows to policy_ecc_assessments")
    except Exception as e:
        db.rollback()
        print(f"  [ECC2] WARNING: policy_ecc_assessments save failed: {e}")
        print(f"  [ECC2] Continuing with compliance_results save...")

    # ── Save summary to compliance_results (legacy frontend table) ────────
    try:
        db.execute(sql_text("""
            INSERT INTO compliance_results
                (id, policy_id, framework_id, compliance_score,
                 controls_covered, controls_partial, controls_missing,
                 status, analyzed_at, analysis_duration, details)
            VALUES
                (:id, :pid, :fwid, :sc, :cov, :par, :mis,
                 'completed', :at, :dur, :det)
            ON CONFLICT DO NOTHING
        """), {
            "id": str(uuid.uuid4()),
            "pid": policy_id,
            "fwid": legacy_fw_id,
            "sc": round(score, 1),
            "cov": comp,
            "par": part,
            "mis": miss,
            "at": datetime.now(timezone.utc),
            "dur": duration,
            "det": json.dumps([{
                "control_code": r["control_code"],
                "control_type": r["control_type"],
                "domain_code": r["domain_code"],
                "subdomain_code": r["subdomain_code"],
                "status": (
                    "Compliant" if r["compliance_status"] == "compliant"
                    else "Partial" if r["compliance_status"] == "partial"
                    else "Non-Compliant"
                ),
                "score": r["score"],
                "confidence": r["confidence_score"],
                "evidence": r["evidence_text"][:300],
                "l1_loaded": r["l1_loaded"],
                "l2_loaded": r["l2_loaded"],
                "l3_loaded": r["l3_loaded"],
                "source_tables": r["source_tables"],
            } for r in results_list]),
        })
        db.commit()
        print(f"  [ECC2] Saved compliance_results summary row")
    except Exception as e:
        db.rollback()
        print(f"  [ECC2] WARNING: compliance_results save failed: {e}")

    # ── Save gaps ─────────────────────────────────────────────────────────
    try:
        gap_count = 0
        for r in results_list:
            if r["compliance_status"] in ("non_compliant", "partial"):
                sev = (
                    "High" if r["compliance_status"] == "non_compliant"
                    else "Medium"
                )
                db.execute(sql_text("""
                    INSERT INTO gaps
                        (id, policy_id, framework_id, control_id, control_name,
                         severity, status, description, remediation, created_at)
                    VALUES
                        (:id, :pid, :fwid, NULL, :cn,
                         :sev, 'Open', :desc, :rem, :at)
                """), {
                    "id": str(uuid.uuid4()),
                    "pid": policy_id,
                    "fwid": legacy_fw_id,
                    "cn": f"{r['control_code']} — {r['control_text'][:80]}",
                    "sev": sev,
                    "desc": (r.get("gap_description") or f"ECC-2 control {r['control_code']} not met")[:500],
                    "rem": (
                        f"Address ECC-2 control {r['control_code']}: "
                        f"{r['control_text'][:200]}"
                    ),
                    "at": datetime.now(timezone.utc),
                })
                gap_count += 1
        db.commit()
        print(f"  [ECC2] Saved {gap_count} gap rows")
    except Exception as e:
        db.rollback()
        print(f"  [ECC2] WARNING: gaps save failed: {e}")

    # ── Save mapping reviews ───────────────────────────────────────────────
    try:
        mr_count = 0
        for r in results_list:
            ev = r.get("evidence_text") or "No direct evidence found"
            conf = r.get("confidence_score", 0.5)
            dec = (
                "Accepted" if r["compliance_status"] == "compliant" and conf >= 0.75
                else "Flagged" if r["compliance_status"] == "non_compliant"
                else "Pending"
            )
            db.execute(sql_text("""
                INSERT INTO mapping_reviews
                    (id, policy_id, control_id, framework_id, evidence_snippet,
                     confidence_score, ai_rationale, decision, created_at)
                VALUES
                    (:id, :pid, NULL, :fwid, :ev, :conf, :rat, :dec, :at)
            """), {
                "id": str(uuid.uuid4()),
                "pid": policy_id,
                "fwid": legacy_fw_id,
                "ev": ev[:2000],
                "conf": float(conf),
                "rat": (
                    f"[ECC2][{r['control_code']}] "
                    f"Score={r['score']}% | "
                    f"L1={r['l1_loaded']} L2={r['l2_loaded']} L3={r['l3_loaded']} | "
                    f"Retrieval quality={r['retrieval_quality']}"
                )[:500],
                "dec": dec,
                "at": datetime.now(timezone.utc),
            })
            mr_count += 1
        db.commit()
        print(f"  [ECC2] Saved {mr_count} mapping_reviews rows")
    except Exception as e:
        db.rollback()
        print(f"  [ECC2] WARNING: mapping_reviews save failed: {e}")

    # ── Update policy status ───────────────────────────────────────────────
    try:
        db.execute(sql_text(
            "UPDATE policies SET status='analyzed', last_analyzed_at=:now WHERE id=:pid"
        ), {"now": datetime.now(timezone.utc), "pid": policy_id})
        db.commit()
    except Exception:
        db.rollback()

    print(f"\n{'='*60}")
    print(f"ECC-2 ANALYSIS COMPLETE: {duration}s | "
          f"score={round(score, 1)}% | {comp}✓ {part}~ {miss}✗")
    print(f"{'='*60}\n")

    return {
        FRAMEWORK_ID: {
            "score": round(score, 1),
            "total_controls": total,
            "compliant": comp,
            "partial": part,
            "non_compliant": miss,
            "not_applicable": deleted_count,
            "duration_s": duration,
            "analyzer_source": "structured_ecc_tables",
        }
    }


def verify_ecc2_loaded(db) -> dict:
    """
    Check that all three ECC-2 data layers are present in the database.
    Used by the /api/ecc2/status endpoint.
    """
    result = {
        "framework_id": FRAMEWORK_ID,
        "layer1_count": 0,
        "layer2_count": 0,
        "layer3_count": 0,
        "joined_count": 0,
        "orphan_l3_count": 0,
        "missing_l2_count": 0,
        "analyzer_source": "not_loaded",
        "status": "not_loaded",
        "errors": [],
    }

    try:
        result["layer1_count"] = db.execute(sql_text(
            "SELECT COUNT(*) FROM ecc_framework WHERE framework_id = :fwid"
        ), {"fwid": FRAMEWORK_ID}).fetchone()[0]
    except Exception as e:
        result["errors"].append(f"ecc_framework: {e}")

    try:
        result["layer2_count"] = db.execute(sql_text(
            "SELECT COUNT(*) FROM ecc_compliance_metadata WHERE framework_id = :fwid"
        ), {"fwid": FRAMEWORK_ID}).fetchone()[0]
    except Exception as e:
        result["errors"].append(f"ecc_compliance_metadata: {e}")

    try:
        result["layer3_count"] = db.execute(sql_text(
            "SELECT COUNT(*) FROM ecc_ai_checkpoints WHERE framework_id = :fwid"
        ), {"fwid": FRAMEWORK_ID}).fetchone()[0]
    except Exception as e:
        result["errors"].append(f"ecc_ai_checkpoints: {e}")

    try:
        result["joined_count"] = db.execute(sql_text(
            "SELECT COUNT(*) FROM ecc_full_control_view WHERE framework_id = :fwid"
        ), {"fwid": FRAMEWORK_ID}).fetchone()[0]
    except Exception as e:
        result["errors"].append(f"ecc_full_control_view: {e}")

    try:
        result["orphan_l3_count"] = db.execute(sql_text("""
            SELECT COUNT(*)
            FROM ecc_ai_checkpoints c
            LEFT JOIN ecc_framework f
                ON c.framework_id = f.framework_id AND c.control_code = f.control_code
            WHERE c.framework_id = :fwid AND f.control_code IS NULL
        """), {"fwid": FRAMEWORK_ID}).fetchone()[0]
    except Exception as e:
        result["errors"].append(f"orphan check: {e}")

    try:
        result["missing_l2_count"] = db.execute(sql_text("""
            SELECT COUNT(*)
            FROM ecc_framework f
            LEFT JOIN ecc_compliance_metadata m
                ON f.framework_id = m.framework_id AND f.control_code = m.control_code
            WHERE f.framework_id = :fwid AND m.control_code IS NULL
        """), {"fwid": FRAMEWORK_ID}).fetchone()[0]
    except Exception as e:
        result["errors"].append(f"missing L2 check: {e}")

    # Sample control lookup
    try:
        sample = db.execute(sql_text("""
            SELECT f.control_code, f.control_text,
                   m.applicability, c.audit_questions
            FROM ecc_framework f
            LEFT JOIN ecc_compliance_metadata m
                ON f.framework_id = m.framework_id AND f.control_code = m.control_code
            LEFT JOIN ecc_ai_checkpoints c
                ON f.framework_id = c.framework_id AND f.control_code = c.control_code
            WHERE f.framework_id = :fwid AND f.control_code = '2-2-3-1'
        """), {"fwid": FRAMEWORK_ID}).fetchone()
        if sample:
            result["sample_control"] = {
                "control_code": sample[0],
                "control_text_preview": (sample[1] or "")[:120],
                "applicability": str(sample[2]) if sample[2] else None,
                "has_audit_questions": sample[3] is not None,
            }
    except Exception as e:
        result["errors"].append(f"sample lookup: {e}")

    if result["layer1_count"] == 200:
        result["analyzer_source"] = "structured_ecc_tables"
        result["status"] = (
            "ready"
            if result["layer2_count"] == 200 and result["layer3_count"] == 200
            else "partial"
        )
    elif result["layer1_count"] > 0:
        result["status"] = "partial"
    else:
        result["status"] = "not_loaded"

    return result
