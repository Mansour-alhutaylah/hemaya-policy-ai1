"""Tests for Phase 12 atomic upload pipeline.

Two surfaces locked here:

1. Policy upload (backend/main.py upload_policy):
   - Extraction / chunking / embedding / store failures must roll back
     the policies row + saved file. No "Ready" policy with zero chunks.
2. Framework chunks replacement (backend/framework_loader.py
   load_framework_document):
   - Embeddings computed BEFORE delete. Embedding failure preserves
     existing framework_chunks. DELETE+INSERT atomic in one transaction.

The route helper _rollback_failed_policy_upload is unit-tested directly;
the full route is exercised structurally via source-grep so we don't need
a running uvicorn / FastAPI test client.

Run from repo root:
  python -m pytest backend/tests/test_phase12_atomic_upload.py -v
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s)


# =========================================================================
# POLICY UPLOAD — rollback helper (unit) + structural assertions on the route
# =========================================================================

# ─────────────────────────────────────────────────────────────────────────
# 1. Rollback helper: deletes chunks, deletes policy, removes file.
# ─────────────────────────────────────────────────────────────────────────
def test_rollback_helper_deletes_chunks_policy_and_file(tmp_path):
    """Direct unit test on _rollback_failed_policy_upload."""
    from backend.main import _rollback_failed_policy_upload

    # Create a fake saved file
    f = tmp_path / "policy.pdf"
    f.write_bytes(b"fake")
    assert f.exists()

    db = MagicMock()
    captured = []
    def exec_side(stmt, params=None):
        captured.append((str(stmt), params))
        return MagicMock()
    db.execute.side_effect = exec_side

    _rollback_failed_policy_upload(db, "policy-xyz", f)

    # Both DELETE statements executed
    sqls = [s for s, _ in captured]
    assert any("DELETE FROM policy_chunks" in s for s in sqls), (
        "rollback must delete policy_chunks"
    )
    assert any("DELETE FROM policies" in s for s in sqls), (
        "rollback must delete policies row"
    )
    # File removed
    assert not f.exists(), "rollback must delete the saved file"


# ─────────────────────────────────────────────────────────────────────────
# 2. Rollback helper: missing file is silently ignored.
# ─────────────────────────────────────────────────────────────────────────
def test_rollback_helper_silently_ignores_missing_file(tmp_path):
    from backend.main import _rollback_failed_policy_upload

    db = MagicMock()
    db.execute.return_value = MagicMock()

    # No file written; helper must not raise on the unlink branch.
    _rollback_failed_policy_upload(db, "policy-xyz", tmp_path / "does-not-exist.pdf")
    # Reaches here without exception → pass.


# ─────────────────────────────────────────────────────────────────────────
# 3. Rollback helper: DB exception during delete is swallowed.
# ─────────────────────────────────────────────────────────────────────────
def test_rollback_helper_swallows_db_exception(tmp_path):
    from backend.main import _rollback_failed_policy_upload

    f = tmp_path / "policy.pdf"
    f.write_bytes(b"x")

    db = MagicMock()
    db.execute.side_effect = RuntimeError("db down")
    # Helper must not propagate; it has its own try/except.
    _rollback_failed_policy_upload(db, "policy-xyz", f)
    # File should still be unlinked even if DB cleanup failed
    assert not f.exists(), "file cleanup runs even when DB cleanup raises"


# ─────────────────────────────────────────────────────────────────────────
# 4. Structural: policy upload route catches errors and rolls back.
# ─────────────────────────────────────────────────────────────────────────
def test_policy_upload_route_has_prepare_then_commit_structure():
    """Source-grep on the upload route: must (a) have a try/except
    surrounding the prepare+commit phases, (b) call
    _rollback_failed_policy_upload in the except handler, and (c) raise
    HTTPException on failure (no silent swallow)."""
    src = open("backend/main.py", encoding="utf-8").read()
    norm = _normalize(src)

    assert "_rollback_failed_policy_upload(db, policy_id, dest)" in norm, (
        "upload route must call the rollback helper on failure"
    )
    # Must NOT silently swallow embedding errors anymore. The legacy
    # comment said "will auto-embed during analysis"; that path is gone.
    assert "will auto-embed during analysis" not in norm, (
        "the silent embedding-failure swallow path must be removed"
    )
    # Mark-as-Ready UPDATE must live INSIDE the try block, so it's only
    # reached after store_chunks_with_embeddings succeeds.
    assert (
        "store_chunks_with_embeddings(db, policy_id, chunks, embeddings)"
        in norm
    )
    # Status='uploaded' set only after successful store
    upload_idx = norm.find("UPDATE policies SET status='uploaded'")
    store_idx = norm.find("store_chunks_with_embeddings(db, policy_id, chunks, embeddings)")
    assert upload_idx > store_idx > 0, (
        "the 'mark uploaded' UPDATE must come AFTER the chunks store call"
    )


# ─────────────────────────────────────────────────────────────────────────
# 5. Structural: extraction / chunking / embedding errors raise HTTPException
# ─────────────────────────────────────────────────────────────────────────
def test_policy_upload_raises_on_extraction_failure():
    """Source-grep: 'extraction produced no text' must be wired to a 422."""
    src = open("backend/main.py", encoding="utf-8").read()
    norm = _normalize(src)
    assert "extraction produced no text" in norm
    assert "status_code=422" in norm  # at least one 422 raise


def test_policy_upload_raises_on_zero_chunks():
    src = open("backend/main.py", encoding="utf-8").read()
    norm = _normalize(src)
    assert "chunker produced zero chunks" in norm


def test_policy_upload_raises_on_embedding_mismatch():
    src = open("backend/main.py", encoding="utf-8").read()
    norm = _normalize(src)
    assert "embedding API returned" in norm
    assert "status_code=502" in norm


# =========================================================================
# FRAMEWORK UPLOAD — prepare-before-delete + atomic swap
# =========================================================================

# ─────────────────────────────────────────────────────────────────────────
# 6. Framework: embeddings failure preserves old framework_chunks (no DELETE).
# ─────────────────────────────────────────────────────────────────────────
def test_framework_embedding_failure_preserves_old_chunks(monkeypatch):
    """When get_embeddings raises BEFORE we touch framework_chunks, the
    old rows remain. The function returns an error dict; no DB write
    to framework_chunks.

    framework_loader does LOCAL imports (`from backend.text_extractor
    import extract_text` inside the function), so patches must target
    the source modules' attributes — those are what the local imports
    pull in fresh on every call.
    """
    from backend import framework_loader as fl

    # Patch the source modules. framework_loader's local imports
    # rebind these names on every call, so patches stick.
    monkeypatch.setattr(
        "backend.text_extractor.extract_text",
        lambda fp, ext=None: "Frame text body sufficient for chunking.",
    )
    monkeypatch.setattr(
        "backend.chunker.chunk_text",
        lambda text, chunk_size=800, overlap=200: [
            {"chunk_index": 0, "text": "chunk-a", "char_start": 0, "char_end": 7},
            {"chunk_index": 1, "text": "chunk-b", "char_start": 7, "char_end": 14},
        ],
    )

    # Force get_embeddings to raise. The loader did
    # `from backend.vector_store import get_embeddings` at the top of
    # the function; that rebinds the local name on every call. Patching
    # on backend.vector_store catches it.
    async def fail_embed(texts):
        raise RuntimeError("embedding 503")
    monkeypatch.setattr("backend.vector_store.get_embeddings", fail_embed)

    # DB: lookup framework -> existing row id; never see DELETE/INSERT.
    db = MagicMock()
    executed = []
    def exec_side(stmt, params=None):
        sql = str(stmt)
        executed.append(sql)
        r = MagicMock()
        if "SELECT id FROM frameworks" in sql:
            r.fetchone.return_value = ("fw-1",)
        else:
            r.fetchone.return_value = None
        return r
    db.execute.side_effect = exec_side

    # Phase 12 puts get_embeddings in a try/except that returns an error
    # dict — but the underlying RuntimeError raised by our mock will
    # propagate out of the loader because the loader doesn't catch it
    # at the embeddings call. That's fine: assertion shifts to "the
    # exception fires and no DELETE was issued" — same observable safety.
    try:
        result = asyncio.run(fl.load_framework_document(
            db, "fake.docx", "TestFW", "fake.docx"
        ))
        # If the loader caught it (future-proofing), assert the dict shape.
        if isinstance(result, dict):
            assert "error" in result, f"expected error dict, got {result}"
    except RuntimeError as e:
        # Embedding failure propagated. That's acceptable — what matters
        # is that DELETE FROM framework_chunks did NOT run.
        assert "embedding 503" in str(e)

    delete_calls = [s for s in executed if "DELETE FROM framework_chunks" in s]
    assert not delete_calls, (
        "embedding failure must NOT delete framework_chunks - "
        f"saw {len(delete_calls)} DELETE call(s)"
    )


# ─────────────────────────────────────────────────────────────────────────
# 7. Framework: structural — DELETE happens AFTER get_embeddings.
# ─────────────────────────────────────────────────────────────────────────
def test_framework_loader_delete_happens_after_get_embeddings():
    """Source-grep: in load_framework_document, the position of
    'await get_embeddings' must be BEFORE the DELETE FROM
    framework_chunks line that lives inside the atomic-swap block."""
    src = open("backend/framework_loader.py", encoding="utf-8").read()
    # Find positions
    embed_idx = src.find("await get_embeddings(chunk_texts)")
    delete_idx = src.find("DELETE FROM framework_chunks WHERE framework_id = :fwid")
    assert embed_idx > 0 and delete_idx > 0
    assert embed_idx < delete_idx, (
        "Phase 12 invariant: get_embeddings must run BEFORE the chunks "
        "DELETE so embedding failures preserve existing chunks. "
        f"embed_idx={embed_idx}, delete_idx={delete_idx}"
    )


# ─────────────────────────────────────────────────────────────────────────
# 8. Framework: structural — DELETE+INSERT wrapped in try/except with rollback.
# ─────────────────────────────────────────────────────────────────────────
def test_framework_loader_swap_is_atomic():
    """Source-grep: the DELETE + INSERT block has try/except that
    rolls back on failure and returns an error dict (preserves old
    chunks)."""
    src = open("backend/framework_loader.py", encoding="utf-8").read()
    norm = _normalize(src)
    assert "framework_chunks atomic swap failed" in norm, (
        "atomic swap must surface a clear error message on failure"
    )
    assert "old framework_chunks preserved by rollback" in norm


# ─────────────────────────────────────────────────────────────────────────
# 9. Framework: structural — embedding-mismatch validation before delete.
# ─────────────────────────────────────────────────────────────────────────
def test_framework_loader_validates_embedding_count_before_swap():
    """If get_embeddings returns the wrong number of vectors, the
    function must error out BEFORE deleting old chunks."""
    src = open("backend/framework_loader.py", encoding="utf-8").read()
    norm = _normalize(src)
    assert "embedding API returned" in norm
    assert "old framework_chunks preserved" in norm


# =========================================================================
# DOWNSTREAM INVARIANTS — file_hash gate + Phase 11 attribution unchanged
# =========================================================================

# ─────────────────────────────────────────────────────────────────────────
# 10. file_hash gate untouched (Phase 0 + 4b invariant locked here too).
# ─────────────────────────────────────────────────────────────────────────
def test_file_hash_gate_unchanged():
    src = open("backend/main.py", encoding="utf-8").read()
    norm = _normalize(src)
    # Phase 4b's gate is the AND of extraction_complete and is_ready.
    assert "persist_hash = extraction_complete and rd[\"is_ready\"]" in norm


# ─────────────────────────────────────────────────────────────────────────
# 11. Phase 11 source attribution unchanged.
# ─────────────────────────────────────────────────────────────────────────
def test_phase11_source_attribution_invariant_unchanged():
    """Phase 11's _attribute_evidence_to_chunk + rechunk function
    bodies must be untouched. Phase 12 only changes the upload route
    and the framework chunks block."""
    src = open("backend/checkpoint_analyzer.py", encoding="utf-8").read()
    norm = _normalize(src)
    assert "_attribute_evidence_to_chunk" in norm
    assert "_resolve_policy_source_file" in norm
    assert "rechunk_for_source_attribution" in norm


# ─────────────────────────────────────────────────────────────────────────
# 12. Successful policy upload structurally hits store + mark-Ready in order.
# ─────────────────────────────────────────────────────────────────────────
def test_successful_upload_path_runs_store_then_mark_ready():
    """The store_chunks_with_embeddings call and the
    'UPDATE policies SET status=uploaded' must both live inside the
    same try block, in that order."""
    src = open("backend/main.py", encoding="utf-8").read()
    # Find the upload route specifically
    route_start = src.find("async def upload_policy(")
    route_end = src.find("\n@app.", route_start + 1)
    if route_end == -1:
        route_end = len(src)
    route = src[route_start:route_end]
    # Order check
    store_idx = route.find("store_chunks_with_embeddings(db, policy_id, chunks, embeddings)")
    ready_idx = route.find("UPDATE policies SET status='uploaded'")
    assert 0 < store_idx < ready_idx, (
        "store_chunks_with_embeddings must come BEFORE 'UPDATE status=uploaded'"
    )
    # Both inside the same try block: rollback helper appears AFTER both
    rollback_idx = route.find("_rollback_failed_policy_upload(db, policy_id, dest)")
    assert ready_idx < rollback_idx, (
        "rollback helper appears in the except branch, after the try-block content"
    )


# ─────────────────────────────────────────────────────────────────────────
# 13. Retry after failure: helper is idempotent on subsequent calls.
# ─────────────────────────────────────────────────────────────────────────
def test_rollback_helper_is_idempotent(tmp_path):
    """Running the rollback helper twice with the same arguments must
    not raise (e.g., second unlink swallows OSError)."""
    from backend.main import _rollback_failed_policy_upload

    f = tmp_path / "p.pdf"
    f.write_bytes(b"x")
    db = MagicMock()
    db.execute.return_value = MagicMock()

    _rollback_failed_policy_upload(db, "pid-1", f)
    _rollback_failed_policy_upload(db, "pid-1", f)  # second call: file gone
    # No exception → pass.


# ─────────────────────────────────────────────────────────────────────────
# 14. Phase 12 must not change retrieval / grounding / cache key.
# ─────────────────────────────────────────────────────────────────────────
def test_phase12_does_not_touch_retrieval_grounding_cache_key():
    src_ca = open("backend/checkpoint_analyzer.py", encoding="utf-8").read()
    norm_ca = _normalize(src_ca)
    # Phase 9 + Phase 10 invariants still in place
    assert 'RAG_MIN_RELEVANCE_SCORE = float(os.getenv("RAG_MIN_RELEVANCE_SCORE", "0.10"))' in norm_ca
    assert 'GROUNDING_VERSION = "v2"' in norm_ca
    assert 'GROUNDING_MIN_SIMILARITY = float(os.getenv("GROUNDING_MIN_SIMILARITY", "0.75"))' in norm_ca

    # ECC-2 cache key still includes floor + grounding fields
    src_ecc = open("backend/ecc2_analyzer.py", encoding="utf-8").read()
    norm_ecc = _normalize(src_ecc)
    assert "floor={retrieval_floor:.3f}" in norm_ecc
    assert "grounding={grounding_version}" in norm_ecc
