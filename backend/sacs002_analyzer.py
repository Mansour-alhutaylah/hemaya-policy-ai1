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
import hashlib
import asyncio
from datetime import datetime, timezone
from sqlalchemy import text as sql_text

import backend.sacs002_cache as _sacs_cache

import backend.checkpoint_analyzer as _ca
from backend.checkpoint_analyzer import (
    call_llm,
    _find_grounded_evidence,
    _attribute_evidence_to_chunk,
)
from backend.vector_store import get_embeddings, search_similar_chunks

FRAMEWORK_ID = "SACS-002"
FRAMEWORK_DISPLAY = "Saudi Aramco Third Party Cybersecurity Standard (SACS-002)"

# Phase G.2 verification cache — cache_key invariants.
# Bump SACS002_PROMPT_VERSION whenever the verifier prompt, the action
# coverage logic, the L3 ratio thresholds, or any other scoring rule
# in this module changes. Bumping invalidates every cached row, so the
# next analysis re-runs through GPT and writes fresh entries.
SACS002_PROMPT_VERSION = "v3"  # bumped: Phase 3 reranking + neighbor expansion + section boost
SACS002_MODEL = "gpt-4o-mini"

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


# ──────────────────────────────────────────────────────────────────────────
# SACS-002 dedicated retrieval pipeline (Phase 1+2).
# Uses synonym expansion + top_k=15 + hybrid BM25/vector RRF.
# Completely isolated from the ECC-2 analysis path.
# ──────────────────────────────────────────────────────────────────────────

SACS002_SYNONYMS: dict[str, list[str]] = {
    "mfa":              ["multi-factor authentication", "two-factor", "multifactor", "2fa"],
    "2fa":              ["multi-factor authentication", "mfa", "two-factor"],
    "siem":             ["security information and event management", "centralized logging",
                         "log aggregation", "log management", "event management"],
    "waf":              ["web application firewall", "application firewall"],
    "iam":              ["identity and access management", "access control", "identity management"],
    "dlp":              ["data loss prevention", "data leakage prevention"],
    "ids":              ["intrusion detection system", "intrusion prevention system", "ips"],
    "ips":              ["intrusion prevention system", "intrusion detection", "ids"],
    "vpn":              ["virtual private network", "secure tunnel", "encrypted connection"],
    "soc":              ["security operations center", "security operations"],
    "pki":              ["public key infrastructure", "certificate authority", "digital certificate"],
    "rbac":             ["role-based access control", "role based access control", "permissions"],
    "patch":            ["vulnerability management", "software update", "security update", "patching"],
    "backup":           ["data backup", "business continuity", "disaster recovery", "data recovery"],
    "encrypt":          ["encryption", "cryptography", "aes", "tls", "ssl", "https"],
    "encryption":       ["encrypt", "cryptography", "aes", "tls", "ssl"],
    "firewall":         ["network firewall", "perimeter security", "packet filtering"],
    "pentest":          ["penetration test", "penetration testing", "vulnerability assessment"],
    "incident":         ["incident response", "security incident", "breach response"],
    "audit":            ["audit log", "audit trail", "activity log", "event log", "logging"],
    "password":         ["passphrase", "credential", "authentication credential"],
    "privileged":       ["privileged access", "admin access", "elevated privilege", "superuser"],
    "vulnerability":    ["cve", "security weakness", "security exposure", "risk assessment"],
    "monitoring":       ["monitor", "surveillance", "detection", "alerting", "siem"],
    "malware":          ["antivirus", "anti-malware", "endpoint protection", "edr"],
    "classification":   ["data sensitivity", "information classification", "data labeling", "data tier"],
    "access control":   ["rbac", "authorization", "permissions", "access rights", "least privilege"],
    "third party":      ["vendor", "supplier", "contractor", "subcontractor", "outsourced"],
    "awareness":        ["training", "education", "security training", "user awareness"],
    "configuration":    ["hardening", "baseline", "secure configuration", "config management"],
    "asset":            ["inventory", "asset management", "asset register", "hardware inventory"],
}


def _sacs002_expand_query(keywords: list[str], control_text: str) -> list[str]:
    """Expand BM25 query keywords with SACS-002 cybersecurity synonyms."""
    text_lower = control_text.lower()
    expanded = list(keywords)
    seen = set(k.lower() for k in keywords)
    for key, synonyms in SACS002_SYNONYMS.items():
        if key in text_lower or any(s in text_lower for s in synonyms[:2]):
            for s in synonyms:
                if s not in seen:
                    expanded.append(s)
                    seen.add(s)
    return expanded


def _sacs002_retrieve(
    chunks: list[dict],
    control_text: str,
    expanded_kw: list[str],
    bm25,
    top_k: int = 15,
) -> tuple:
    """BM25+keyword retrieval with expanded synonyms and configurable top_k."""
    if not chunks:
        return "", 0.0, []

    kw_scores = []
    for c in chunks:
        score = 0
        text_lower = c["text"].lower()
        for kw in expanded_kw:
            if kw.lower() in text_lower:
                score += 3
        if c.get("classification") == "mandatory":
            score += 4
        elif c.get("classification") == "advisory":
            score += 1
        kw_scores.append(score)

    query_tokens = (control_text + " " + " ".join(expanded_kw)).lower().split()
    bm25_raw = bm25.get_scores(query_tokens)

    max_kw = max(kw_scores) or 1
    max_bm25 = max(bm25_raw) or 1
    scored = [
        (0.5 * kw_scores[i] / max_kw + 0.5 * bm25_raw[i] / max_bm25, chunks[i])
        for i in range(len(chunks))
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = scored[:top_k]
    quality = selected[0][0] if selected else 0.0
    selected_chunks = [s[1] for s in selected]
    return "\n---\n".join(c["text"] for c in selected_chunks), quality, selected_chunks


def _sacs002_vector_search(db, embedding, policy_id, policy_version_id=None, top_k=20):
    """pgvector cosine search scoped to a policy (or specific version)."""
    import json as _json
    emb_str = _json.dumps(embedding)
    if policy_version_id:
        sql = (
            "SELECT chunk_index, 1-(embedding<=>cast(:emb as vector)) AS sim "
            "FROM policy_chunks "
            "WHERE embedding IS NOT NULL AND policy_version_id = :vid "
            "ORDER BY embedding <=> cast(:emb as vector) LIMIT :top_k"
        )
        params = {"emb": emb_str, "vid": policy_version_id, "top_k": top_k}
    else:
        sql = (
            "SELECT chunk_index, 1-(embedding<=>cast(:emb as vector)) AS sim "
            "FROM policy_chunks "
            "WHERE embedding IS NOT NULL AND policy_id = :pid "
            "ORDER BY embedding <=> cast(:emb as vector) LIMIT :top_k"
        )
        params = {"emb": emb_str, "pid": policy_id, "top_k": top_k}
    rows = db.execute(sql_text(sql), params).fetchall()
    return [{"chunk_index": int(r[0]), "similarity": float(r[1])} for r in rows]


def _sacs002_hybrid_retrieve(
    chunks: list[dict],
    control_text: str,
    expanded_kw: list[str],
    bm25,
    vec_results: list[dict],
    top_k: int = 15,
    rrf_k: int = 60,
) -> tuple:
    """Reciprocal Rank Fusion over BM25 and pgvector results."""
    if not chunks:
        return "", 0.0, []

    kw_scores = []
    for c in chunks:
        score = 0
        text_lower = c["text"].lower()
        for kw in expanded_kw:
            if kw.lower() in text_lower:
                score += 3
        if c.get("classification") == "mandatory":
            score += 4
        kw_scores.append(score)

    query_tokens = (control_text + " " + " ".join(expanded_kw)).lower().split()
    bm25_raw = bm25.get_scores(query_tokens)

    max_kw = max(kw_scores) or 1
    max_bm25 = max(bm25_raw) or 1
    bm25_combined = [
        0.5 * kw_scores[i] / max_kw + 0.5 * bm25_raw[i] / max_bm25
        for i in range(len(chunks))
    ]
    bm25_order = sorted(range(len(chunks)), key=lambda i: bm25_combined[i], reverse=True)
    bm25_rank = {idx: rank for rank, idx in enumerate(bm25_order)}

    # Map vec_results chunk_index back to list position
    cidx_to_pos = {c.get("chunk_index", -1): i for i, c in enumerate(chunks)}
    vec_rank: dict[int, int] = {}
    for v_rank, vr in enumerate(vec_results):
        pos = cidx_to_pos.get(vr.get("chunk_index", -1))
        if pos is not None:
            vec_rank[pos] = v_rank

    n = len(chunks)
    rrf_scores = []
    for i in range(n):
        b_r = bm25_rank.get(i, n)
        v_r = vec_rank.get(i, n)
        rrf = 1.0 / (rrf_k + b_r) + 1.0 / (rrf_k + v_r)
        rrf_scores.append((rrf, chunks[i]))

    rrf_scores.sort(key=lambda x: x[0], reverse=True)
    selected = rrf_scores[:top_k]
    quality = min(1.0, selected[0][0] * rrf_k / 2.0) if selected else 0.0
    selected_chunks = [s[1] for s in selected]
    return "\n---\n".join(c["text"] for c in selected_chunks), quality, selected_chunks


# ──────────────────────────────────────────────────────────────────────────
# Phase 3: SACS-002 reranking + neighbor expansion + section-aware boosting.
# Completely isolated from ECC-2. Zero new hard dependencies — BAAI model
# is optional and gated by SACS002_USE_RERANKER_MODEL=true env var.
# Default reranker: single GPT-4o-mini call that scores all 20 candidates.
# ──────────────────────────────────────────────────────────────────────────

import os as _os

# Reranking on/off. Disable in prod if cost matters: SACS002_RERANK_ENABLED=false
SACS002_RERANK_ENABLED = _os.getenv("SACS002_RERANK_ENABLED", "true").lower() == "true"
# Skip rerank when hybrid quality already exceeds this (obviously good retrieval)
_RERANK_SKIP_THRESHOLD = 0.85

# Lazy-loaded BAAI cross-encoder (requires `sentence-transformers`).
# Enable via: SACS002_USE_RERANKER_MODEL=true
_RERANKER_MODEL = None
_RERANKER_ATTEMPTED = False

# Control code → section-heading keywords for chunk boosting.
# Rules that keep false-positive rate low:
#   1. Every entry has a non-empty control_codes set — no broad "fire for all" entries.
#   2. Keywords are multi-word phrases, not single words. Single words like "monitoring",
#      "incident", "encryption" appear in almost every security-policy chunk and would
#      cause section_boost=Y for the majority of controls, defeating the purpose.
#   3. Boost value is +0.10 (additive, not multiplicative) — a nudge, not a takeover.
SACS002_SECTION_MAP: list[tuple[list[str], frozenset]] = [
    (
        ["incident response", "incident management", "security incident",
         "breach response", "forensic investigation", "incident reporting procedure",
         "incident handling"],
        frozenset({"TPC-23", "TPC-88", "TPC-89", "TPC-90"}),
    ),
    (
        ["siem", "centralized logging", "log management system", "audit log retention",
         "security event monitoring", "log review procedure", "log aggregation",
         "security operations center monitoring"],
        frozenset(f"TPC-{n}" for n in range(75, 88)),
    ),
    (
        ["identity and access management", "privileged access management",
         "role-based access control", "account lifecycle management",
         "access review procedure", "least privilege policy",
         "multi-factor authentication policy", "user provisioning"],
        frozenset({f"TPC-{n}" for n in range(2, 7)} | {f"TPC-{n}" for n in range(32, 46)}),
    ),
    (
        ["data encryption policy", "encryption key management", "data classification policy",
         "data at rest encryption", "transport layer security policy",
         "cryptographic controls", "sensitive data handling procedure"],
        frozenset(f"TPC-{n}" for n in range(50, 60)),
    ),
    (
        ["vulnerability management program", "penetration testing policy",
         "patch management procedure", "security assessment schedule",
         "cve remediation process", "vulnerability scanning procedure"],
        frozenset({"TPC-27", "TPC-28", "TPC-29", "TPC-85", "TPC-91"}),
    ),
    (
        ["business continuity plan", "disaster recovery plan", "backup procedure",
         "recovery time objective", "data backup policy", "rto", "rpo",
         "business continuity management", "backup and recovery"],
        frozenset(f"TPC-{n}" for n in range(64, 71)),
    ),
    (
        ["email security policy", "anti-phishing controls", "email filtering policy",
         "email gateway configuration", "phishing prevention", "spam filtering policy"],
        frozenset(f"TPC-{n}" for n in range(13, 18)),
    ),
    (
        ["application security policy", "secure development lifecycle",
         "cloud security policy", "api security controls", "web application firewall policy",
         "secure coding standard", "sdlc security"],
        frozenset(
            {f"TPC-{n}" for n in range(60, 64)} |
            {f"TPC-{n}" for n in range(72, 75)} |
            {"TPC-79", "TPC-92"}
        ),
    ),
]

# Boost magnitude: additive nudge to the combined score, not a takeover.
_SECTION_BOOST_VALUE = 0.10


def _sacs002_section_boost(chunk_text: str, control_code: str) -> tuple[float, str]:
    """Return (boost, triggering_keyword).

    Boost is +0.10 when the chunk content contains a section-specific phrase
    AND the control belongs to that section's mapped code set.
    Returns (0.0, "") when no match — callers must unpack both values.
    """
    text_sample = chunk_text.lower()[:800]
    for section_kws, control_codes in SACS002_SECTION_MAP:
        if control_code not in control_codes:
            continue
        for kw in section_kws:
            if kw in text_sample:
                return _SECTION_BOOST_VALUE, kw
    return 0.0, ""


def _sacs002_expand_neighbors(
    selected_chunks: list[dict],
    all_chunks: list[dict],
    window: int = 1,
) -> list[dict]:
    """Add preceding and following chunks to avoid evidence split across boundaries.

    For each selected chunk at index i, includes chunks i-window … i+window.
    Result is sorted by chunk_index (document order) and deduplicated.
    """
    chunk_by_idx = {c.get("chunk_index", -1): c for c in all_chunks}
    seen: set[int] = set()
    result: list[tuple[int, dict]] = []
    for c in selected_chunks:
        base_idx = c.get("chunk_index", -1)
        for offset in range(-window, window + 1):
            idx = base_idx + offset
            if idx >= 0 and idx not in seen:
                neighbor = chunk_by_idx.get(idx)
                if neighbor:
                    seen.add(idx)
                    result.append((idx, neighbor))
    result.sort(key=lambda x: x[0])
    return [c for _, c in result]


_SACS002_RERANKER_PROMPT = """\
You are a compliance evidence reranker for SACS-002 (Saudi Aramco Third Party Cybersecurity Standard).

Given a control requirement and numbered candidate policy chunks, rank by how well each chunk supports the control.

Score each chunk on:
1. Direct evidence of the control requirement (implementation, not just mention)
2. Operational wording — the organization DOES this, not just says it will
3. Monitoring / review cadence (annual, quarterly, periodic)
4. Ownership / responsibility (who owns this control)
5. Semantic match even when exact wording differs (e.g. "two-factor" = "MFA")

Return ONLY valid JSON — no markdown, no explanation:
{"top": [<0-based indices of best 8 chunks, most relevant first>]}"""


async def _sacs002_llm_rerank(
    control_text: str,
    candidates: list[dict],
    control_code: str = "",
) -> list[dict]:
    """Rerank up to 20 candidate chunks with one GPT call.

    Sends truncated chunk previews (200 chars each) to keep token cost low.
    Returns candidates reordered by GPT relevance score.
    On any failure, returns the original order unchanged.
    """
    if not candidates:
        return candidates

    chunk_lines = "\n".join(
        f"[{i}] {c['text'][:200].strip()}"
        for i, c in enumerate(candidates)
    )
    user_msg = (
        f"Control {control_code}: {control_text[:300]}\n\n"
        f"CANDIDATE CHUNKS:\n{chunk_lines}"
    )
    try:
        raw = await call_llm(_SACS002_RERANKER_PROMPT, user_msg)
        data = json.loads(raw)
        indices = data.get("top", [])
        if not isinstance(indices, list):
            return candidates
        # Rebuild ordered list: ranked first, then any remainder
        seen: set[int] = set()
        reranked: list[dict] = []
        for idx in indices:
            if isinstance(idx, int) and 0 <= idx < len(candidates) and idx not in seen:
                reranked.append(candidates[idx])
                seen.add(idx)
        for i, c in enumerate(candidates):
            if i not in seen:
                reranked.append(c)
        return reranked
    except Exception as _e:
        return candidates  # silent fallback: keep original order


def _sacs002_try_model_rerank(
    control_text: str,
    candidates: list[dict],
) -> list[dict] | None:
    """Attempt BAAI/bge-reranker-v2-m3 cross-encoder reranking.

    Returns reordered candidates, or None if the model is unavailable.
    Requires: pip install sentence-transformers
    Enable:   SACS002_USE_RERANKER_MODEL=true env var
    """
    global _RERANKER_MODEL, _RERANKER_ATTEMPTED
    if not _os.getenv("SACS002_USE_RERANKER_MODEL", "false").lower() == "true":
        return None
    if not _RERANKER_ATTEMPTED:
        _RERANKER_ATTEMPTED = True
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
            _RERANKER_MODEL = CrossEncoder(
                "BAAI/bge-reranker-v2-m3",
                max_length=512,
                device="cpu",
            )
            print("  [SACS002] BAAI/bge-reranker-v2-m3 loaded")
        except Exception as _load_err:
            print(f"  [SACS002] BAAI reranker unavailable: {_load_err}")
            _RERANKER_MODEL = None
    if _RERANKER_MODEL is None:
        return None
    try:
        pairs = [(control_text, c["text"][:400]) for c in candidates]
        scores = _RERANKER_MODEL.predict(pairs)
        reranked = [c for _, c in sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)]
        return reranked
    except Exception as _score_err:
        print(f"  [SACS002] BAAI rerank scoring failed: {_score_err}")
        return None


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
    db=None,
    policy_hash: str | None = None,
    control_embedding=None,
    policy_id: str | None = None,
    policy_version_id: str | None = None,
) -> dict:
    """
    bm25_index:        pre-built BM25Okapi — build once, pass to avoid 92× rebuilds.
    diag:              log focused_text preview and raw GPT response for first controls.
    db, policy_hash:   cache read/write via sacs002_verification_cache.
    control_embedding: pre-computed OpenAI embedding for this control's text.
                       When provided, enables hybrid BM25+vector RRF retrieval (Phase 2).
    policy_id, policy_version_id: used for pgvector scoped search.
    """
    from rank_bm25 import BM25Okapi

    control_code = control["control_code"]
    control_text = control["control_text"]
    audit_qs = control["audit_questions"]
    keywords = control["keywords"]

    # ── Phase G.2: cache lookup ──────────────────────────────────────────
    # All cache I/O goes through sacs002_cache.py which handles rollback,
    # TTL filtering, stats, and error swallowing in one place.
    cache_key = None
    if db is not None and policy_hash:
        retrieval_min_score = getattr(_ca, "RAG_MIN_RELEVANCE_SCORE", 0.10)
        grounding_version   = getattr(_ca, "GROUNDING_VERSION", "v1")
        grounding_sim       = getattr(_ca, "GROUNDING_MIN_SIMILARITY", 0.75)
        cache_key = _sacs_cache.build_cache_key(
            control_code, policy_hash,
            SACS002_PROMPT_VERSION, SACS002_MODEL,
            retrieval_min_score, grounding_version, grounding_sim,
        )
        cached = _sacs_cache.lookup(db, cache_key)
        if cached is not None:
            print(f"    [SACS002][{control_code}] cache HIT")
            return cached

    # Build BM25 only if the caller did not provide a pre-built index
    if bm25_index is None and policy_chunks:
        tokenized = [c["text"].lower().split() for c in policy_chunks]
        bm25_index = BM25Okapi(tokenized)

    # ── Phase 1+2: hybrid retrieval with 20 raw candidates ──────────────────
    # Retrieve 20 candidates to give Phase 3 reranker room to work.
    expanded_kw = _sacs002_expand_query(keywords, control_text)
    _retrieval_mode = "bm25"
    if control_embedding is not None and db is not None and policy_id is not None:
        try:
            vec_results = _sacs002_vector_search(
                db, control_embedding, policy_id, policy_version_id, top_k=25
            )
            _, retrieval_quality, selected_chunks = _sacs002_hybrid_retrieve(
                policy_chunks, control_text, expanded_kw, bm25_index, vec_results, top_k=20
            )
            _retrieval_mode = "hybrid_rrf"
        except Exception as _vec_err:
            print(f"    [SACS002][{control_code}] vector search failed ({_vec_err}); BM25 fallback")
            _, retrieval_quality, selected_chunks = _sacs002_retrieve(
                policy_chunks, control_text, expanded_kw, bm25_index, top_k=20
            )
    else:
        _, retrieval_quality, selected_chunks = _sacs002_retrieve(
            policy_chunks, control_text, expanded_kw, bm25_index, top_k=20
        )

    # ── Phase 3a: section-aware boost ───────────────────────────────────────
    # Reorder candidates using section-category alignment as a tiebreaker.
    # _sacs002_section_boost returns (float, str) — unpack both to log the keyword.
    # Stable on equal boost: original retrieval rank preserved via -i tiebreaker.
    _boost_pairs = [_sacs002_section_boost(c["text"], control_code) for c in selected_chunks]
    _section_boosts = [b for b, _ in _boost_pairs]
    _any_section_boost = any(b > 0 for b in _section_boosts)
    if _any_section_boost:
        selected_chunks = [
            c for _, _, c in sorted(
                zip(_section_boosts, range(len(selected_chunks)), selected_chunks),
                key=lambda x: (x[0], -x[1]),
                reverse=True,
            )
        ]
        _triggered_kws = [kw for b, kw in _boost_pairs if b > 0]
        print(
            f"    [SACS002][BOOST][{control_code}] "
            f"+{_SECTION_BOOST_VALUE} via: {_triggered_kws[:3]}"
        )

    # ── Phase 3b: reranking ─────────────────────────────────────────────────
    _reranked = False
    _rerank_method = "none"
    if SACS002_RERANK_ENABLED:
        # Try BAAI cross-encoder first (requires sentence-transformers + env flag)
        _model_result = _sacs002_try_model_rerank(control_text, selected_chunks)
        if _model_result is not None:
            selected_chunks = _model_result
            _reranked = True
            _rerank_method = "baai_bge"
        else:
            # LLM reranker: one GPT-4o-mini call re-orders all 20 candidates
            selected_chunks = await _sacs002_llm_rerank(
                control_text, selected_chunks, control_code
            )
            _reranked = True
            _rerank_method = "llm"

    # Top 5 after reranking — keeps context focused; neighbors add back ~2-4 more
    final_chunks = selected_chunks[:5]

    # ── Phase 3c: neighbor expansion ────────────────────────────────────────
    # Add prev/next chunks to avoid evidence cut at chunk boundaries.
    _pre_expand_count = len(final_chunks)
    final_chunks = _sacs002_expand_neighbors(final_chunks, policy_chunks, window=1)

    focused_text = "\n---\n".join(c["text"] for c in final_chunks)
    focused_text = focused_text[:9000]  # hard cap: keep GPT context manageable

    # ── Phase 3 retrieval log (every control) ───────────────────────────────
    _top_preview = (final_chunks[0]["text"][:80].replace("\n", " ") if final_chunks else "")
    print(
        f"    [SACS002][RETR][{control_code}] "
        f"mode={_retrieval_mode} rerank={_rerank_method} "
        f"section_boost={'Y' if _any_section_boost else 'N'} "
        f"neighbors_added={len(final_chunks) - _pre_expand_count} "
        f"chunks={len(final_chunks)} chars={len(focused_text)} "
        f"quality={retrieval_quality:.3f}"
    )
    if diag:
        print(f"    [SACS002][DIAG][{control_code}] top_chunk: {_top_preview!r}")
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

    is_gpt_error_fallback = False
    try:
        raw = await call_llm(SACS002_VERIFIER_PROMPT, user_msg)
        if diag:
            print(f"    [SACS002][DIAG][{control_code}] raw GPT response: {raw[:600]}")
        gpt_data = json.loads(raw)
        results = gpt_data.get("checkpoints", [])
    except Exception as e:
        print(f"    [SACS002][{control_code}] GPT error: {e}")
        is_gpt_error_fallback = True
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

    # Phase 11: post-hoc source attribution. SACS-002 has no verification
    # cache, so attribution always runs against fresh GPT results, but the
    # mechanic is identical to ECC-2.
    src_chunk = None
    if best_evidence:
        src_chunk = _attribute_evidence_to_chunk(best_evidence, selected_chunks)
    src_chunk_id     = src_chunk.get("chunk_id") if src_chunk else None
    src_page_number  = src_chunk.get("page_number") if src_chunk else None
    src_paragraph_ix = src_chunk.get("paragraph_index") if src_chunk else None

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

    result = {
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
        # Phase 11: source attribution.
        "evidence_chunk_id":     src_chunk_id,
        "evidence_page_number":  src_page_number,
        "evidence_paragraph_index": src_paragraph_ix,
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

    # ── Phase G.2: cache write ───────────────────────────────────────────
    # GPT-error fallbacks are never cached so that the next analysis
    # re-runs through GPT once the upstream issue clears.
    if db is not None and cache_key is not None and not is_gpt_error_fallback:
        ok = _sacs_cache.write(
            db, cache_key, control_code, policy_hash,
            SACS002_PROMPT_VERSION, SACS002_MODEL, result,
        )
        if not ok:
            print(f"    [SACS002][{control_code}] cache write failed (non-fatal)")

    return result


def _save_assessment_row(db, policy_id: str, result: dict, framework_id_legacy: str):
    """Write one SACS-002 control result. Phase 11 adds chunk_id /
    page_number / paragraph_index source-attribution columns (all nullable;
    NULL when attribution couldn't pin evidence to a specific chunk).
    """
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
        "id": str(uuid.uuid4()),
        "pid": str(policy_id),
        "fwid": FRAMEWORK_ID,
        "cc": result["control_code"],
        "cs": result["compliance_status"],
        "ev": (result.get("evidence_text") or "")[:4000],
        "gap": (result.get("gap_description") or "")[:2000],
        "conf": result["confidence_score"],
        "ckid":   result.get("evidence_chunk_id"),
        "pgnum":  result.get("evidence_page_number"),
        "paridx": result.get("evidence_paragraph_index"),
        "at": datetime.now(timezone.utc),
    })


async def run_sacs002_analysis(
    db,
    policy_id: str,
    progress_cb=None,
    control_codes=None,
    policy_version_id: str | None = None,
) -> dict:
    """
    Analyze a policy against SACS-002 controls.

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
    print(f"SACS-002 STRUCTURED ANALYSIS STARTED - policy={policy_id}")
    print(f"{'='*60}")

    _report(12, "SACS-002: Checking policy chunks")

    if policy_version_id:
        _chunk_where  = "policy_version_id = :vid AND embedding IS NOT NULL"
        _chunk_params = {"vid": policy_version_id}
        print(f"  [SACS002] Version-scoped mode: policy_version_id={policy_version_id}")
    else:
        _chunk_where  = "policy_id = :pid AND embedding IS NOT NULL"
        _chunk_params = {"pid": policy_id}

    n_chunks = db.execute(sql_text(
        f"SELECT COUNT(*) FROM policy_chunks WHERE {_chunk_where}"
    ), _chunk_params).fetchone()[0]

    if n_chunks == 0:
        if policy_version_id:
            return {FRAMEWORK_ID: {"error": (
                f"No embedded chunks found for version {policy_version_id}. "
                "The version content was not embedded before analysis."
            )}}
        print("  [SACS002] Auto-embedding policy chunks...")
        _report(15, "SACS-002: Embedding policy text")
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
            print("  [SACS002] Backfill rechunk")
            _report(16, "SACS-002: Rechunking for source attribution")
            try:
                n_chunks = await rechunk_for_source_attribution(db, policy_id)
            except RechunkError as e:
                print(f"  [SACS002] Backfill skipped: {e}")

    print(f"  [SACS002] Loaded {n_chunks} chunks "
          f"(version={policy_version_id or 'original'})")

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
    if control_codes is not None:
        controls = [c for c in controls if c["control_code"] in control_codes]
        print(f"  [SACS002] Incremental mode: restricted to {len(controls)} targeted controls")

    sample = [c["control_code"] for c in controls[:3]]
    l2_loaded = sum(1 for c in controls if c["l2_loaded"])
    l3_loaded = sum(1 for c in controls if c["l3_loaded"])
    print(f"  [SACS002] {len(controls)} controls loaded "
          f"(first 3: {sample}) "
          f"L2={l2_loaded}/{len(controls)} L3={l3_loaded}/{len(controls)}")
    _report(22, f"SACS-002: Analysing {len(controls)} controls")

    try:
        _load_where_s  = "policy_version_id = :vid" if policy_version_id else "policy_id = :pid"
        _load_params_s = {"vid": policy_version_id} if policy_version_id else {"pid": policy_id}
        chunk_rows = db.execute(sql_text(
            "SELECT chunk_text, COALESCE(classification, 'descriptive'), "
            "       chunk_index, page_number, paragraph_index "
            f"FROM policy_chunks WHERE {_load_where_s} ORDER BY chunk_index"
        ), _load_params_s).fetchall()
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
        # Fallback for older schemas missing the Phase-11 columns.
        db.rollback()
        try:
            chunk_rows = db.execute(sql_text(
                "SELECT chunk_text, COALESCE(classification, 'descriptive'), "
                "       chunk_index "
                f"FROM policy_chunks WHERE {_load_where_s} ORDER BY chunk_index"
            ), _load_params_s).fetchall()
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

    policy_text = "\n\n".join(c["text"] for c in policy_chunks)
    # Phase G.2: hash once per run, reuse across all controls' cache lookups.
    # Truncated to 16 hex chars to match ECC-2's convention.
    policy_hash = hashlib.sha256(policy_text.encode("utf-8")).hexdigest()[:16]
    print(f"  [SACS002] Loaded {len(policy_chunks)} chunks "
          f"({len(policy_text)} chars total policy text, hash={policy_hash})")

    # Build BM25 index ONCE over the policy corpus.
    # Previously rebuilt inside _assess_control for every control (92×).
    # The index depends only on policy_chunks, not on the control being assessed.
    from rank_bm25 import BM25Okapi
    if policy_chunks:
        global_bm25 = BM25Okapi([c["text"].lower().split() for c in policy_chunks])
        print(f"  [SACS002] BM25 index built over {len(policy_chunks)} chunks")
    else:
        global_bm25 = None

    # Phase 2: pre-compute control text embeddings in one batch call.
    # This enables hybrid BM25+vector RRF retrieval for every control without
    # N individual embedding requests inside the control loop.
    ctrl_embedding_map: dict[str, list] = {}
    try:
        ctrl_texts = [c["control_text"][:500] for c in controls]
        print(f"  [SACS002] Pre-computing embeddings for {len(controls)} controls...")
        ctrl_embs = await get_embeddings(ctrl_texts)
        ctrl_embedding_map = {c["control_code"]: emb for c, emb in zip(controls, ctrl_embs)}
        print(f"  [SACS002] Control embeddings ready ({len(ctrl_embedding_map)} total)")
    except Exception as _emb_err:
        print(f"  [SACS002] WARNING: embedding pre-computation failed ({_emb_err}); BM25-only mode")

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
                control_embedding=ctrl_embedding_map.get(ctrl["control_code"]),
                policy_id=policy_id,
                policy_version_id=policy_version_id,
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

    # Phase HOTFIX: status must satisfy chk_compliance_results_status
    # ('Compliant' | 'Partial' | 'Non-Compliant'). Derive from score so
    # the row actually lands in compliance_results.
    verdict = (
        "Compliant" if score >= 80
        else "Partial" if score >= 50
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
            "id": str(uuid.uuid4()),
            "pid": policy_id,
            "fwid": legacy_fw_id,
            "st": verdict,
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

    # ── Cache observability ──────────────────────────────────────────────
    cache_stats = _sacs_cache.get_stats(db)
    print(
        f"  [SACS002] Cache stats: "
        f"hits={cache_stats['cache_hits']} "
        f"misses={cache_stats['cache_misses']} "
        f"hit_rate={cache_stats['hit_rate']:.1%} "
        f"write_ok={cache_stats['write_ok']} "
        f"write_fail={cache_stats['write_failures']} "
        f"lookup_fail={cache_stats['lookup_failures']} "
        f"avg_lookup={cache_stats['avg_lookup_ms']:.1f}ms"
    )
    if "db_total_rows" in cache_stats:
        print(
            f"  [SACS002] Cache DB: "
            f"total={cache_stats['db_total_rows']} "
            f"policies={cache_stats['db_distinct_policies']} "
            f"expired={cache_stats['db_expired_rows']}"
        )

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
