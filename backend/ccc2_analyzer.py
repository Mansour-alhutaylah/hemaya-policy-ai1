"""
ccc2_analyzer.py
CCC-2:2024 structured compliance analysis engine.

Data sources (in priority order):
  L1 — ecc_framework:          Official CCC-2:2024 control text (source of truth)
  L2 — ecc_compliance_metadata + ccc_metadata:  Applicability (CSP/CST), mandatory levels
  L3 — ecc_ai_checkpoints:     AI audit hints (never used as requirements)

Results written to:
  policy_ecc_assessments   — detailed per-control results
  compliance_results       — summary row (for frontend compatibility)
"""

import json
import re
import time
import uuid
import hashlib
import asyncio
from datetime import datetime, timezone
from sqlalchemy import text as sql_text

import backend.ccc2_cache as _ccc2_cache

import backend.checkpoint_analyzer as _ca
from backend.checkpoint_analyzer import (
    call_llm,
    _find_grounded_evidence,
    _attribute_evidence_to_chunk,
)

FRAMEWORK_ID = "CCC-2:2024"
FRAMEWORK_DISPLAY = "Cloud Cybersecurity Controls (CCC-2:2024) — National Cybersecurity Authority (NCA), Saudi Arabia"

CCC2_PROMPT_VERSION = "v2"
CCC2_MODEL = "gpt-4o-mini"

CCC2_VERIFIER_PROMPT = """You assess whether a policy document complies with CCC-2:2024 (Cloud Cybersecurity Controls, National Cybersecurity Authority, Saudi Arabia, 2024).

CCC-2 applies to cloud service providers (CSP) and cloud service tenants (CST):
- CSP controls: obligations on the organization providing cloud services (infrastructure, platform, software).
- CST controls: obligations on the tenant organization that consumes or subscribes to cloud services.
- "both": applies to both CSP and CST roles.

CHECKPOINT TIERS — apply different standards:

CHECKPOINT 1 [L1_official] is the OFFICIAL REGULATORY REQUIREMENT from CCC-2:2024.
  - met=true ONLY if the policy SPECIFICALLY implements this requirement with concrete language
  - Generic phrases ("we follow best practices", "cloud security policies are in place") do NOT satisfy
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
        "cloud", "service", "provider", "tenant", "nca", "ccc",
    }
    words = re.findall(r"[a-z]{4,}", text.lower())
    return [w for w in words if w not in stop][:20]


ACTION_VERBS: dict[str, set[str]] = {
    "document":   {"document", "documented", "record", "recorded", "log", "logged", "maintain", "maintained"},
    "approve":    {"approv", "authoriz", "sign-off", "signed off"},
    "review":     {"review", "audit", "assess", "evaluat", "inspect", "periodic", "annual", "quarterly"},
    "test":       {"test", "tested", "testing", "verif", "validat", "exercise", "simulat"},
    "monitor":    {"monitor", "track", "surveil", "observ", "detect", "alert", "watch"},
    "implement":  {"implement", "enforc", "deploy", "appl", "operat", "activat", "install"},
    "classify":   {"classif", "categori", "label", "tier", "sensitiv"},
    "report":     {"report", "escalat", "notif", "communicat", "inform", "disclose"},
    "train":      {"train", "aware", "educat", "instruct"},
    "retain":     {"retain", "retent", "preserv", "archive", "stor"},
    "update":     {"update", "updat", "revis", "amend", "refresh"},
    "identify":   {"identif", "discover", "detect", "recogniz", "list", "inventori"},
    "encrypt":    {"encrypt", "crypt", "cipher", "tls", "ssl", "https"},
    "isolate":    {"isolat", "segregat", "separat", "network", "segment", "vlan"},
    "backup":     {"backup", "back-up", "recover", "restor", "redundan", "replica"},
}


def _extract_required_actions(control_text: str) -> set[str]:
    t = control_text.lower()
    return {cat for cat, verbs in ACTION_VERBS.items() if any(v in t for v in verbs)}


def _compute_action_coverage(required: set[str], evidence: str) -> tuple[float, set[str], set[str]]:
    if not required:
        return 1.0, set(), set()
    ev = evidence.lower()
    covered = {cat for cat in required if any(v in ev for v in ACTION_VERBS[cat])}
    missing = required - covered
    return len(covered) / len(required), covered, missing


def load_ccc2_controls(db) -> list[dict]:
    rows = db.execute(sql_text("""
        SELECT
            f.control_code,
            f.control_type,
            f.control_text,
            f.source_page,
            f.domain_code,
            f.domain_name,
            f.subdomain_code,
            f.subdomain_name,
            cm.applicability_type,
            cm.ecc_references,
            cm.mandatory_level_1,
            cm.mandatory_level_2,
            cm.mandatory_level_3,
            cm.mandatory_level_4,
            cm.governance_control,
            cm.technical_control,
            cm.operational_control,
            ecm.responsible_party,
            ecm.frequency,
            cp.audit_questions,
            cp.suggested_evidence,
            cp.possible_technical_evidence,
            cp.indicators_of_implementation
        FROM ecc_framework f
        LEFT JOIN ccc_metadata cm
            ON f.framework_id = cm.framework_id AND f.control_code = cm.control_code
        LEFT JOIN ecc_compliance_metadata ecm
            ON f.framework_id = ecm.framework_id AND f.control_code = ecm.control_code
        LEFT JOIN ecc_ai_checkpoints cp
            ON f.framework_id = cp.framework_id AND f.control_code = cp.control_code
        WHERE f.framework_id = :fwid
          AND f.control_type IN ('main_control', 'subcontrol')
        ORDER BY f.control_code
    """), {"fwid": FRAMEWORK_ID}).fetchall()

    controls = []
    for r in rows:
        def _parse_jsonb(val):
            if val is None:
                return []
            if isinstance(val, (list, dict)):
                return val
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return []
            return list(val) if hasattr(val, "__iter__") else []

        audit_qs      = _parse_jsonb(r[19])
        suggested_ev  = _parse_jsonb(r[20])
        tech_ev       = _parse_jsonb(r[21])
        indicators    = _parse_jsonb(r[22])
        ecc_refs      = _parse_jsonb(r[9])

        kw_pool = _extract_keywords(r[2] or "")
        for aq in audit_qs[:3]:
            kw_pool += _extract_keywords(aq)
        for se in suggested_ev[:3]:
            kw_pool += _extract_keywords(se)
        kw_pool = list(dict.fromkeys(kw_pool))[:30]

        applicability_type = str(r[8]) if r[8] else "CSP"

        controls.append({
            "control_code":        r[0],
            "control_type":        str(r[1]) if r[1] else "main_control",
            "control_text":        r[2] or "",
            "source_page":         r[3],
            "domain_code":         r[4] or "",
            "domain_name":         r[5] or "",
            "subdomain_code":      r[6] or "",
            "subdomain_name":      r[7] or "",
            "applicability_type":  applicability_type,
            "ecc_references":      ecc_refs,
            "mandatory_level_1":   bool(r[10]) if r[10] is not None else True,
            "mandatory_level_2":   bool(r[11]) if r[11] is not None else True,
            "mandatory_level_3":   bool(r[12]) if r[12] is not None else True,
            "mandatory_level_4":   bool(r[13]) if r[13] is not None else True,
            "governance_control":  bool(r[14]) if r[14] is not None else False,
            "technical_control":   bool(r[15]) if r[15] is not None else False,
            "operational_control": bool(r[16]) if r[16] is not None else False,
            "responsible_party":   r[17],
            "frequency":           r[18],
            "audit_questions":     audit_qs[:3],
            "suggested_evidence":  suggested_ev[:4],
            "possible_technical_evidence": tech_ev[:3],
            "indicators_of_implementation": indicators[:3],
            "keywords":            kw_pool,
            "l1_loaded":           bool(r[2]),
            "l2_loaded":           r[8] is not None,
            "l3_loaded":           r[19] is not None,
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
    from backend.checkpoint_analyzer import _find_relevant_sections
    from rank_bm25 import BM25Okapi

    control_code   = control["control_code"]
    control_text   = control["control_text"]
    audit_qs       = control["audit_questions"]
    app_type       = control["applicability_type"]
    domain_name    = control["domain_name"]
    subdomain_name = control["subdomain_name"]
    ecc_refs       = control["ecc_references"]

    # Prepend the control code itself to keywords so BM25 and the keyword
    # scorer both rank chunks that explicitly cite the control ID first.
    # CCC-2 control codes contain only digits, hyphens, and single letters
    # so _extract_keywords()'s [a-z]{4,} regex would discard them entirely.
    keywords = [control_code] + list(control["keywords"])

    # Cache lookup
    cache_key = None
    if db is not None and policy_hash:
        retrieval_min_score = getattr(_ca, "RAG_MIN_RELEVANCE_SCORE", 0.10)
        grounding_version   = getattr(_ca, "GROUNDING_VERSION", "v1")
        grounding_sim       = getattr(_ca, "GROUNDING_MIN_SIMILARITY", 0.75)
        cache_key = _ccc2_cache.build_cache_key(
            control_code, policy_hash,
            CCC2_PROMPT_VERSION, CCC2_MODEL,
            retrieval_min_score, grounding_version, grounding_sim,
        )
        cached = _ccc2_cache.lookup(db, cache_key)
        if cached is not None:
            print(f"    [CCC2][{control_code}] cache HIT")
            return cached

    if bm25_index is None and policy_chunks:
        tokenized = [c["text"].lower().split() for c in policy_chunks]
        bm25_index = BM25Okapi(tokenized)

    # ── Pass 1: direct control-ID lookup ────────────────────────────────
    # Find chunks that explicitly name this control code (or any of its
    # subcontrols, e.g. "1-1-P-1" matches "1-1-P-1-1") before BM25.
    # This ensures compliance matrices that cite controls by ID are always
    # included in the GPT prompt regardless of BM25 ranking.
    cc_lower = control_code.lower()
    direct_chunks = [
        c for c in policy_chunks
        if cc_lower in c["text"].lower()
    ]
    direct_text = (
        "\n---\n".join(c["text"] for c in direct_chunks[:4])
        if direct_chunks else ""
    )

    # ── Pass 2: BM25 + keyword retrieval ────────────────────────────────
    focused_text, retrieval_quality, selected_chunks = _find_relevant_sections(
        policy_chunks, control_text, keywords, bm25=bm25_index, offset=0,
        return_selected=True,
    )

    # Merge: prepend direct hits that BM25 may have missed
    if direct_text and direct_text not in focused_text:
        focused_text = direct_text + "\n---\n" + focused_text
        # Merge into selected_chunks for source attribution
        existing_texts = {c["text"] for c in selected_chunks}
        extra = [c for c in direct_chunks[:4] if c["text"] not in existing_texts]
        selected_chunks = extra + selected_chunks

    if diag:
        print(
            f"    [CCC2][DIAG][{control_code}] "
            f"direct_hits={len(direct_chunks)} "
            f"focused_text={len(focused_text)} chars | "
            f"retrieval_quality={retrieval_quality:.3f}"
        )

    app_label = {
        "CSP": "Cloud Service Provider",
        "CST": "Cloud Service Tenant",
        "both": "Cloud Service Provider and Tenant",
    }.get(app_type, app_type)

    ecc_ref_str = (
        f"ECC-2 Cross-References: {', '.join(ecc_refs)}" if ecc_refs else ""
    )

    checkpoints = [
        {
            "checkpoint_index": 1,
            "checkpoint_id":    f"{control_code}-L1",
            "requirement":      control_text,
            "weight":           2.0,
            "source":           "L1_official",
        }
    ]
    for i, aq in enumerate(audit_qs[:3], start=2):
        checkpoints.append({
            "checkpoint_index": i,
            "checkpoint_id":    f"{control_code}-L3-{i}",
            "requirement":      aq,
            "weight":           1.0,
            "source":           "L3_audit_hint",
        })

    cp_lines = "\n".join(
        f"CHECKPOINT {cp['checkpoint_index']} [source={cp['source']}]: {cp['requirement']}"
        for cp in checkpoints
    )
    user_msg = (
        f"Control: {control_code} [{app_type} — {app_label}]\n"
        f"Domain: {domain_name} > {subdomain_name}\n"
        + (f"{ecc_ref_str}\n" if ecc_ref_str else "")
        + f"\n{cp_lines}\n\n"
        f"POLICY TEXT EVIDENCE:\n{focused_text[:12000]}"
    )

    is_gpt_error_fallback = False
    try:
        raw = await call_llm(CCC2_VERIFIER_PROMPT, user_msg)
        if diag:
            print(f"    [CCC2][DIAG][{control_code}] raw GPT response: {raw[:600]}")
        gpt_data = json.loads(raw)
        results = gpt_data.get("checkpoints", [])
    except Exception as e:
        print(f"    [CCC2][{control_code}] GPT error: {e}")
        is_gpt_error_fallback = True
        results = [
            {
                "index":      cp["checkpoint_index"],
                "met":        False,
                "confidence": 0.1,
                "evidence":   f"GPT error: {str(e)[:80]}",
            }
            for cp in checkpoints
        ]

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
                        f"    [CCC2][{control_code}] CP{v.get('index')} "
                        f"GROUNDING REJECTED (sim={sim:.2f})"
                    )
                else:
                    v["evidence"] = actual

    res_map = {v.get("index"): v for v in results}

    l1_r = res_map.get(1, {"met": False, "confidence": 0.1, "evidence": ""})
    l1_met  = bool(l1_r.get("met", False))
    l1_conf = float(l1_r.get("confidence", 0.1))
    l1_ev   = (l1_r.get("evidence") or "").strip()
    _ev_bad = ("no evidence found", "no result", "", "evidence could not be grounded in policy text")
    l1_has_grounded_evidence = l1_met and bool(l1_ev and l1_ev.lower() not in _ev_bad)

    l3_checkpoints = [cp for cp in checkpoints if cp["checkpoint_index"] > 1]
    l3_met_w   = sum(
        cp["weight"]
        for cp in l3_checkpoints
        if res_map.get(cp["checkpoint_index"], {}).get("met", False)
    )
    l3_total_w = sum(cp["weight"] for cp in l3_checkpoints) or 1.0
    l3_ratio   = l3_met_w / l3_total_w

    met_weight  = (2.0 if l1_met else 0.0) + l3_met_w
    total_weight = 2.0 + l3_total_w
    score = (met_weight / total_weight * 100) if total_weight > 0 else 0

    conf_sum = l1_conf * 2.0 + sum(
        float(res_map.get(cp["checkpoint_index"], {}).get("confidence", 0.1)) * cp["weight"]
        for cp in l3_checkpoints
    )
    avg_confidence = conf_sum / total_weight

    best_evidence = l1_ev if l1_has_grounded_evidence else ""
    if not best_evidence:
        for cp in l3_checkpoints:
            r = res_map.get(cp["checkpoint_index"], {})
            if r.get("met"):
                ev = (r.get("evidence") or "").strip()
                if ev and ev.lower() not in ("no evidence found",):
                    best_evidence = ev
                    break

    src_chunk = None
    if best_evidence:
        src_chunk = _attribute_evidence_to_chunk(best_evidence, selected_chunks)
    src_chunk_id      = src_chunk.get("chunk_id")     if src_chunk else None
    src_page_number   = src_chunk.get("page_number")  if src_chunk else None
    src_paragraph_ix  = src_chunk.get("paragraph_index") if src_chunk else None

    required_actions = _extract_required_actions(control_text)
    if l1_has_grounded_evidence and required_actions:
        action_coverage, covered_actions, missing_actions = _compute_action_coverage(
            required_actions, l1_ev
        )
    elif l1_has_grounded_evidence and not required_actions:
        action_coverage  = 1.0
        covered_actions  = set()
        missing_actions  = set()
    else:
        action_coverage  = 0.0
        covered_actions  = set()
        missing_actions  = required_actions

    if not l1_has_grounded_evidence:
        status = "non_compliant"
        status_reason = f"No grounded L1 evidence (l1_met={l1_met}, conf={l1_conf:.2f})"
    elif l1_conf < 0.45:
        status = "non_compliant"
        status_reason = f"L1 evidence too vague (conf={l1_conf:.2f} < 0.45)"
    elif l1_conf >= 0.65 and (action_coverage >= 0.50 or l3_ratio >= 0.67):
        status = "compliant"
        status_reason = (
            f"L1 solid (conf={l1_conf:.2f}), "
            f"action_cov={action_coverage:.2f}, L3_ratio={l3_ratio:.2f}"
        )
    else:
        status = "partial"
        status_reason = (
            f"L1 partial (conf={l1_conf:.2f}), "
            f"action_cov={action_coverage:.2f}, L3_ratio={l3_ratio:.2f}, "
            f"covered={covered_actions} missing={missing_actions}"
        )
        print(
            f"    [CCC2][PARTIAL] {control_code} "
            f"l1_conf={l1_conf:.2f} action_cov={action_coverage:.2f} "
            f"covered={covered_actions} missing={missing_actions}"
        )

    gap_parts = []
    for cp in checkpoints:
        r = res_map.get(cp["checkpoint_index"], {"met": False})
        if not r.get("met"):
            gap_parts.append(cp["requirement"][:120])
    gap_desc = "; ".join(gap_parts) if gap_parts else ""

    print(
        f"    [CCC2][{control_code}] [{app_type}] "
        f"L1_conf={l1_conf:.2f} grounded={'Y' if l1_has_grounded_evidence else 'N'} "
        f"action_cov={action_coverage:.2f} L3_ratio={l3_ratio:.2f} "
        f"quality={retrieval_quality:.2f} -> {status}"
    )

    result = {
        "control_code":              control_code,
        "control_type":              control["control_type"],
        "control_text":              control_text,
        "domain_code":               control["domain_code"],
        "domain_name":               domain_name,
        "subdomain_code":            control["subdomain_code"],
        "subdomain_name":            subdomain_name,
        "applicability_type":        app_type,
        "ecc_references":            ecc_refs,
        "compliance_status":         status,
        "evidence_text":             best_evidence or "No direct evidence found",
        "gap_description":           gap_desc,
        "confidence_score":          round(min(1.0, max(0.0, avg_confidence)), 3),
        "score":                     round(score, 1),
        "retrieval_quality":         round(retrieval_quality, 3),
        "l1_loaded":                 control["l1_loaded"],
        "l2_loaded":                 control["l2_loaded"],
        "l3_loaded":                 control["l3_loaded"],
        "source_tables":             "ecc_framework + ccc_metadata + ecc_ai_checkpoints",
        "evidence_chunk_id":         src_chunk_id,
        "evidence_page_number":      src_page_number,
        "evidence_paragraph_index":  src_paragraph_ix,
        "_l1_conf":                  l1_conf,
        "_l1_grounded":              l1_has_grounded_evidence,
        "_action_cov":               round(action_coverage, 2),
        "sub_results": [
            {
                "source":      cp["source"],
                "requirement": cp["requirement"][:200],
                "met":         bool(res_map.get(cp["checkpoint_index"], {}).get("met", False)),
                "evidence":    res_map.get(cp["checkpoint_index"], {}).get("evidence", ""),
                "confidence":  res_map.get(cp["checkpoint_index"], {}).get("confidence", 0.1),
            }
            for cp in checkpoints
        ],
    }

    # Cache write — never cache GPT error fallbacks
    if db is not None and cache_key is not None and not is_gpt_error_fallback:
        ok = _ccc2_cache.write(
            db, cache_key, control_code, policy_hash,
            CCC2_PROMPT_VERSION, CCC2_MODEL, result,
        )
        if not ok:
            print(f"    [CCC2][{control_code}] cache write failed (non-fatal)")

    return result


def _save_assessment_row(db, policy_id: str, result: dict, framework_id_legacy: str):
    db.execute(sql_text("""
        INSERT INTO policy_ecc_assessments
            (id, policy_id, framework_id, control_code, compliance_status,
             evidence_text, gap_description, confidence_score,
             chunk_id, page_number, paragraph_index,
             assessed_by, assessed_at)
        VALUES
            (:id, :pid, :fwid, :cc, CAST(:cs AS compliance_status_enum),
             :ev, :gap, :conf,
             :ckid, :pgnum, :paridx,
             CAST('AI' AS assessed_by_enum), :at)
        ON CONFLICT (policy_id, control_code)
        DO UPDATE SET
            compliance_status = EXCLUDED.compliance_status,
            evidence_text     = EXCLUDED.evidence_text,
            gap_description   = EXCLUDED.gap_description,
            confidence_score  = EXCLUDED.confidence_score,
            chunk_id          = EXCLUDED.chunk_id,
            page_number       = EXCLUDED.page_number,
            paragraph_index   = EXCLUDED.paragraph_index,
            assessed_at       = EXCLUDED.assessed_at
    """), {
        "id":     str(uuid.uuid4()),
        "pid":    str(policy_id),
        "fwid":   FRAMEWORK_ID,
        "cc":     result["control_code"],
        "cs":     result["compliance_status"],
        "ev":     (result.get("evidence_text") or "")[:4000],
        "gap":    (result.get("gap_description") or "")[:2000],
        "conf":   result["confidence_score"],
        "ckid":   result.get("evidence_chunk_id"),
        "pgnum":  result.get("evidence_page_number"),
        "paridx": result.get("evidence_paragraph_index"),
        "at":     datetime.now(timezone.utc),
    })


async def run_ccc2_analysis(
    db,
    policy_id: str,
    progress_cb=None,
    control_codes=None,
    policy_version_id: str | None = None,
) -> dict:
    """
    Analyze a policy against CCC-2:2024 controls (main_control + subcontrol, 175 rows).

    control_codes:      optional set of control codes to assess (incremental mode).
    policy_version_id:  when provided, reads ONLY that version's chunks.
    """
    def _report(pct: int, stage: str):
        if progress_cb:
            try:
                progress_cb(pct, stage)
            except Exception:
                pass

    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"CCC-2:2024 STRUCTURED ANALYSIS STARTED - policy={policy_id}")
    print(f"{'='*60}")

    _report(12, "CCC-2: Checking policy chunks")

    if policy_version_id:
        _chunk_where  = "policy_version_id = :vid AND embedding IS NOT NULL"
        _chunk_params = {"vid": policy_version_id}
        print(f"  [CCC2] Version-scoped mode: policy_version_id={policy_version_id}")
    else:
        _chunk_where  = "policy_id = :pid AND embedding IS NOT NULL"
        _chunk_params = {"pid": policy_id}

    n_chunks = db.execute(sql_text(
        f"SELECT COUNT(*) FROM policy_chunks WHERE {_chunk_where}"
    ), _chunk_params).fetchone()[0]

    if n_chunks == 0:
        if policy_version_id:
            return {FRAMEWORK_ID: {"error": (
                f"No embedded chunks found for version {policy_version_id}."
            )}}
        print("  [CCC2] Auto-embedding policy chunks...")
        _report(15, "CCC-2: Embedding policy text")
        from backend.checkpoint_analyzer import _auto_embed
        embedded = await _auto_embed(db, policy_id)
        if embedded == 0:
            return {FRAMEWORK_ID: {"error": "No text found in policy. Re-upload the document."}}
        n_chunks = embedded

    if not policy_version_id:
        from backend.checkpoint_analyzer import (
            policy_needs_source_attribution_backfill,
            rechunk_for_source_attribution,
            RechunkError,
        )
        if policy_needs_source_attribution_backfill(db, policy_id):
            print("  [CCC2] Backfill rechunk")
            _report(16, "CCC-2: Rechunking for source attribution")
            try:
                n_chunks = await rechunk_for_source_attribution(db, policy_id)
            except RechunkError as e:
                print(f"  [CCC2] Backfill skipped: {e}")

    print(f"  [CCC2] Policy has {n_chunks} embedded chunks")
    _report(18, "CCC-2: Loading structured controls")

    try:
        controls = load_ccc2_controls(db)
    except Exception as e:
        import traceback as _tb
        print(f"  [CCC2] ERROR loading controls: {e}")
        print(_tb.format_exc())
        return {
            FRAMEWORK_ID: {
                "error": f"CCC-2:2024 structured tables not loaded: {e}."
            }
        }

    if not controls:
        try:
            raw = db.execute(sql_text(
                "SELECT COUNT(*) FROM ecc_framework WHERE framework_id = :fwid"
            ), {"fwid": FRAMEWORK_ID}).fetchone()[0]
            print(f"  [CCC2] load_ccc2_controls returned 0 controls "
                  f"(ecc_framework has {raw} rows for CCC-2:2024)")
        except Exception:
            raw = "unknown"
        return {
            FRAMEWORK_ID: {
                "error": (
                    f"CCC-2:2024 controls not found in ecc_framework (raw count={raw}). "
                    "Run: python data/ccc2/ccc2_import.py"
                )
            }
        }

    if control_codes is not None:
        controls = [c for c in controls if c["control_code"] in control_codes]
        print(f"  [CCC2] Incremental mode: {len(controls)} targeted controls")

    sample   = [c["control_code"] for c in controls[:3]]
    l2_cnt   = sum(1 for c in controls if c["l2_loaded"])
    l3_cnt   = sum(1 for c in controls if c["l3_loaded"])
    csp_cnt  = sum(1 for c in controls if c["applicability_type"] in ("CSP", "both"))
    cst_cnt  = sum(1 for c in controls if c["applicability_type"] in ("CST", "both"))
    print(
        f"  [CCC2] {len(controls)} controls loaded "
        f"(first 3: {sample}) "
        f"L2={l2_cnt}/{len(controls)} L3={l3_cnt}/{len(controls)} "
        f"CSP={csp_cnt} CST={cst_cnt}"
    )
    _report(22, f"CCC-2: Analysing {len(controls)} controls")

    # Load policy chunks
    try:
        _load_where  = "policy_version_id = :vid" if policy_version_id else "policy_id = :pid"
        _load_params = {"vid": policy_version_id} if policy_version_id else {"pid": policy_id}
        chunk_rows = db.execute(sql_text(
            "SELECT chunk_text, COALESCE(classification, 'descriptive'), "
            "       chunk_index, page_number, paragraph_index "
            f"FROM policy_chunks WHERE {_load_where} ORDER BY chunk_index"
        ), _load_params).fetchall()
        policy_chunks = [
            {
                "text": r[0], "classification": r[1],
                "chunk_index": r[2], "page_number": r[3],
                "paragraph_index": r[4],
                "chunk_id": f"{policy_id}_chunk_{r[2]}",
            }
            for r in chunk_rows if r[0]
        ]
    except Exception:
        db.rollback()
        try:
            chunk_rows = db.execute(sql_text(
                "SELECT chunk_text, COALESCE(classification, 'descriptive'), chunk_index "
                f"FROM policy_chunks WHERE {_load_where} ORDER BY chunk_index"
            ), _load_params).fetchall()
            policy_chunks = [
                {
                    "text": r[0], "classification": r[1],
                    "chunk_index": r[2], "page_number": None,
                    "paragraph_index": None,
                    "chunk_id": f"{policy_id}_chunk_{r[2]}",
                }
                for r in chunk_rows if r[0]
            ]
        except Exception:
            db.rollback()
            chunk_rows = db.execute(sql_text(
                "SELECT chunk_text FROM policy_chunks "
                "WHERE policy_id = :pid ORDER BY chunk_index"
            ), {"pid": policy_id}).fetchall()
            policy_chunks = [
                {"text": r[0], "classification": "descriptive",
                 "chunk_index": i, "page_number": None,
                 "paragraph_index": None,
                 "chunk_id": f"{policy_id}_chunk_{i}"}
                for i, r in enumerate(chunk_rows) if r[0]
            ]

    policy_text  = "\n\n".join(c["text"] for c in policy_chunks)
    policy_hash  = hashlib.sha256(policy_text.encode("utf-8")).hexdigest()[:16]
    print(f"  [CCC2] Loaded {len(policy_chunks)} chunks "
          f"({len(policy_text)} chars total policy text, hash={policy_hash})")

    # Build BM25 index once for all controls
    from rank_bm25 import BM25Okapi
    if policy_chunks:
        global_bm25 = BM25Okapi([c["text"].lower().split() for c in policy_chunks])
        print(f"  [CCC2] BM25 index built over {len(policy_chunks)} chunks")
    else:
        global_bm25 = None

    # Ensure legacy frameworks row
    legacy_fw_id = _ensure_framework_row(db)

    sem = asyncio.Semaphore(8)
    results_list: list[dict] = []

    async def _run_one(ctrl, ctrl_idx: int):
        async with sem:
            return await _assess_control(
                ctrl, policy_chunks, policy_text,
                bm25_index=global_bm25,
                diag=(ctrl_idx < 3),
                db=db,
                policy_hash=policy_hash,
            )

    total_ctrl = len(controls)
    batch_size = 8
    for i in range(0, total_ctrl, batch_size):
        batch = controls[i:i + batch_size]
        t1 = time.time()
        batch_results = await asyncio.gather(
            *[_run_one(c, i + j) for j, c in enumerate(batch)]
        )
        results_list.extend(batch_results)
        done    = min(i + batch_size, total_ctrl)
        elapsed = round(time.time() - t1, 1)
        pct     = int(22 + (done / total_ctrl) * 65)
        print(f"  [CCC2] Controls {i+1}-{done}/{total_ctrl} in {elapsed}s")
        _report(pct, f"CCC-2: {done}/{total_ctrl} controls")

    # Confidence distribution
    d_low     = [r for r in results_list if r["_l1_conf"] < 0.45]
    d_mid     = [r for r in results_list if 0.45 <= r["_l1_conf"] < 0.75]
    d_high    = [r for r in results_list if r["_l1_conf"] >= 0.75]
    d_grounded = [r for r in results_list if r["_l1_grounded"]]
    print(f"\n  [CCC2] === CONFIDENCE DISTRIBUTION ({len(results_list)} controls) ===")
    print(f"    L1_conf 0.00-0.44 : {len(d_low):3d}  (-> non_compliant)")
    print(f"    L1_conf 0.45-0.74 : {len(d_mid):3d}  (grounded -> partial candidates)")
    print(f"    L1_conf 0.75-1.00 : {len(d_high):3d}  (grounded -> compliant/partial by action_cov)")
    print(f"    Grounded evidence  : {len(d_grounded):3d}")
    print(f"  [CCC2] =====================================================\n")

    comp  = sum(1 for r in results_list if r["compliance_status"] == "compliant")
    part  = sum(1 for r in results_list if r["compliance_status"] == "partial")
    miss  = sum(1 for r in results_list if r["compliance_status"] == "non_compliant")
    total = len(results_list)
    score = ((comp + part * 0.5) / total * 100) if total else 0
    duration = round(time.time() - t0, 1)

    print(f"\n  [CCC2] RESULT: {round(score, 1)}% "
          f"({comp} compliant, {part} partial, {miss} non-compliant) "
          f"in {duration}s")

    _report(88, "CCC-2: Saving results")

    try:
        for result in results_list:
            _save_assessment_row(db, policy_id, result, legacy_fw_id)
        db.commit()
        print(f"  [CCC2] Saved {len(results_list)} rows to policy_ecc_assessments")
    except Exception as e:
        db.rollback()
        print(f"  [CCC2] WARNING: policy_ecc_assessments save failed: {e}")

    # Group by domain
    by_domain: dict = {}
    for r in results_list:
        dk = r.get("domain_code") or "unknown"
        dn = r.get("domain_name") or dk
        if dk not in by_domain:
            by_domain[dk] = {
                "domain_name":   dn,
                "compliant":     0,
                "partial":       0,
                "non_compliant": 0,
            }
        by_domain[dk][r["compliance_status"]] = by_domain[dk].get(r["compliance_status"], 0) + 1

    # CSP vs CST split (controls that apply to each role)
    csp_results = [r for r in results_list if r["applicability_type"] in ("CSP", "both")]
    cst_results = [r for r in results_list if r["applicability_type"] in ("CST", "both")]

    def _summary(subset):
        c = sum(1 for r in subset if r["compliance_status"] == "compliant")
        p = sum(1 for r in subset if r["compliance_status"] == "partial")
        n = sum(1 for r in subset if r["compliance_status"] == "non_compliant")
        sc = ((c + p * 0.5) / len(subset) * 100) if subset else 0
        return {"total": len(subset), "compliant": c, "partial": p,
                "non_compliant": n, "score": round(sc, 1)}

    verdict = (
        "Compliant"     if score >= 80
        else "Partial"  if score >= 50
        else "Non-Compliant"
    )
    try:
        db.execute(sql_text("""
            INSERT INTO compliance_results
                (id, policy_id, framework_id, compliance_score,
                 controls_covered, controls_partial, controls_missing,
                 status, analyzed_at, analysis_duration, details)
            VALUES
                (:id, :pid, :fwid, :sc, :cov, :par, :mis,
                 :st, :at, :dur, :det)
            ON CONFLICT DO NOTHING
        """), {
            "id":   str(uuid.uuid4()),
            "pid":  policy_id,
            "fwid": legacy_fw_id,
            "st":   verdict,
            "sc":   round(score, 1),
            "cov":  comp,
            "par":  part,
            "mis":  miss,
            "at":   datetime.now(timezone.utc),
            "dur":  duration,
            "det":  json.dumps({
                "framework":       FRAMEWORK_ID,
                "total_controls":  total,
                "compliant":       comp,
                "partial":         part,
                "non_compliant":   miss,
                "csp_controls":    _summary(csp_results),
                "cst_controls":    _summary(cst_results),
                "by_domain":       by_domain,
                "controls": [{
                    "control_code":       r["control_code"],
                    "control_type":       r.get("control_type"),
                    "domain_code":        r.get("domain_code"),
                    "applicability_type": r.get("applicability_type"),
                    "status": (
                        "Compliant"     if r["compliance_status"] == "compliant"
                        else "Partial"  if r["compliance_status"] == "partial"
                        else "Non-Compliant"
                    ),
                    "score":      r["score"],
                    "confidence": r["confidence_score"],
                    "evidence":   r["evidence_text"][:300],
                } for r in results_list],
            }),
        })
        db.commit()
        print(f"  [CCC2] Saved compliance_results summary row")
    except Exception as e:
        db.rollback()
        print(f"  [CCC2] WARNING: compliance_results save failed: {e}")

    # Cache observability
    cache_stats = _ccc2_cache.get_stats(db)
    print(
        f"  [CCC2] Cache stats: "
        f"hits={cache_stats['cache_hits']} "
        f"misses={cache_stats['cache_misses']} "
        f"hit_rate={cache_stats['hit_rate']:.1%} "
        f"write_ok={cache_stats['write_ok']} "
        f"write_fail={cache_stats['write_failures']} "
        f"avg_lookup={cache_stats['avg_lookup_ms']:.1f}ms"
    )

    _report(100, "CCC-2: Complete")

    return {
        FRAMEWORK_ID: {
            "framework":         FRAMEWORK_ID,
            "framework_display": FRAMEWORK_DISPLAY,
            "total_controls":    total,
            "compliant":         comp,
            "partial":           part,
            "non_compliant":     miss,
            "compliance_score":  round(score, 1),
            "csp_controls":      _summary(csp_results),
            "cst_controls":      _summary(cst_results),
            "by_domain":         by_domain,
            "duration_seconds":  duration,
            "data_source":       "structured_db",
            "cache_stats": {
                "hits":          cache_stats["cache_hits"],
                "misses":        cache_stats["cache_misses"],
                "hit_rate":      cache_stats["hit_rate"],
                "write_ok":      cache_stats["write_ok"],
                "write_failures": cache_stats["write_failures"],
            },
            "controls": results_list,
        }
    }


def _ensure_framework_row(db) -> str:
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
        "id":   fwid,
        "name": FRAMEWORK_ID,
        "desc": FRAMEWORK_DISPLAY,
        "ver":  "2024",
    })
    db.commit()
    row = db.execute(sql_text(
        "SELECT id FROM frameworks WHERE name = :n"
    ), {"n": FRAMEWORK_ID}).fetchone()
    return str(row[0])
