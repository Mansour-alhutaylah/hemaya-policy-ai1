"""Tests for the checkpoint-batch failure tracking added to
backend/framework_loader.py.

Run from repo root:  python -m pytest backend/tests/test_framework_extraction.py -v

These tests mock httpx and the SQLAlchemy session so they do not touch
OpenAI or the database. They exercise the JSON / schema / transport / HTTP
guards in generate_checkpoints_for_framework and the caller-side wiring in
load_framework_document.
"""
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from backend import framework_loader


def _make_response(status_code=200, content=None, json_payload=None, raw_body=None):
    """Build a mock httpx.Response-like object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = raw_body or ""
    if status_code == 200:
        body = (raw_body if raw_body is not None
                else json.dumps({"choices": [{"message": {"content": content}}]}))
        resp.json = MagicMock(return_value=json.loads(body))
    else:
        resp.json = MagicMock(side_effect=ValueError("not 200"))
    return resp


def _make_db_with_two_controls():
    """Mock SQLAlchemy session that returns two controls and swallows writes.

    Returned db lets generate_checkpoints_for_framework reach the OpenAI call
    site with a single batch of 2 controls. The function will then loop the
    batch loop exactly once.
    """
    db = MagicMock()

    # Sequence of execute() return values for the SELECTs the function makes:
    #   1. SELECT COUNT(*) FROM control_checkpoints WHERE framework=:fwid
    #      → fetchone()[0] = 0   (no existing checkpoints, proceed)
    #   2. SELECT id, control_code, ... FROM control_library WHERE framework_id=:fid
    #      → fetchall() = [(id1, "C-1", "Title 1", "[]"), (id2, "C-2", "Title 2", "[]")]
    # All subsequent INSERTs and the ensure_control_library_sync call should
    # also work via the same MagicMock.
    count_result = MagicMock()
    count_result.fetchone.return_value = (0,)
    controls_result = MagicMock()
    controls_result.fetchall.return_value = [
        ("id-1", "C-1", "Title 1", "[]"),
        ("id-2", "C-2", "Title 2", "[]"),
    ]
    insert_result = MagicMock()
    insert_result.rowcount = 0

    call_log = {"executes": 0}

    def execute_side_effect(sql, params=None):
        call_log["executes"] += 1
        sql_str = str(sql).upper()
        if "COUNT(*)" in sql_str and "CONTROL_CHECKPOINTS" in sql_str:
            return count_result
        if "CONTROL_LIBRARY" in sql_str and "FRAMEWORK_ID" in sql_str:
            return controls_result
        return insert_result

    db.execute.side_effect = execute_side_effect
    return db


def _patch_sync(monkeypatch):
    """ensure_control_library_sync is imported lazily inside the function;
    stub it out so the test does not import checkpoint_seed."""
    import backend.checkpoint_seed as cs
    monkeypatch.setattr(cs, "ensure_control_library_sync", lambda db: None)


# ─────────────────────────────────────────────────────────────────────────
# Test 1: HTTP error in checkpoint batch is recorded, not silently dropped.
# ─────────────────────────────────────────────────────────────────────────
def test_checkpoint_batch_http_error_is_tracked(monkeypatch):
    _patch_sync(monkeypatch)
    db = _make_db_with_two_controls()
    bad_response = _make_response(status_code=500, raw_body="upstream error")

    async def fake_post(*args, **kwargs):
        return bad_response

    # Zero out backoff so the 3-attempt retry runs instantly.
    monkeypatch.setattr(framework_loader, "CHECKPOINT_RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy", force=False, control_window_map={},
    ))

    assert result["total_checkpoints"] == 0
    assert len(result["failed_batches"]) == 1
    fb = result["failed_batches"][0]
    assert "HTTP 500" in fb["reason"]
    assert fb["control_codes"] == ["C-1", "C-2"]
    # 3 attempts = 2 retries
    assert fb["retry_count"] == 2


# ─────────────────────────────────────────────────────────────────────────
# Test 2: Malformed JSON in checkpoint batch is recorded.
# ─────────────────────────────────────────────────────────────────────────
def test_checkpoint_batch_json_decode_error_is_tracked(monkeypatch):
    _patch_sync(monkeypatch)
    db = _make_db_with_two_controls()
    # 200 OK but the LLM "content" payload is not valid JSON.
    raw_body = json.dumps({"choices": [{"message": {"content": "not-a-json {{{"}}]})
    response = _make_response(status_code=200, raw_body=raw_body)

    async def fake_post(*args, **kwargs):
        return response

    monkeypatch.setattr(framework_loader, "CHECKPOINT_RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy", force=False, control_window_map={},
    ))

    assert result["total_checkpoints"] == 0
    assert len(result["failed_batches"]) == 1
    fb = result["failed_batches"][0]
    assert "JSONDecodeError" in fb["reason"]
    assert fb["control_codes"] == ["C-1", "C-2"]
    assert fb["retry_count"] == 2


# ─────────────────────────────────────────────────────────────────────────
# Test 3: Schema violation (missing 'checkpoints' key) is recorded as failure.
# ─────────────────────────────────────────────────────────────────────────
def test_checkpoint_batch_schema_violation_is_tracked(monkeypatch):
    _patch_sync(monkeypatch)
    db = _make_db_with_two_controls()
    # 200 OK, valid JSON, but wrong shape: 'items' instead of 'checkpoints'.
    inner = json.dumps({"items": [{"control_code": "C-1", "items": []}]})
    raw_body = json.dumps({"choices": [{"message": {"content": inner}}]})
    response = _make_response(status_code=200, raw_body=raw_body)

    async def fake_post(*args, **kwargs):
        return response

    monkeypatch.setattr(framework_loader, "CHECKPOINT_RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy", force=False, control_window_map={},
    ))

    assert result["total_checkpoints"] == 0
    assert len(result["failed_batches"]) == 1
    fb = result["failed_batches"][0]
    assert "schema" in fb["reason"]
    assert "checkpoints" in fb["reason"]
    assert fb["control_codes"] == ["C-1", "C-2"]
    assert fb["retry_count"] == 2


# ─────────────────────────────────────────────────────────────────────────
# Test 4: Happy path — valid response inserts checkpoints, no failures.
# ─────────────────────────────────────────────────────────────────────────
def test_happy_path_inserts_checkpoints(monkeypatch):
    _patch_sync(monkeypatch)
    db = _make_db_with_two_controls()
    inner = json.dumps({
        "checkpoints": [
            {"control_code": "C-1", "items": [
                {"index": 1, "requirement": "Req A", "keywords": ["a"]},
                {"index": 2, "requirement": "Req B", "keywords": ["b"]},
            ]},
            {"control_code": "C-2", "items": [
                {"index": 1, "requirement": "Req C", "keywords": ["c"]},
            ]},
        ]
    })
    raw_body = json.dumps({"choices": [{"message": {"content": inner}}]})
    response = _make_response(status_code=200, raw_body=raw_body)

    async def fake_post(*args, **kwargs):
        return response

    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy", force=False, control_window_map={},
    ))

    assert result["total_checkpoints"] == 3
    assert result["failed_batches"] == []


# ─────────────────────────────────────────────────────────────────────────
# Test 5: Transport-level exception (e.g. timeout) is recorded as failure.
# ─────────────────────────────────────────────────────────────────────────
def test_checkpoint_batch_transport_error_is_tracked(monkeypatch):
    _patch_sync(monkeypatch)
    db = _make_db_with_two_controls()
    import httpx

    async def fake_post(*args, **kwargs):
        raise httpx.TimeoutException("upstream timeout")

    monkeypatch.setattr(framework_loader, "CHECKPOINT_RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy", force=False, control_window_map={},
    ))

    assert result["total_checkpoints"] == 0
    assert len(result["failed_batches"]) == 1
    fb = result["failed_batches"][0]
    assert "transport" in fb["reason"]
    assert "TimeoutException" in fb["reason"]
    assert fb["retry_count"] == 2


# ─────────────────────────────────────────────────────────────────────────
# Test 6: Return shape is stable (dict with both keys, even when empty).
# ─────────────────────────────────────────────────────────────────────────
def test_skip_path_returns_consistent_dict_shape(monkeypatch):
    _patch_sync(monkeypatch)
    # When checkpoints already exist, the function returns early with the
    # existing count and an empty failed_batches list.
    db = MagicMock()
    count_result = MagicMock()
    count_result.fetchone.return_value = (42,)  # existing checkpoints
    db.execute.return_value = count_result

    result = asyncio.run(framework_loader.generate_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy", force=False, control_window_map={},
    ))

    assert result == {"total_checkpoints": 42, "failed_batches": []}


# ─────────────────────────────────────────────────────────────────────────
# Test 7: Caller wiring — failed_batches flips extraction_complete=False.
# This is the integration assertion that proves the file_hash gate at
# main.py:1969 (which reads extraction_complete) will skip persisting the
# hash when checkpoint generation has any failed batch.
# ─────────────────────────────────────────────────────────────────────────
def test_load_framework_document_marks_incomplete_on_checkpoint_failure(monkeypatch):
    # Patch the lazily-imported helpers used by load_framework_document.
    import backend.text_extractor as te
    import backend.chunker as ch
    import backend.vector_store as vs

    monkeypatch.setattr(te, "extract_text", lambda *a, **kw: "framework text body")
    monkeypatch.setattr(ch, "chunk_text",
                        lambda *a, **kw: [{"text": "x", "chunk_index": 0}])

    async def fake_get_embeddings(texts):
        # None embeddings → chunk insert loop skips them, no real DB writes
        return [None for _ in texts]
    monkeypatch.setattr(vs, "get_embeddings", fake_get_embeddings)

    async def fake_extract_controls(*args, **kwargs):
        # Extraction itself succeeds — only checkpoints will fail.
        return {
            "controls_inserted": 5,
            "windows_total": 1,
            "windows_failed": [],
            "extraction_complete": True,
            "raw_controls": 5,
            "deduped_controls": 5,
            "control_window_map": {},
        }
    monkeypatch.setattr(framework_loader,
                        "extract_controls_from_framework", fake_extract_controls)

    async def fake_gen_checkpoints(*args, **kwargs):
        return {
            "total_checkpoints": 0,
            "failed_batches": [{
                "batch_index": 1,
                "control_codes": ["C-1", "C-2"],
                "reason": "JSONDecodeError: simulated",
            }],
        }
    monkeypatch.setattr(framework_loader,
                        "generate_checkpoints_for_framework", fake_gen_checkpoints)

    # Mock db: fetchone returns a framework_id (existing row found).
    db = MagicMock()
    fw_lookup_result = MagicMock()
    fw_lookup_result.fetchone.return_value = ("fid-1",)
    db.execute.return_value = fw_lookup_result

    result = asyncio.run(framework_loader.load_framework_document(
        db=db, file_path="/tmp/dummy.txt", framework_name="TEST",
        source_document="src", force=True,
    ))

    # Caller-side assertions — the contract main.py:1969 relies on:
    assert result["extraction_complete"] is False
    assert result["status"] == "incomplete"
    assert result["failed_checkpoint_batches_count"] == 1
    assert result["failed_checkpoint_batches"][0]["control_codes"] == ["C-1", "C-2"]
    assert any("Checkpoint generation incomplete" in w
               for w in result["extraction_warnings"])
    assert result["warning"] is not None


# ─────────────────────────────────────────────────────────────────────────
# Test 8: control_library INSERT statement uses ON CONFLICT DO NOTHING.
# Lock in the contract that protects against duplicates under the
# uq_control_library_framework_code constraint.
# ─────────────────────────────────────────────────────────────────────────
def test_control_library_insert_uses_on_conflict():
    src = open("backend/framework_loader.py", encoding="utf-8").read()
    # Single regex over whitespace so newlines/indentation drift won't break it.
    import re
    norm = re.sub(r"\s+", " ", src)
    assert "INSERT INTO control_library" in norm
    assert "ON CONFLICT (framework_id, control_code) DO NOTHING" in norm, (
        "framework_loader.py must use ON CONFLICT DO NOTHING for the "
        "control_library insert to defend against the unique constraint."
    )

    # Same contract for checkpoint_seed.py (two insert sites).
    seed_src = open("backend/checkpoint_seed.py", encoding="utf-8").read()
    seed_norm = re.sub(r"\s+", " ", seed_src)
    assert seed_norm.count("ON CONFLICT (framework_id, control_code) DO NOTHING") >= 2, (
        "checkpoint_seed.py must apply ON CONFLICT to both control_library "
        "insert sites (NCA seed + ensure_control_library_sync)."
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 9: extract_controls_from_framework counts skipped conflicts correctly.
# When the DB raises a conflict (rowcount==0), the row is counted as skipped,
# not inserted, so controls_inserted stays accurate.
# ─────────────────────────────────────────────────────────────────────────
def test_extract_controls_counts_skipped_conflicts(monkeypatch):
    # Stub OpenAI to return three controls — one will "conflict" in the mock.
    inner = json.dumps({"controls": [
        {"code": "X-1", "title": "First", "severity": "High", "keywords": []},
        {"code": "X-2", "title": "Second", "severity": "High", "keywords": []},
        {"code": "X-3", "title": "Third", "severity": "High", "keywords": []},
    ]})
    raw_body = json.dumps({"choices": [{"message": {"content": inner}}]})
    response = _make_response(status_code=200, raw_body=raw_body)

    async def fake_post(*args, **kwargs):
        return response
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    # Mock db where the SECOND INSERT returns rowcount=0 (conflict).
    db = MagicMock()
    insert_call = {"n": 0}

    def execute_side_effect(sql, params=None):
        sql_str = str(sql).upper()
        if "SELECT COUNT(*)" in sql_str and "CONTROL_LIBRARY" in sql_str:
            r = MagicMock()
            r.fetchone.return_value = (0,)
            return r
        if "INSERT INTO CONTROL_LIBRARY" in sql_str:
            insert_call["n"] += 1
            r = MagicMock()
            # Second insert (X-2) hits a conflict; others succeed.
            r.rowcount = 0 if insert_call["n"] == 2 else 1
            return r
        # DELETE / other
        r = MagicMock()
        r.rowcount = 0
        return r

    db.execute.side_effect = execute_side_effect

    result = asyncio.run(framework_loader.extract_controls_from_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy text body", force=True,
    ))

    assert result["controls_inserted"] == 2
    assert result["controls_skipped_conflict"] == 1
    assert result["extraction_complete"] is True  # no window failures


def _make_db_with_n_controls(n):
    """Mock SQLAlchemy session that returns n controls."""
    db = MagicMock()
    count_result = MagicMock()
    count_result.fetchone.return_value = (0,)
    controls_result = MagicMock()
    controls_result.fetchall.return_value = [
        (f"id-{i}", f"C-{i}", f"Title {i}", "[]") for i in range(1, n + 1)
    ]
    delete_result = MagicMock()
    delete_result.rowcount = 0
    insert_result = MagicMock()
    insert_result.rowcount = 1

    def execute_side_effect(sql, params=None):
        sql_str = str(sql).upper()
        if "DELETE FROM CONTROL_CHECKPOINTS" in sql_str:
            return delete_result
        if "COUNT(*)" in sql_str and "CONTROL_CHECKPOINTS" in sql_str:
            return count_result
        if "CONTROL_LIBRARY" in sql_str and "FRAMEWORK_ID" in sql_str:
            return controls_result
        return insert_result

    db.execute.side_effect = execute_side_effect
    return db


# ─────────────────────────────────────────────────────────────────────────
# Test 10: Phase 2 atomic semantics — failure mid-run rolls back, no
# partial INSERTs. The first batch succeeds, the second batch's GPT call
# fails (HTTP 500). The function must:
#   - call db.rollback() exactly once
#   - never execute INSERT INTO control_checkpoints
#   - return total_checkpoints=0 and failed_batches non-empty
# ─────────────────────────────────────────────────────────────────────────
def test_atomic_partial_failure_inserts_nothing_and_rolls_back(monkeypatch):
    _patch_sync(monkeypatch)
    db = _make_db_with_n_controls(20)  # 2 batches of 10

    # Sequence: batch 1 succeeds (1 call), batch 2 fails HTTP 500 on every
    # retry (Phase 3 adds MAX_CHECKPOINT_ATTEMPTS=3 retries, so we queue
    # 3 failures for batch 2). The retries are 5xx, which IS retryable but
    # never recovers — the batch ends up in failed_batches.
    success_inner = json.dumps({
        "checkpoints": [
            {"control_code": f"C-{i}", "items": [
                {"index": 1, "requirement": f"Req {i}", "keywords": []},
            ]}
            for i in range(1, 11)
        ]
    })
    success_body = json.dumps({"choices": [{"message": {"content": success_inner}}]})
    success_response = _make_response(status_code=200, raw_body=success_body)
    failure_response = _make_response(status_code=500, raw_body="upstream error")
    # batch 1: 1 call. batch 2: up to MAX_CHECKPOINT_ATTEMPTS=3 calls.
    queue = [success_response] + [failure_response] * 3

    async def fake_post(*args, **kwargs):
        return queue.pop(0)
    # Speed up the test: zero out retry backoff.
    monkeypatch.setattr(framework_loader, "CHECKPOINT_RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy", force=True, control_window_map={},
    ))

    # Atomic outcome: zero rows persisted, one rollback, no INSERT executed.
    assert result["total_checkpoints"] == 0
    assert len(result["failed_batches"]) == 1
    assert "HTTP 500" in result["failed_batches"][0]["reason"]

    db.rollback.assert_called_once()
    assert db.commit.call_count == 0  # no commit on failure path

    # Verify no INSERT INTO control_checkpoints was ever called.
    insert_call_count = sum(
        1 for call in db.execute.call_args_list
        if "INSERT INTO control_checkpoints"
        in str(call.args[0]).replace("\n", " ").replace("  ", " ")
    )
    assert insert_call_count == 0, (
        "Atomic semantics violated: an INSERT was executed even though "
        "a later batch failed."
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 11: force=True happy path — DELETE staged, all batches succeed,
# function commits exactly once with all buffered INSERTs.
# ─────────────────────────────────────────────────────────────────────────
def test_atomic_happy_path_force_true_commits_once_with_all_inserts(monkeypatch):
    _patch_sync(monkeypatch)
    db = _make_db_with_n_controls(15)  # 2 batches: 10 + 5

    success_inner_b1 = json.dumps({
        "checkpoints": [
            {"control_code": f"C-{i}", "items": [
                {"index": 1, "requirement": f"R{i}a", "keywords": []},
                {"index": 2, "requirement": f"R{i}b", "keywords": []},
            ]}
            for i in range(1, 11)
        ]
    })
    success_inner_b2 = json.dumps({
        "checkpoints": [
            {"control_code": f"C-{i}", "items": [
                {"index": 1, "requirement": f"R{i}a", "keywords": []},
            ]}
            for i in range(11, 16)
        ]
    })
    queue = [
        _make_response(200, raw_body=json.dumps({"choices": [{"message": {"content": success_inner_b1}}]})),
        _make_response(200, raw_body=json.dumps({"choices": [{"message": {"content": success_inner_b2}}]})),
    ]

    async def fake_post(*args, **kwargs):
        return queue.pop(0)
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy", force=True, control_window_map={},
    ))

    # Batch 1: 10 controls × 2 items = 20. Batch 2: 5 × 1 = 5. Total = 25.
    assert result["total_checkpoints"] == 25
    assert result["failed_batches"] == []

    # Exactly one DELETE staged at the start (and not committed separately).
    delete_calls = sum(
        1 for call in db.execute.call_args_list
        if "DELETE FROM CONTROL_CHECKPOINTS" in str(call.args[0]).upper()
    )
    assert delete_calls == 1

    # All 25 INSERTs executed (one per checkpoint).
    insert_calls = sum(
        1 for call in db.execute.call_args_list
        if "INSERT INTO control_checkpoints"
        in str(call.args[0]).replace("\n", " ").replace("  ", " ")
    )
    assert insert_calls == 25

    # Exactly one commit (atomic at the end). No rollback.
    assert db.commit.call_count == 1
    assert db.rollback.call_count == 0


# ─────────────────────────────────────────────────────────────────────────
# Test 12: Phase 3 retry — first attempt returns invalid JSON, second
# attempt returns valid JSON. The function recovers and the batch is NOT
# in failed_batches.
# ─────────────────────────────────────────────────────────────────────────
def test_checkpoint_batch_retry_succeeds_on_second_attempt(monkeypatch):
    _patch_sync(monkeypatch)
    db = _make_db_with_two_controls()

    bad_body = json.dumps({"choices": [{"message": {"content": "garbage {"}}]})
    good_inner = json.dumps({
        "checkpoints": [
            {"control_code": "C-1", "items": [
                {"index": 1, "requirement": "R1", "keywords": []},
            ]},
            {"control_code": "C-2", "items": [
                {"index": 1, "requirement": "R2", "keywords": []},
            ]},
        ]
    })
    good_body = json.dumps({"choices": [{"message": {"content": good_inner}}]})
    queue = [
        _make_response(200, raw_body=bad_body),
        _make_response(200, raw_body=good_body),
    ]

    async def fake_post(*args, **kwargs):
        return queue.pop(0)

    monkeypatch.setattr(framework_loader, "CHECKPOINT_RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy", force=False, control_window_map={},
    ))

    assert result["total_checkpoints"] == 2
    assert result["failed_batches"] == []
    # Sanity: the queue should be exhausted (both responses were used).
    assert queue == []


# ─────────────────────────────────────────────────────────────────────────
# Test 13: Phase 3 — permanent 4xx (e.g., 401 Unauthorized) is NOT retried.
# Records the failure with retry_count=0 (one attempt, no retries).
# ─────────────────────────────────────────────────────────────────────────
def test_checkpoint_batch_permanent_4xx_is_not_retried(monkeypatch):
    _patch_sync(monkeypatch)
    db = _make_db_with_two_controls()

    call_count = {"n": 0}

    async def fake_post(*args, **kwargs):
        call_count["n"] += 1
        return _make_response(status_code=401, raw_body="invalid api key")

    monkeypatch.setattr(framework_loader, "CHECKPOINT_RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy", force=False, control_window_map={},
    ))

    # Exactly one OpenAI call — the 401 stops retries.
    assert call_count["n"] == 1
    assert result["total_checkpoints"] == 0
    assert len(result["failed_batches"]) == 1
    fb = result["failed_batches"][0]
    assert "HTTP 401" in fb["reason"]
    # retry_count == 0 because we used 1 attempt and stopped (no retries).
    assert fb["retry_count"] == 0


# ─────────────────────────────────────────────────────────────────────────
# Test 14: Phase 3 — HTTP 429 (rate limit) IS retried (treated as transient).
# Confirms 429 is excluded from the permanent-4xx classification.
# ─────────────────────────────────────────────────────────────────────────
def test_checkpoint_batch_429_is_retried(monkeypatch):
    _patch_sync(monkeypatch)
    db = _make_db_with_two_controls()

    call_count = {"n": 0}

    async def fake_post(*args, **kwargs):
        call_count["n"] += 1
        return _make_response(status_code=429, raw_body="rate limit")

    monkeypatch.setattr(framework_loader, "CHECKPOINT_RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy", force=False, control_window_map={},
    ))

    # Three attempts (initial + 2 retries) before giving up.
    assert call_count["n"] == 3
    assert len(result["failed_batches"]) == 1
    assert result["failed_batches"][0]["retry_count"] == 2


def _make_db_for_repair(missing_codes, chunk_text="dummy framework text"):
    """Mock db for generate_missing_checkpoints_for_framework.
    Simulates: SELECT missing controls + SELECT framework_chunks.
    """
    db = MagicMock()
    missing_result = MagicMock()
    missing_result.fetchall.return_value = [
        (f"id-{c}", c, f"Title {c}", "[]") for c in missing_codes
    ]
    chunks_result = MagicMock()
    chunks_result.fetchall.return_value = [(chunk_text,), ("more context",)]
    insert_result = MagicMock()
    insert_result.rowcount = 1

    def execute_side_effect(sql, params=None):
        sql_str = str(sql).upper()
        if "FRAMEWORK_CHUNKS" in sql_str and "CHUNK_TEXT" in sql_str:
            return chunks_result
        if ("CONTROL_LIBRARY" in sql_str and "FRAMEWORK_ID" in sql_str
                and "NOT EXISTS" in sql_str):
            return missing_result
        if "INSERT INTO CONTROL_CHECKPOINTS" in sql_str:
            return insert_result
        # default: empty result for anything else
        r = MagicMock()
        r.fetchall.return_value = []
        r.fetchone.return_value = (0,)
        return r

    db.execute.side_effect = execute_side_effect
    return db


# ─────────────────────────────────────────────────────────────────────────
# Test 15: Phase 4 repair — generate_missing_checkpoints_for_framework
# adds checkpoints ONLY for missing controls. No DELETE. Single commit.
# ─────────────────────────────────────────────────────────────────────────
def test_repair_adds_checkpoints_only_for_missing_controls(monkeypatch):
    db = _make_db_for_repair(["1-2-2", "1-7-1"])

    inner = json.dumps({
        "checkpoints": [
            {"control_code": "1-2-2", "items": [
                {"index": 1, "requirement": "R1", "keywords": []},
                {"index": 2, "requirement": "R2", "keywords": []},
            ]},
            {"control_code": "1-7-1", "items": [
                {"index": 1, "requirement": "R3", "keywords": []},
            ]},
        ]
    })
    raw_body = json.dumps({"choices": [{"message": {"content": inner}}]})
    response = _make_response(200, raw_body=raw_body)

    async def fake_post(*args, **kwargs):
        return response
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_missing_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
    ))

    assert result["total_checkpoints_added"] == 3
    assert result["controls_repaired"] == 2
    assert result["controls_missing_before"] == 2
    assert result["failed_batches"] == []

    # No DELETE statement should have been issued — repair must not destroy data.
    delete_calls = sum(
        1 for call in db.execute.call_args_list
        if "DELETE" in str(call.args[0]).upper()
    )
    assert delete_calls == 0

    # Exactly 3 INSERTs and exactly 1 commit.
    insert_calls = sum(
        1 for call in db.execute.call_args_list
        if "INSERT INTO control_checkpoints"
        in str(call.args[0]).replace("\n", " ").replace("  ", " ")
    )
    assert insert_calls == 3
    assert db.commit.call_count == 1
    assert db.rollback.call_count == 0


# ─────────────────────────────────────────────────────────────────────────
# Test 16: repair with no missing controls is a no-op.
# ─────────────────────────────────────────────────────────────────────────
def test_repair_noop_when_no_missing_controls(monkeypatch):
    db = _make_db_for_repair([])  # empty list = no missing controls

    # OpenAI must not be called.
    call_count = {"n": 0}

    async def fake_post(*args, **kwargs):
        call_count["n"] += 1
        return _make_response(200)
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_missing_checkpoints_for_framework(
        db=db, framework_name="CLEAN", framework_id="fid-clean",
    ))

    assert result == {
        "total_checkpoints_added": 0,
        "controls_repaired": 0,
        "controls_missing_before": 0,
        "failed_batches": [],
    }
    assert call_count["n"] == 0
    assert db.commit.call_count == 0
    assert db.rollback.call_count == 0


# ─────────────────────────────────────────────────────────────────────────
# Test 17a: control_code normalization — GPT prefixes the code (e.g. returns
# "ECC-1-2-2" when we sent "1-2-2"). The buffer logic must recover the
# original code by suffix/containment match and insert with the requested code.
# ─────────────────────────────────────────────────────────────────────────
def test_run_loop_normalizes_prefixed_codes(monkeypatch):
    _patch_sync(monkeypatch)
    db = _make_db_with_two_controls()  # batch_codes = ["C-1", "C-2"]

    # GPT returns "ECC-C-1" and "PREFIX-C-2" — both should normalize.
    inner = json.dumps({
        "checkpoints": [
            {"control_code": "ECC-C-1", "items": [
                {"index": 1, "requirement": "R1", "keywords": []},
            ]},
            {"control_code": "PREFIX-C-2", "items": [
                {"index": 1, "requirement": "R2", "keywords": []},
                {"index": 2, "requirement": "R3", "keywords": []},
            ]},
        ]
    })
    raw_body = json.dumps({"choices": [{"message": {"content": inner}}]})
    response = _make_response(200, raw_body=raw_body)

    async def fake_post(*args, **kwargs):
        return response
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy", force=False, control_window_map={},
    ))

    # Both codes recovered → 3 checkpoints inserted with the requested codes.
    assert result["total_checkpoints"] == 3
    assert result["failed_batches"] == []

    # Verify the INSERT calls used the BATCH codes ("C-1", "C-2"), not the
    # GPT-returned mangled codes ("ECC-C-1", "PREFIX-C-2").
    inserted_codes = []
    for call in db.execute.call_args_list:
        sql_str = str(call.args[0]).replace("\n", " ").replace("  ", " ")
        if "INSERT INTO control_checkpoints" in sql_str:
            inserted_codes.append(call.args[1]["cc"])
    assert sorted(inserted_codes) == ["C-1", "C-2", "C-2"]
    assert "ECC-C-1" not in inserted_codes
    assert "PREFIX-C-2" not in inserted_codes


# ─────────────────────────────────────────────────────────────────────────
# Test 17b: unmatchable codes are skipped — GPT returns a control_code that
# bears no relation to any requested code. No insert; no exception.
# ─────────────────────────────────────────────────────────────────────────
def test_run_loop_skips_unmatchable_codes(monkeypatch):
    _patch_sync(monkeypatch)
    db = _make_db_with_two_controls()  # batch_codes = ["C-1", "C-2"]

    inner = json.dumps({
        "checkpoints": [
            # Valid first
            {"control_code": "C-1", "items": [
                {"index": 1, "requirement": "R1", "keywords": []},
            ]},
            # Garbage code — must be skipped
            {"control_code": "WHATEVER-99", "items": [
                {"index": 1, "requirement": "RX", "keywords": []},
            ]},
        ]
    })
    raw_body = json.dumps({"choices": [{"message": {"content": inner}}]})
    response = _make_response(200, raw_body=raw_body)

    async def fake_post(*args, **kwargs):
        return response
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
        full_text="dummy", force=False, control_window_map={},
    ))

    # Only the matching code's checkpoint persists.
    assert result["total_checkpoints"] == 1
    assert result["failed_batches"] == []

    inserted_codes = [
        call.args[1]["cc"]
        for call in db.execute.call_args_list
        if "INSERT INTO control_checkpoints"
        in str(call.args[0]).replace("\n", " ").replace("  ", " ")
    ]
    assert inserted_codes == ["C-1"]


# ─────────────────────────────────────────────────────────────────────────
# Test 18: repair atomicity — failure rolls back, no INSERTs persist.
# ─────────────────────────────────────────────────────────────────────────
def test_repair_atomic_on_failure(monkeypatch):
    db = _make_db_for_repair(["X-1", "X-2"])

    # Always fail with HTTP 500.
    async def fake_post(*args, **kwargs):
        return _make_response(500, raw_body="upstream error")

    monkeypatch.setattr(framework_loader, "CHECKPOINT_RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(framework_loader._openai_client, "post", fake_post)

    result = asyncio.run(framework_loader.generate_missing_checkpoints_for_framework(
        db=db, framework_name="TEST", framework_id="fid-1",
    ))

    assert result["total_checkpoints_added"] == 0
    assert result["controls_repaired"] == 0
    assert result["controls_missing_before"] == 2
    assert len(result["failed_batches"]) == 1

    # Atomic: rollback called, no INSERTs, no commit.
    assert db.rollback.call_count == 1
    assert db.commit.call_count == 0
    insert_calls = sum(
        1 for call in db.execute.call_args_list
        if "INSERT INTO control_checkpoints"
        in str(call.args[0]).replace("\n", " ").replace("  ", " ")
    )
    assert insert_calls == 0


# ─────────────────────────────────────────────────────────────────────────
# Test 19: framework_readiness — happy path: every control has a checkpoint.
# ─────────────────────────────────────────────────────────────────────────
def test_framework_readiness_returns_ready_for_complete_framework():
    db = MagicMock()
    row = MagicMock()
    # (fwid, total_controls, zero_cp_controls)
    row.__iter__ = lambda self: iter(("fid-1", 100, 0))
    # Need to support tuple unpacking; use real tuple
    select_result = MagicMock()
    select_result.fetchone.return_value = ("fid-1", 100, 0)
    db.execute.return_value = select_result

    rd = framework_loader.framework_readiness(db, "MY_FRAMEWORK")
    assert rd["is_ready"] is True
    assert rd["framework_id"] == "fid-1"
    assert rd["total_controls"] == 100
    assert rd["zero_cp_controls"] == 0
    assert rd["reason"] is None
    assert rd["structured"] is False


# ─────────────────────────────────────────────────────────────────────────
# Test 20: framework_readiness — not ready when any zero_cp control exists.
# ─────────────────────────────────────────────────────────────────────────
def test_framework_readiness_not_ready_when_zero_cp_exists():
    db = MagicMock()
    select_result = MagicMock()
    select_result.fetchone.return_value = ("fid-1", 50, 3)
    db.execute.return_value = select_result

    rd = framework_loader.framework_readiness(db, "MY_FRAMEWORK")
    assert rd["is_ready"] is False
    assert rd["zero_cp_controls"] == 3
    assert rd["total_controls"] == 50
    assert "3 of 50" in rd["reason"]


# ─────────────────────────────────────────────────────────────────────────
# Test 21: framework_readiness — structured framework allowlist
# (ECC-2:2024) is vacuously ready.
# ─────────────────────────────────────────────────────────────────────────
def test_framework_readiness_structured_framework_is_ready():
    db = MagicMock()
    # The function must NOT query the DB for structured frameworks.
    db.execute.side_effect = AssertionError("structured framework should not query DB")

    rd = framework_loader.framework_readiness(db, "ECC-2:2024")
    assert rd["is_ready"] is True
    assert rd["structured"] is True
    assert rd["reason"] is None


# ─────────────────────────────────────────────────────────────────────────
# Test 21b: SACS-002 is also a structured framework. It has its own
# analyzer (run_sacs002_analysis) and its own tables (sacs002_metadata
# + ecc_* layer tables) and must bypass the control_library readiness
# check exactly like ECC-2:2024. A regression here means analyze_policy
# returns HTTP 409 for any request that includes "SACS-002".
# ─────────────────────────────────────────────────────────────────────────
def test_framework_readiness_sacs002_is_ready():
    db = MagicMock()
    db.execute.side_effect = AssertionError("structured framework should not query DB")

    rd = framework_loader.framework_readiness(db, "SACS-002")
    assert rd["is_ready"] is True
    assert rd["structured"] is True
    assert rd["reason"] is None
    assert rd["framework_id"] is None  # not looked up; vacuously ready


# ─────────────────────────────────────────────────────────────────────────
# Test 22: framework_readiness — unknown framework is not ready.
# ─────────────────────────────────────────────────────────────────────────
def test_framework_readiness_unknown_framework_is_not_ready():
    db = MagicMock()
    select_result = MagicMock()
    select_result.fetchone.return_value = None  # no matching row
    db.execute.return_value = select_result

    rd = framework_loader.framework_readiness(db, "NONEXISTENT")
    assert rd["is_ready"] is False
    assert "not found" in rd["reason"]
    assert rd["framework_id"] is None


# ─────────────────────────────────────────────────────────────────────────
# Test 23: framework_readiness — empty framework (zero controls) is NOT ready.
# Prevents an empty-shell framework from passing the gate.
# ─────────────────────────────────────────────────────────────────────────
def test_framework_readiness_empty_framework_is_not_ready():
    db = MagicMock()
    select_result = MagicMock()
    select_result.fetchone.return_value = ("fid-empty", 0, 0)
    db.execute.return_value = select_result

    rd = framework_loader.framework_readiness(db, "EMPTY")
    assert rd["is_ready"] is False
    assert rd["total_controls"] == 0
    assert "zero controls" in rd["reason"]
