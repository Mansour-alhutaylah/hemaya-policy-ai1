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
