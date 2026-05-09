"""Tests for the Phase 7 ECC-2 verification cache.

Run from repo root:  python -m pytest backend/tests/test_ecc2_cache.py -v

The ECC-2 verifier in backend/ecc2_analyzer.py must:
  1. Skip the GPT call entirely on a cache hit.
  2. Cache POST-grounded results so on hit grounding is also skipped.
  3. Treat (control_code, policy_hash, prompt_version, model) as the key,
     so changing any of those produces a miss.
  4. Never let cache failures abort analysis.
  5. Never cache the synthetic GPT-error fallback.
"""
import asyncio
import hashlib
import json
import re
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from backend import ecc2_analyzer


def _normalize(s):
    return re.sub(r"\s+", " ", s)


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────
def _control(code="ECC-1-1-1"):
    return {
        "control_code": code,
        "control_text": "Cybersecurity strategy approved by senior management",
        "audit_questions": ["Is it documented?", "Is it approved?", "Is it reviewed?"],
        "keywords": ["strategy", "approved", "senior management"],
        "control_type": "MANDATORY",
        "domain_code": "1",
        "subdomain_code": "1-1",
        "deleted_in_ecc2": False,
        # Layer-loaded flags expected by _assess_control return shape
        "l1_loaded": True,
        "l2_loaded": True,
        "l3_loaded": True,
    }


def _policy_chunks():
    return [
        {"text": "The organization has a documented cybersecurity strategy "
                 "approved by senior management.", "classification": "mandatory"},
        {"text": "The strategy is reviewed annually.", "classification": "mandatory"},
    ]


def _gpt_response(control_code="ECC-1-1-1"):
    """Valid post-grounding GPT response."""
    return json.dumps({
        "checkpoints": [
            {"index": 1, "met": True,  "confidence": 0.85,
             "evidence": "documented cybersecurity strategy"},
            {"index": 2, "met": True,  "confidence": 0.75, "evidence": "approved"},
            {"index": 3, "met": False, "confidence": 0.40, "evidence": "no evidence found"},
            {"index": 4, "met": True,  "confidence": 0.70, "evidence": "reviewed annually"},
        ]
    })


def _make_db_with_cached_row(cached_results):
    """Mock db where the SELECT cache lookup returns cached_results."""
    db = MagicMock()
    select_result = MagicMock()
    # JSONB columns may round-trip as already-parsed list/dict OR as a JSON
    # string depending on driver. The cache reader handles both.
    select_result.fetchone.return_value = (cached_results,)
    db.execute.return_value = select_result
    return db


def _make_db_with_no_cached_row():
    """Mock db where the SELECT cache lookup returns nothing."""
    db = MagicMock()
    select_result = MagicMock()
    select_result.fetchone.return_value = None
    db.execute.return_value = select_result
    return db


# ─────────────────────────────────────────────────────────────────────────
# Test 1: Cache MISS → GPT called + INSERT issued.
# ─────────────────────────────────────────────────────────────────────────
def test_cache_miss_calls_gpt_and_writes_cache(monkeypatch):
    db = _make_db_with_no_cached_row()
    captured_inserts = []

    def execute_side_effect(sql, params=None):
        sql_str = str(sql)
        if "SELECT result FROM ecc2_verification_cache" in sql_str:
            r = MagicMock()
            r.fetchone.return_value = None
            return r
        if "INSERT INTO ecc2_verification_cache" in sql_str:
            captured_inserts.append(params)
            return MagicMock()
        return MagicMock()

    db.execute.side_effect = execute_side_effect

    fake_call_llm = AsyncMock(return_value=_gpt_response())
    monkeypatch.setattr(ecc2_analyzer, "call_llm", fake_call_llm)

    result = asyncio.run(ecc2_analyzer._assess_control(
        control=_control(),
        policy_chunks=_policy_chunks(),
        policy_text="\n\n".join(c["text"] for c in _policy_chunks()),
        bm25_index=None,
        db=db,
        policy_hash="abc123def456",
    ))

    assert fake_call_llm.call_count == 1, "GPT must be called on cache miss"
    assert len(captured_inserts) == 1, "Cache INSERT must run after GPT call"
    insert = captured_inserts[0]
    assert insert["cc"] == "ECC-1-1-1"
    assert insert["ph"] == "abc123def456"
    assert insert["pv"] == ecc2_analyzer.ECC2_PROMPT_VERSION
    assert insert["mdl"] == ecc2_analyzer.ECC2_MODEL
    # cache_key is the SHA256 of the canonical key string. Phase 9 added the
    # retrieval floor to the key so changes to RAG_MIN_RELEVANCE_SCORE produce
    # a different cache_key (no stale-cache reuse across floors). Phase 10
    # appended a literal grounding-algorithm version tag (e.g. "v2") so a
    # change to the body of _find_grounded_evidence also segregates rows.
    from backend import checkpoint_analyzer as ca
    floor = getattr(ca, "RAG_MIN_RELEVANCE_SCORE", 0.0)
    grounding = getattr(ca, "GROUNDING_VERSION", "v1")
    expected_key = hashlib.sha256(
        (
            f"ECC2|ECC-1-1-1|abc123def456|"
            f"{ecc2_analyzer.ECC2_PROMPT_VERSION}|{ecc2_analyzer.ECC2_MODEL}|"
            f"floor={floor:.3f}|"
            f"grounding={grounding}"
        ).encode()
    ).hexdigest()
    assert insert["ck"] == expected_key
    # Result was scored (downstream gating ran)
    assert "compliance_status" in result and "_l1_conf" in result


# ─────────────────────────────────────────────────────────────────────────
# Test 2: Cache HIT → GPT NOT called.
# ─────────────────────────────────────────────────────────────────────────
def test_cache_hit_skips_gpt(monkeypatch):
    cached = [
        {"index": 1, "met": True,  "confidence": 0.9, "evidence": "documented strategy"},
        {"index": 2, "met": True,  "confidence": 0.8, "evidence": "approved"},
        {"index": 3, "met": False, "confidence": 0.3, "evidence": "no evidence found"},
        {"index": 4, "met": True,  "confidence": 0.7, "evidence": "reviewed annually"},
    ]
    # JSONB driver round-trip: result column is already a parsed list.
    db = MagicMock()
    select_result = MagicMock()
    select_result.fetchone.return_value = (cached,)
    db.execute.return_value = select_result

    fake_call_llm = AsyncMock(return_value=_gpt_response())
    monkeypatch.setattr(ecc2_analyzer, "call_llm", fake_call_llm)

    result = asyncio.run(ecc2_analyzer._assess_control(
        control=_control(),
        policy_chunks=_policy_chunks(),
        policy_text="\n\n".join(c["text"] for c in _policy_chunks()),
        bm25_index=None,
        db=db,
        policy_hash="abc123def456",
    ))

    assert fake_call_llm.call_count == 0, "GPT must NOT be called on cache hit"
    # Downstream gating still ran with cached results
    assert "compliance_status" in result


# ─────────────────────────────────────────────────────────────────────────
# Test 3: Cache HIT with JSON-string round-trip (some drivers return str).
# ─────────────────────────────────────────────────────────────────────────
def test_cache_hit_handles_json_string_round_trip(monkeypatch):
    cached = [
        {"index": 1, "met": True, "confidence": 0.9, "evidence": "ok"},
    ]
    # Simulate a driver that returns JSONB as a JSON-encoded string.
    db = MagicMock()
    select_result = MagicMock()
    select_result.fetchone.return_value = (json.dumps(cached),)
    db.execute.return_value = select_result

    fake_call_llm = AsyncMock(return_value=_gpt_response())
    monkeypatch.setattr(ecc2_analyzer, "call_llm", fake_call_llm)

    result = asyncio.run(ecc2_analyzer._assess_control(
        control=_control(),
        policy_chunks=_policy_chunks(),
        policy_text="\n\n".join(c["text"] for c in _policy_chunks()),
        bm25_index=None,
        db=db,
        policy_hash="abc123def456",
    ))

    assert fake_call_llm.call_count == 0, "GPT must NOT be called on cache hit"
    assert "compliance_status" in result


# ─────────────────────────────────────────────────────────────────────────
# Test 4: Changing prompt_version invalidates cached rows (different key).
# ─────────────────────────────────────────────────────────────────────────
def test_prompt_version_bump_changes_cache_key(monkeypatch):
    captured_select_keys = []
    captured_insert_keys = []

    def execute_side_effect(sql, params=None):
        sql_str = str(sql)
        if "SELECT result FROM ecc2_verification_cache" in sql_str:
            captured_select_keys.append(params["ck"])
            r = MagicMock()
            r.fetchone.return_value = None  # always miss
            return r
        if "INSERT INTO ecc2_verification_cache" in sql_str:
            captured_insert_keys.append(params["ck"])
            return MagicMock()
        return MagicMock()

    db = MagicMock()
    db.execute.side_effect = execute_side_effect
    fake_call_llm = AsyncMock(return_value=_gpt_response())
    monkeypatch.setattr(ecc2_analyzer, "call_llm", fake_call_llm)

    # First run with current prompt_version
    asyncio.run(ecc2_analyzer._assess_control(
        control=_control(),
        policy_chunks=_policy_chunks(),
        policy_text="\n\n".join(c["text"] for c in _policy_chunks()),
        bm25_index=None,
        db=db, policy_hash="abc123",
    ))
    key_v1 = captured_select_keys[-1]

    # Bump the version
    monkeypatch.setattr(ecc2_analyzer, "ECC2_PROMPT_VERSION", "v999")
    asyncio.run(ecc2_analyzer._assess_control(
        control=_control(),
        policy_chunks=_policy_chunks(),
        policy_text="\n\n".join(c["text"] for c in _policy_chunks()),
        bm25_index=None,
        db=db, policy_hash="abc123",
    ))
    key_v999 = captured_select_keys[-1]

    assert key_v1 != key_v999, "Bumping ECC2_PROMPT_VERSION must produce a different cache_key"


# ─────────────────────────────────────────────────────────────────────────
# Test 4b: Phase 9 — RAG_MIN_RELEVANCE_SCORE is part of the cache key.
# Changing the floor must produce a different cache_key so verdicts
# computed under one floor are NOT served on requests using a different
# floor (focused_text differs → GPT input differs → cached verdict stale).
# ─────────────────────────────────────────────────────────────────────────
def test_retrieval_floor_change_produces_different_cache_key(monkeypatch):
    from backend import checkpoint_analyzer as ca

    captured_select_keys = []

    def execute_side_effect(sql, params=None):
        sql_str = str(sql)
        if "SELECT result FROM ecc2_verification_cache" in sql_str:
            captured_select_keys.append(params["ck"])
            r = MagicMock()
            r.fetchone.return_value = None  # always miss → INSERT path runs
            return r
        if "INSERT INTO ecc2_verification_cache" in sql_str:
            return MagicMock()
        return MagicMock()

    db = MagicMock()
    db.execute.side_effect = execute_side_effect
    fake_call_llm = AsyncMock(return_value=_gpt_response())
    monkeypatch.setattr(ecc2_analyzer, "call_llm", fake_call_llm)

    # Run with floor=0.0
    monkeypatch.setattr(ca, "RAG_MIN_RELEVANCE_SCORE", 0.0)
    asyncio.run(ecc2_analyzer._assess_control(
        control=_control(), policy_chunks=_policy_chunks(),
        policy_text="\n\n".join(c["text"] for c in _policy_chunks()),
        bm25_index=None, db=db, policy_hash="abc123",
    ))
    key_floor_0 = captured_select_keys[-1]

    # Run with floor=0.10 (Phase 9 default)
    monkeypatch.setattr(ca, "RAG_MIN_RELEVANCE_SCORE", 0.10)
    asyncio.run(ecc2_analyzer._assess_control(
        control=_control(), policy_chunks=_policy_chunks(),
        policy_text="\n\n".join(c["text"] for c in _policy_chunks()),
        bm25_index=None, db=db, policy_hash="abc123",
    ))
    key_floor_010 = captured_select_keys[-1]

    # Run with floor=0.20
    monkeypatch.setattr(ca, "RAG_MIN_RELEVANCE_SCORE", 0.20)
    asyncio.run(ecc2_analyzer._assess_control(
        control=_control(), policy_chunks=_policy_chunks(),
        policy_text="\n\n".join(c["text"] for c in _policy_chunks()),
        bm25_index=None, db=db, policy_hash="abc123",
    ))
    key_floor_020 = captured_select_keys[-1]

    assert key_floor_0 != key_floor_010, (
        "floor=0.0 and floor=0.10 must produce different cache keys; "
        "otherwise stale cached verdicts will be served when the retrieval "
        "floor changes."
    )
    assert key_floor_010 != key_floor_020, (
        "floor=0.10 and floor=0.20 must produce different cache keys."
    )
    assert key_floor_0 != key_floor_020, (
        "floor=0.0 and floor=0.20 must produce different cache keys."
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 5: Synthetic GPT-error fallback is NOT cached. Otherwise an error
# during the first run would poison the cache for future runs.
# ─────────────────────────────────────────────────────────────────────────
def test_gpt_error_fallback_is_not_cached(monkeypatch):
    captured_inserts = []

    def execute_side_effect(sql, params=None):
        sql_str = str(sql)
        if "SELECT result FROM ecc2_verification_cache" in sql_str:
            r = MagicMock()
            r.fetchone.return_value = None
            return r
        if "INSERT INTO ecc2_verification_cache" in sql_str:
            captured_inserts.append(params)
            return MagicMock()
        return MagicMock()

    db = MagicMock()
    db.execute.side_effect = execute_side_effect
    # Make GPT raise — the analyzer must produce a synthetic fallback result.
    fake_call_llm = AsyncMock(side_effect=RuntimeError("upstream timeout"))
    monkeypatch.setattr(ecc2_analyzer, "call_llm", fake_call_llm)

    result = asyncio.run(ecc2_analyzer._assess_control(
        control=_control(),
        policy_chunks=_policy_chunks(),
        policy_text="\n\n".join(c["text"] for c in _policy_chunks()),
        bm25_index=None,
        db=db, policy_hash="abc123",
    ))

    assert fake_call_llm.call_count == 1
    assert len(captured_inserts) == 0, (
        "Synthetic GPT-error fallback must NOT be cached "
        "(would poison subsequent runs)"
    )
    # Result still has structure (status produced from fallback)
    assert "compliance_status" in result


# ─────────────────────────────────────────────────────────────────────────
# Test 6: db=None disables the cache entirely (defense for callers that
# don't have a session).
# ─────────────────────────────────────────────────────────────────────────
def test_cache_disabled_when_db_is_none(monkeypatch):
    fake_call_llm = AsyncMock(return_value=_gpt_response())
    monkeypatch.setattr(ecc2_analyzer, "call_llm", fake_call_llm)

    result = asyncio.run(ecc2_analyzer._assess_control(
        control=_control(),
        policy_chunks=_policy_chunks(),
        policy_text="\n\n".join(c["text"] for c in _policy_chunks()),
        bm25_index=None,
        db=None,
        policy_hash=None,
    ))

    assert fake_call_llm.call_count == 1, "GPT must run when no db provided"
    assert "compliance_status" in result
