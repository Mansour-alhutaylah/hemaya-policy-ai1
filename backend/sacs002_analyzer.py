"""
sacs002_analyzer.py
SACS-002 structured compliance analysis engine.

Data sources (in priority order):
  L1 — ecc_framework:            Official SACS-002 control text (source of truth)
  L2 — ecc_compliance_metadata + sacs002_metadata:  Applicability, section, NIST mapping
  L3 — ecc_ai_checkpoints:       AI audit hints (never used as requirements)

Results written to:
  policy_ecc_assessments   — detailed per-control results
  compliance_results       — summary row (for frontend compatibility)
"""

import json
import re
import time
import uuid
import asyncio
from datetime import datetime, timezone
from sqlalchemy import text as sql_text

from backend.checkpoint_analyzer import call_llm, _find_grounded_evidence
from backend.vector_store import get_embeddings, search_similar_chunks

FRAMEWORK_ID = "SACS-002"
FRAMEWORK_DISPLAY = "Saudi Aramco Third Party Cybersecurity Standard (SACS-002)"

SACS002_VERIFIER_PROMPT = """You assess whether a policy document complies with SACS-002 (Saudi Aramco Third Party Cybersecurity Standard, Feb 2022).

CHECKPOINT TIERS — apply different standards:

CHECKPOINT 1 [L1_official] is the OFFICIAL REGULATORY REQUIREMENT.
  - met=true ONLY if the policy SPECIFICALLY implements this requirement with concrete language
  - Generic phrases ("we follow best practices", "security policies are in place", "we protect data") do NOT satisfy
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
        "third", "party", "must", "saudi", "aramco",
    }
    words = re.findall(r"[a-z]{4,}", text.lower())
    return [w for w in words if w not in stop][:20]


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
    t = control_text.lower()
    return {cat for cat, verbs in ACTION_VERBS.items() if any(v in t for v in verbs)}


def _compute_action_coverage(required: set[str], evidence: str) -> tuple[float, set[str], set[str]]:
    if not required:
        return 1.0, set(), set()
    ev = evidence.lower()
    covered = {cat for cat in required if any(v in ev for v in ACTION_VERBS[cat])}
    missing = required - covered
    ratio = len(covered) / len(required)
    return ratio, covered, missing


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
        "id": fwid,
        "name": FRAMEWORK_ID,
        "desc": FRAMEWORK_DISPLAY,
        "ver": "Feb 2022",
    })
    db.commit()
    row = db.execute(sql_text(
        "SELECT id FROM frameworks WHERE name = :n"
    ), {"n": FRAMEWORK_ID}).fetchone()
    return str(row[0])


def seed_sacs002_if_empty(db) -> int:
    """
    Auto-import SACS-002 from bundled JSON files if ecc_framework has no rows.
    Returns the number of L1 rows now in the database (0 if files are missing).
    Called from startup_seed() so data is always present without a manual import step.
    """
    from pathlib import Path

    count = db.execute(sql_text(
        "SELECT COUNT(*) FROM ecc_framework WHERE framework_id = :fwid"
    ), {"fwid": FRAMEWORK_ID}).fetchone()[0]

    if count > 0:
        return count

    base = Path(__file__).parent.parent / "data" / "sacs002"
    l1_path = base / "sacs002_layer1_official.json"
    l2_path = base / "sacs002_layer2_metadata.json"
    l3_path = base / "sacs002_layer3_ai_checkpoints.json"

    if not l1_path.exists():
        print(f"  [SACS002] Auto-import skipped: {l1_path} not found")
        return 0

    print(f"  [SACS002] Auto-importing from {base} ...")
    l1 = json.load(open(l1_path, encoding="utf-8"))
    l2 = json.load(open(l2_path, encoding="utf-8"))
    l3 = json.load(open(l3_path, encoding="utf-8"))
    l2_map = {r["control_code"]: r for r in l2}

    # L1 — ecc_framework
    for r in l1:
        db.execute(sql_text("""
            INSERT INTO ecc_framework
                (framework_id, domain_code, domain_name, subdomain_code, subdomain_name,
                 control_code, control_type, control_text, parent_control_code,
                 is_ecc2_new, ecc2_change_note, source_page)
            VALUES
                (:fwid, NULL, NULL, NULL, NULL,
                 :cc, 'main_control', :txt, NULL,
                 FALSE, NULL, :pg)
            ON CONFLICT (framework_id, control_code) DO NOTHING
        """), {"fwid": FRAMEWORK_ID, "cc": r["control_code"],
               "txt": r["control_text"], "pg": r.get("source_page")})

    # L2 — ecc_compliance_metadata
    # applicability is NULL for all SACS-002 rows: the shared applicability_enum
    # has ECC-specific values that don't cover SACS-002's section/class scheme.
    # Applicability is stored in sacs002_metadata.section + applicable_classes.
    for r in l2:
        db.execute(sql_text("""
            INSERT INTO ecc_compliance_metadata
                (framework_id, control_code, applicability, applicability_note,
                 responsible_party, frequency, ecc_version_introduced,
                 change_from_ecc1, deleted_in_ecc2)
            VALUES
                (:fwid, :cc, NULL, NULL,
                 :rp, :freq, 'SACS-002',
                 NULL, FALSE)
            ON CONFLICT (framework_id, control_code) DO NOTHING
        """), {"fwid": FRAMEWORK_ID, "cc": r["control_code"],
               "rp": r.get("responsible_party"),
               "freq": r.get("frequency")})

    # L2 — sacs002_metadata (NIST mapping, section, applicability classes)
    for r in l2:
        l1r = next((x for x in l1 if x["control_code"] == r["control_code"]), {})
        db.execute(sql_text("""
            INSERT INTO sacs002_metadata
                (framework_id, control_code, section,
                 nist_function_code, nist_function_name,
                 nist_category_code, nist_category_name,
                 applicable_classes,
                 governance_control, technical_control, operational_control,
                 review_required, approval_required, testing_required,
                 monitoring_required, third_party_assessment)
            VALUES
                (:fwid, :cc, :sec,
                 :fc, :fn, :catc, :catn,
                 CAST(:ac AS jsonb),
                 :gov, :tech, :ops,
                 :rev, :appr, :test,
                 :mon, :tpa)
            ON CONFLICT (framework_id, control_code) DO NOTHING
        """), {
            "fwid": FRAMEWORK_ID,
            "cc":   r["control_code"],
            "sec":  l1r.get("section", "A"),
            "fc":   l1r.get("function_code"),
            "fn":   l1r.get("function_name"),
            "catc": l1r.get("category_code"),
            "catn": l1r.get("category_name"),
            "ac":   json.dumps(l1r.get("applicable_classes", [])),
            "gov":  bool(r.get("governance_control", False)),
            "tech": bool(r.get("technical_control", False)),
            "ops":  bool(r.get("operational_control", False)),
            "rev":  bool(r.get("review_required", False)),
            "appr": bool(r.get("approval_required", False)),
            "test": bool(r.get("testing_required", False)),
            "mon":  bool(r.get("monitoring_required", False)),
            "tpa":  bool(r.get("third_party_assessment", False)),
        })

    # L3 — ecc_ai_checkpoints
    for r in l3:
        db.execute(sql_text("""
            INSERT INTO ecc_ai_checkpoints
                (framework_id, control_code, ai_generated, model_version,
                 audit_questions, suggested_evidence, indicators_of_implementation,
                 maturity_signals, possible_documents, possible_technical_evidence)
            VALUES
                (:fwid, :cc, TRUE, :mv,
                 CAST(:aq AS jsonb), CAST(:se AS jsonb), CAST(:ii AS jsonb),
                 CAST(:ms AS jsonb), CAST(:pd AS jsonb), CAST(:pte AS jsonb))
            ON CONFLICT DO NOTHING
        """), {
            "fwid": FRAMEWORK_ID,
            "cc":   r["control_code"],
            "mv":   r.get("model_version", "claude-sonnet-4-6"),
            "aq":   json.dumps(r.get("audit_questions", [])),
            "se":   json.dumps(r.get("suggested_evidence", [])),
            "ii":   json.dumps(r.get("indicators_of_implementation", [])),
            "ms":   json.dumps(r.get("maturity_signals", {})),
            "pd":   json.dumps(r.get("possible_documents", [])),
            "pte":  json.dumps(r.get("possible_technical_evidence", [])),
        })

    db.commit()
    final_count = db.execute(sql_text(
        "SELECT COUNT(*) FROM ecc_framework WHERE framework_id = :fwid"
    ), {"fwid": FRAMEWORK_ID}).fetchone()[0]
    print(f"  [SACS002] Auto-import complete: {final_count} controls in ecc_framework")
    return final_count


def load_sacs002_controls(db) -> list[dict]:
    rows = db.execute(sql_text("""
        SELECT
            f.control_code,
            f.control_type,
            f.control_text,
            f.source_page,
            s.section,
            s.nist_function_code,
            s.nist_function_name,
            s.nist_category_code,
            s.nist_category_name,
            s.applicable_classes,
            cm.applicability,
            cm.responsible_party,
            cm.frequency,
            c.audit_questions,
            c.suggested_evidence,
            c.possible_technical_evidence,
            c.indicators_of_implementation
        FROM ecc_framework f
        LEFT JOIN sacs002_metadata s
            ON f.framework_id = s.framework_id AND f.control_code = s.control_code
        LEFT JOIN ecc_compliance_metadata cm
            ON f.framework_id = cm.framework_id AND f.control_code = cm.control_code
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
            if isinstance(val, (list, dict)):
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
        applicable_classes = _parse_jsonb(r[9])

        kw_pool = _extract_keywords(r[2] or "")
        for aq in audit_qs[:3]:
            kw_pool += _extract_keywords(aq)
        for se in suggested_ev[:3]:
            kw_pool += _extract_keywords(se)
        kw_pool = list(dict.fromkeys(kw_pool))[:30]

        controls.append({
            "control_code": r[0],
            "control_type": str(r[1]) if r[1] else "main_control",
            "control_text": r[2] or "",
            "source_page": r[3],
            "section": str(r[4]) if r[4] else "A",
            "nist_function_code": r[5],
            "nist_function_name": r[6],
            "nist_category_code": r[7],
            "nist_category_name": r[8],
            "applicable_classes": applicable_classes,
            "applicability": str(r[10]) if r[10] else "all_third_parties",
            "responsible_party": r[11],
            "frequency": r[12],
            "audit_questions": audit_qs[:3],
            "suggested_evidence": suggested_ev[:4],
            "possible_technical_evidence": tech_ev[:3],
            "indicators_of_implementation": indicators[:3],
            "keywords": kw_pool,
            "l1_loaded": bool(r[2]),
            "l2_loaded": r[10] is not None,
            "l3_loaded": r[13] is not None,
        })

    return controls


async def _assess_control(
    control: dict,
    policy_chunks: list,
    policy_text: str,
    bm25_index=None,
    diag: bool = False,
) -> dict:
    """
    bm25_index: pre-built BM25Okapi over policy_chunks — caller should build
                once and pass in to avoid rebuilding the index 92× per run.
    diag:       when True, log focused_text preview and raw GPT response.
    """
    from backend.checkpoint_analyzer import _find_relevant_sections
    from rank_bm25 import BM25Okapi

    control_code = control["control_code"]
    control_text = control["control_text"]
    audit_qs = control["audit_questions"]
    keywords = control["keywords"]

    # Build BM25 only if the caller did not provide a pre-built index
    if bm25_index is None and policy_chunks:
        tokenized = [c["text"].lower().split() for c in policy_chunks]
        bm25_index = BM25Okapi(tokenized)

    focused_text, retrieval_quality = _find_relevant_sections(
        policy_chunks, control_text, keywords, bm25=bm25_index, offset=0
    )

    if diag:
        print(
            f"    [SACS002][DIAG][{control_code}] "
            f"focused_text={len(focused_text)} chars | "
            f"retrieval_quality={retrieval_quality:.3f}"
        )
        print(f"    [SACS002][DIAG][{control_code}] focused_text[:300]: {focused_text[:300]!r}")

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

    cp_lines = "\n".join(
        f"CHECKPOINT {cp['checkpoint_index']} [source={cp['source']}]: {cp['requirement']}"
        for cp in checkpoints
    )
    user_msg = (
        f"Control: {control_code} (Section {control['section']})\n"
        f"NIST: {control['nist_function_code']} — {control['nist_category_code']}\n\n"
        f"{cp_lines}\n\n"
        f"POLICY TEXT EVIDENCE:\n{focused_text[:12000]}"
    )

    try:
        raw = await call_llm(SACS002_VERIFIER_PROMPT, user_msg)
        if diag:
            print(f"    [SACS002][DIAG][{control_code}] raw GPT response: {raw[:600]}")
        gpt_data = json.loads(raw)
        results = gpt_data.get("checkpoints", [])
    except Exception as e:
        print(f"    [SACS002][{control_code}] GPT error: {e}")
        results = [
            {
                "index": cp["checkpoint_index"],
                "met": False,
                "confidence": 0.1,
                "evidence": f"GPT error: {str(e)[:80]}",
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
                        f"    [SACS002][{control_code}] CP{v.get('index')} "
                        f"GROUNDING REJECTED (sim={sim:.2f})"
                    )
                else:
                    v["evidence"] = actual

    res_map = {v.get("index"): v for v in results}

    l1_r = res_map.get(1, {"met": False, "confidence": 0.1, "evidence": ""})
    l1_met = bool(l1_r.get("met", False))
    l1_conf = float(l1_r.get("confidence", 0.1))
    l1_ev = (l1_r.get("evidence") or "").strip()
    _ev_bad = ("no evidence found", "no result", "", "evidence could not be grounded in policy text")
    l1_has_grounded_evidence = l1_met and bool(l1_ev and l1_ev.lower() not in _ev_bad)

    l3_checkpoints = [cp for cp in checkpoints if cp["checkpoint_index"] > 1]
    l3_met_w = sum(
        cp["weight"]
        for cp in l3_checkpoints
        if res_map.get(cp["checkpoint_index"], {}).get("met", False)
    )
    l3_total_w = sum(cp["weight"] for cp in l3_checkpoints) or 1.0
    l3_ratio = l3_met_w / l3_total_w

    met_weight = (2.0 if l1_met else 0.0) + l3_met_w
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

    required_actions = _extract_required_actions(control_text)
    if l1_has_grounded_evidence and required_actions:
        action_coverage, covered_actions, missing_actions = _compute_action_coverage(
            required_actions, l1_ev
        )
    elif l1_has_grounded_evidence and not required_actions:
        action_coverage = 1.0
        covered_actions = set()
        missing_actions = set()
    else:
        action_coverage = 0.0
        covered_actions = set()
        missing_actions = required_actions

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
            f"    [SACS002][PARTIAL] {control_code} "
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
        f"    [SACS002][{control_code}] "
        f"L1_conf={l1_conf:.2f} grounded={'Y' if l1_has_grounded_evidence else 'N'} "
        f"action_cov={action_coverage:.2f} L3_ratio={l3_ratio:.2f} "
        f"quality={retrieval_quality:.2f} -> {status}"
    )

    return {
        "control_code": control_code,
        "control_type": control["control_type"],
        "control_text": control_text,
        "section": control["section"],
        "nist_category_code": control["nist_category_code"],
        "compliance_status": status,
        "evidence_text": best_evidence or "No direct evidence found",
        "gap_description": gap_desc,
        "confidence_score": round(min(1.0, max(0.0, avg_confidence)), 3),
        "score": round(score, 1),
        "retrieval_quality": round(retrieval_quality, 3),
        "l1_loaded": control["l1_loaded"],
        "l2_loaded": control["l2_loaded"],
        "l3_loaded": control["l3_loaded"],
        "source_tables": "ecc_framework + sacs002_metadata + ecc_ai_checkpoints",
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


async def run_sacs002_analysis(db, policy_id: str, progress_cb=None) -> dict:
    """
    Main entry point: analyze a policy against all 92 SACS-002 controls.
    Returns a summary dict keyed by FRAMEWORK_ID.
    """
    def _report(pct: int, stage: str):
        if progress_cb:
            try:
                progress_cb(pct, stage)
            except Exception:
                pass

    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"SACS-002 STRUCTURED ANALYSIS STARTED - policy={policy_id}")
    print(f"{'='*60}")

    _report(12, "SACS-002: Checking policy chunks")

    n_chunks = db.execute(sql_text(
        "SELECT COUNT(*) FROM policy_chunks "
        "WHERE policy_id = :pid AND embedding IS NOT NULL"
    ), {"pid": policy_id}).fetchone()[0]

    if n_chunks == 0:
        print("  [SACS002] Auto-embedding policy chunks...")
        _report(15, "SACS-002: Embedding policy text")
        from backend.checkpoint_analyzer import _auto_embed
        embedded = await _auto_embed(db, policy_id)
        if embedded == 0:
            return {FRAMEWORK_ID: {"error": "No text found in policy. Re-upload the document."}}
        n_chunks = embedded

    print(f"  [SACS002] Policy has {n_chunks} embedded chunks")
    _report(18, "SACS-002: Loading structured controls")

    try:
        controls = load_sacs002_controls(db)
    except Exception as e:
        import traceback as _tb
        print(f"  [SACS002] ERROR loading controls: {e}")
        print(_tb.format_exc())
        return {
            FRAMEWORK_ID: {
                "error": (
                    f"SACS-002 structured tables not loaded: {e}. "
                    "Server restart should auto-import the data."
                )
            }
        }

    if not controls:
        # Diagnostic: count raw rows in ecc_framework to confirm data absence
        try:
            raw = db.execute(sql_text(
                "SELECT COUNT(*) FROM ecc_framework WHERE framework_id = :fwid"
            ), {"fwid": FRAMEWORK_ID}).fetchone()[0]
            print(f"  [SACS002] load_sacs002_controls returned 0 controls "
                  f"(ecc_framework has {raw} rows for SACS-002). "
                  f"Attempting inline seed...")
        except Exception:
            raw = "unknown"
            print(f"  [SACS002] load_sacs002_controls returned 0 controls; "
                  f"ecc_framework row count unknown.")
        # Attempt inline seed so the current request can still proceed
        try:
            n = seed_sacs002_if_empty(db)
            if n > 0:
                controls = load_sacs002_controls(db)
                print(f"  [SACS002] Inline seed loaded {n} controls; "
                      f"proceeding with {len(controls)} controls")
        except Exception as seed_err:
            print(f"  [SACS002] Inline seed failed: {seed_err}")
        if not controls:
            return {
                FRAMEWORK_ID: {
                    "error": (
                        "SACS-002 controls not found in ecc_framework "
                        f"(raw count={raw}). "
                        "Restart the server to trigger auto-import."
                    )
                }
            }

    sample = [c["control_code"] for c in controls[:3]]
    l2_loaded = sum(1 for c in controls if c["l2_loaded"])
    l3_loaded = sum(1 for c in controls if c["l3_loaded"])
    print(f"  [SACS002] {len(controls)} controls loaded "
          f"(first 3: {sample}) "
          f"L2={l2_loaded}/{len(controls)} L3={l3_loaded}/{len(controls)}")
    _report(22, f"SACS-002: Analysing {len(controls)} controls")

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
    print(f"  [SACS002] Loaded {len(policy_chunks)} chunks "
          f"({len(policy_text)} chars total policy text)")

    # Build BM25 index ONCE over the policy corpus.
    # Previously rebuilt inside _assess_control for every control (92×).
    # The index depends only on policy_chunks, not on the control being assessed.
    from rank_bm25 import BM25Okapi
    if policy_chunks:
        global_bm25 = BM25Okapi([c["text"].lower().split() for c in policy_chunks])
        print(f"  [SACS002] BM25 index built over {len(policy_chunks)} chunks")
    else:
        global_bm25 = None

    legacy_fw_id = _ensure_framework_row(db)

    sem = asyncio.Semaphore(8)
    results_list: list[dict] = []

    async def _run_one(ctrl, ctrl_idx: int):
        async with sem:
            return await _assess_control(
                ctrl, policy_chunks, policy_text,
                bm25_index=global_bm25,
                diag=(ctrl_idx < 3),  # detailed logs for first 3 controls only
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
        done = min(i + batch_size, total_ctrl)
        elapsed = round(time.time() - t1, 1)
        pct = int(22 + (done / total_ctrl) * 65)
        print(f"  [SACS002] Controls {i+1}-{done}/{total_ctrl} in {elapsed}s")
        _report(pct, f"SACS-002: {done}/{total_ctrl} controls")

    d_low = [r for r in results_list if r["_l1_conf"] < 0.45]
    d_mid = [r for r in results_list if 0.45 <= r["_l1_conf"] < 0.75]
    d_high = [r for r in results_list if r["_l1_conf"] >= 0.75]
    d_grounded = [r for r in results_list if r["_l1_grounded"]]
    print(f"\n  [SACS002] === CONFIDENCE DISTRIBUTION ({len(results_list)} controls) ===")
    print(f"    L1_conf 0.00-0.44 : {len(d_low):3d}  (-> non_compliant)")
    print(f"    L1_conf 0.45-0.74 : {len(d_mid):3d}  (grounded -> partial candidates)")
    print(f"    L1_conf 0.75-1.00 : {len(d_high):3d}  (grounded -> compliant/partial by action_cov)")
    print(f"    Grounded evidence  : {len(d_grounded):3d}")
    print(f"  [SACS002] =====================================================\n")

    comp = sum(1 for r in results_list if r["compliance_status"] == "compliant")
    part = sum(1 for r in results_list if r["compliance_status"] == "partial")
    miss = sum(1 for r in results_list if r["compliance_status"] == "non_compliant")
    total = len(results_list)
    score = ((comp + part * 0.5) / total * 100) if total else 0
    duration = round(time.time() - t0, 1)

    print(f"\n  [SACS002] RESULT: {round(score, 1)}% "
          f"({comp} compliant, {part} partial, {miss} non-compliant) "
          f"in {duration}s")

    _report(88, "SACS-002: Saving results")

    try:
        for result in results_list:
            _save_assessment_row(db, policy_id, result, legacy_fw_id)
        db.commit()
        print(f"  [SACS002] Saved {len(results_list)} rows to policy_ecc_assessments")
    except Exception as e:
        db.rollback()
        print(f"  [SACS002] WARNING: policy_ecc_assessments save failed: {e}")

    # Summary by NIST function
    by_function: dict = {}
    for r in results_list:
        fn = r.get("nist_category_code") or "unknown"
        if fn not in by_function:
            by_function[fn] = {"compliant": 0, "partial": 0, "non_compliant": 0}
        by_function[fn][r["compliance_status"]] = by_function[fn].get(r["compliance_status"], 0) + 1

    # Section split
    sec_a = [r for r in results_list if r.get("section") == "A"]
    sec_b = [r for r in results_list if r.get("section") == "B"]

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
            "det": json.dumps({
                "framework": FRAMEWORK_ID,
                "total_controls": total,
                "compliant": comp,
                "partial": part,
                "non_compliant": miss,
                "section_a_count": len(sec_a),
                "section_b_count": len(sec_b),
                "by_nist_category": by_function,
                "controls": [{
                    "control_code": r["control_code"],
                    "section": r.get("section"),
                    "nist_category": r.get("nist_category_code"),
                    "status": (
                        "Compliant" if r["compliance_status"] == "compliant"
                        else "Partial" if r["compliance_status"] == "partial"
                        else "Non-Compliant"
                    ),
                    "score": r["score"],
                    "confidence": r["confidence_score"],
                    "evidence": r["evidence_text"][:300],
                } for r in results_list],
            }),
        })
        db.commit()
        print(f"  [SACS002] Saved compliance_results summary row")
    except Exception as e:
        db.rollback()
        print(f"  [SACS002] WARNING: compliance_results save failed: {e}")

    _report(100, "SACS-002: Complete")

    return {
        FRAMEWORK_ID: {
            "framework": FRAMEWORK_ID,
            "framework_display": FRAMEWORK_DISPLAY,
            "total_controls": total,
            "compliant": comp,
            "partial": part,
            "non_compliant": miss,
            "compliance_score": round(score, 1),
            "section_a": {
                "total": len(sec_a),
                "compliant": sum(1 for r in sec_a if r["compliance_status"] == "compliant"),
                "partial": sum(1 for r in sec_a if r["compliance_status"] == "partial"),
                "non_compliant": sum(1 for r in sec_a if r["compliance_status"] == "non_compliant"),
            },
            "section_b": {
                "total": len(sec_b),
                "compliant": sum(1 for r in sec_b if r["compliance_status"] == "compliant"),
                "partial": sum(1 for r in sec_b if r["compliance_status"] == "partial"),
                "non_compliant": sum(1 for r in sec_b if r["compliance_status"] == "non_compliant"),
            },
            "by_nist_category": by_function,
            "duration_seconds": duration,
            "data_source": "structured_db",
            "controls": results_list,
        }
    }
