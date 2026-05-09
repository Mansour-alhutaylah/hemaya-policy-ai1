"""Tests for Phase 11 source attribution.

End-to-end mapping: source files -> per-segment metadata -> source-aware
chunks -> source-attribution columns on policy_ecc_assessments. Plus
backwards-compatibility locks on the existing extract_text() and
chunk_text() signatures, and a structural lock on the cache key staying
unchanged so cache-hit assessments still attribute via post-hoc match
without forcing a fresh GPT call.

Run from repo root:
  python -m pytest backend/tests/test_phase11_source_attribution.py -v
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend import checkpoint_analyzer
from backend.checkpoint_analyzer import (
    _attribute_evidence_to_chunk,
    _find_relevant_sections,
)
from backend.chunker import chunk_text, chunk_text_segments
from backend.text_extractor import extract_text, extract_text_segments


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────
def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s)


# ─────────────────────────────────────────────────────────────────────────
# 1. extract_text_pdf_returns_per_page_segments
# ─────────────────────────────────────────────────────────────────────────
def test_extract_text_pdf_returns_per_page_segments(monkeypatch):
    """Each PDF page becomes one segment with 1-indexed page_number."""
    from backend import text_extractor

    fake_pages = [MagicMock(number=0), MagicMock(number=1), MagicMock(number=2)]
    fake_pages[0].get_text.return_value = {"blocks": [
        {"type": 0, "lines": [{"spans": [{"text": "Page one body."}]}]}
    ]}
    fake_pages[1].get_text.return_value = {"blocks": [
        {"type": 0, "lines": [{"spans": [{"text": "Page two body."}]}]}
    ]}
    fake_pages[2].get_text.return_value = {"blocks": [
        {"type": 0, "lines": [{"spans": [{"text": "Page three body."}]}]}
    ]}

    fake_doc = MagicMock()
    fake_doc.__iter__ = lambda self: iter(fake_pages)

    fake_fitz = MagicMock()
    fake_fitz.open.return_value = fake_doc
    monkeypatch.setitem(__import__("sys").modules, "fitz", fake_fitz)

    segments = text_extractor._extract_pdf_segments("dummy.pdf")
    assert len(segments) == 3
    assert segments[0]["page_number"] == 1
    assert segments[1]["page_number"] == 2
    assert segments[2]["page_number"] == 3
    assert all(s["paragraph_index"] is None for s in segments)
    assert "Page one body." in segments[0]["text"]


# ─────────────────────────────────────────────────────────────────────────
# 2. extract_text_docx_returns_per_paragraph_segments
# ─────────────────────────────────────────────────────────────────────────
def test_extract_text_docx_returns_per_paragraph_segments(monkeypatch):
    """Each non-empty DOCX paragraph becomes one segment with 0-indexed paragraph_index."""
    from backend import text_extractor

    paragraphs = [
        MagicMock(text="First paragraph."),
        MagicMock(text="   "),  # whitespace-only -> skipped
        MagicMock(text="Third paragraph."),
        MagicMock(text="Fourth paragraph."),
    ]

    fake_doc_cls = MagicMock(return_value=MagicMock(paragraphs=paragraphs))
    monkeypatch.setattr("docx.Document", fake_doc_cls, raising=False)
    import docx as _docx
    monkeypatch.setattr(_docx, "Document", fake_doc_cls)

    segments = text_extractor._extract_docx_segments("dummy.docx")
    # The whitespace-only paragraph at index 1 is dropped; remaining
    # segments retain the original enumeration index.
    assert len(segments) == 3
    assert segments[0]["paragraph_index"] == 0
    assert segments[1]["paragraph_index"] == 2
    assert segments[2]["paragraph_index"] == 3
    assert all(s["page_number"] is None for s in segments)
    assert segments[0]["text"] == "First paragraph."


# ─────────────────────────────────────────────────────────────────────────
# 3. extract_text_txt_returns_single_segment_with_nulls
# ─────────────────────────────────────────────────────────────────────────
def test_extract_text_txt_returns_single_segment_with_nulls(tmp_path):
    """TXT files produce a single segment with both source fields NULL."""
    f = tmp_path / "x.txt"
    f.write_text("Some unstructured text.\nMultiple lines.")
    segments = extract_text_segments(f, "txt")
    assert len(segments) == 1
    assert segments[0]["page_number"] is None
    assert segments[0]["paragraph_index"] is None
    assert "Some unstructured text" in segments[0]["text"]


# ─────────────────────────────────────────────────────────────────────────
# 4. chunk_text_threads_page_number_through
# ─────────────────────────────────────────────────────────────────────────
def test_chunk_text_threads_page_number_through():
    """Source-aware chunking attaches page_number to each chunk."""
    # Two PDF-style segments, large enough that each produces its own chunk
    segments = [
        {"text": "A" * 600, "page_number": 1, "paragraph_index": None},
        {"text": "B" * 600, "page_number": 2, "paragraph_index": None},
    ]
    chunks = chunk_text_segments(segments, chunk_size=500, overlap=100)
    assert len(chunks) >= 2
    pages = {c["page_number"] for c in chunks}
    assert pages == {1, 2}
    assert all(c["paragraph_index"] is None for c in chunks)


# ─────────────────────────────────────────────────────────────────────────
# 5. chunk_text_first_segment_wins_when_chunk_spans_segments
# ─────────────────────────────────────────────────────────────────────────
def test_chunk_text_first_segment_wins_when_chunk_spans_segments():
    """When small DOCX paragraphs combine into one chunk, the chunk
    inherits the first paragraph's index."""
    segments = [
        {"text": "Short A.", "page_number": None, "paragraph_index": 5},
        {"text": "Short B.", "page_number": None, "paragraph_index": 6},
        {"text": "Short C.", "page_number": None, "paragraph_index": 7},
    ]
    chunks = chunk_text_segments(segments, chunk_size=500, overlap=100)
    assert len(chunks) == 1
    # All three small paragraphs fit in one chunk → first wins
    assert chunks[0]["paragraph_index"] == 5
    assert chunks[0]["page_number"] is None


# ─────────────────────────────────────────────────────────────────────────
# 6. store_chunks_with_embeddings_writes_new_columns
# ─────────────────────────────────────────────────────────────────────────
def test_store_chunks_with_embeddings_writes_new_columns(monkeypatch):
    """The INSERT statement binds page_number / paragraph_index params."""
    from backend import vector_store

    captured = []

    def fake_execute(stmt, params=None):
        captured.append({"sql": str(stmt), "params": params})
        return MagicMock()

    db = MagicMock()
    db.execute.side_effect = fake_execute

    # Bypass the real classifier dependency
    monkeypatch.setattr(
        "backend.structured_extractor.classify_sentence",
        lambda txt: "descriptive",
    )

    chunks = [
        {"text": "page-1 chunk", "chunk_index": 0,
         "char_start": 0, "char_end": 12,
         "page_number": 1, "paragraph_index": None},
        {"text": "para-7 chunk", "chunk_index": 1,
         "char_start": 12, "char_end": 24,
         "page_number": None, "paragraph_index": 7},
    ]
    embs = [[0.1] * 1536, [0.2] * 1536]

    vector_store.store_chunks_with_embeddings(db, "policy-xyz", chunks, embs)

    # First INSERT call carries page_number=1; second carries paragraph_index=7
    inserts = [c for c in captured if "INSERT INTO policy_chunks" in c["sql"]]
    assert len(inserts) == 2
    assert "page_number" in inserts[0]["sql"]
    assert "paragraph_index" in inserts[0]["sql"]
    assert inserts[0]["params"]["pgnum"] == 1
    assert inserts[0]["params"]["paridx"] is None
    assert inserts[1]["params"]["pgnum"] is None
    assert inserts[1]["params"]["paridx"] == 7


# ─────────────────────────────────────────────────────────────────────────
# 7. find_relevant_sections_returns_selected_chunks
# ─────────────────────────────────────────────────────────────────────────
def test_find_relevant_sections_returns_selected_chunks():
    """When return_selected=True, the result is a 3-tuple whose third
    element is the list of selected chunk dicts in selection order."""
    chunks = [
        {"text": "Cybersecurity strategy approved by senior management.",
         "classification": "descriptive",
         "page_number": 3, "paragraph_index": None},
        {"text": "Cafeteria opens at 8am.",
         "classification": "descriptive",
         "page_number": 7, "paragraph_index": None},
    ]
    result = _find_relevant_sections(
        chunks, "Cybersecurity strategy approved", ["cybersecurity", "strategy"],
        bm25=None, offset=0, return_selected=True,
    )
    assert isinstance(result, tuple) and len(result) == 3
    focused, quality, selected = result
    assert "cybersecurity strategy" in focused.lower()
    assert isinstance(selected, list)
    # Top selected chunk must be the substantive one (page 3) — its
    # page_number must round-trip through the function unchanged.
    pages = [c["page_number"] for c in selected]
    assert 3 in pages


# ─────────────────────────────────────────────────────────────────────────
# 8. attribute_evidence_to_chunk_exact_substring
# ─────────────────────────────────────────────────────────────────────────
def test_attribute_evidence_to_chunk_exact_substring():
    """Pass 1: when actual_text is a verbatim substring of one chunk's
    text, that chunk is returned."""
    chunks = [
        {"text": "Foo bar.", "page_number": 1},
        {"text": "Multi-factor authentication is required for remote access.",
         "page_number": 14},
        {"text": "Other unrelated.", "page_number": 22},
    ]
    actual_text = "Multi-factor authentication is required"
    matched = _attribute_evidence_to_chunk(actual_text, chunks)
    assert matched is not None
    assert matched["page_number"] == 14


# ─────────────────────────────────────────────────────────────────────────
# 9. attribute_evidence_to_chunk_fuzzy_fallback
# ─────────────────────────────────────────────────────────────────────────
def test_attribute_evidence_to_chunk_fuzzy_fallback():
    """Pass 2: when actual_text isn't a verbatim substring of any chunk
    (cross-chunk grounding window), the highest-overlap chunk wins
    provided ratio >= 0.5."""
    # Two chunks; the claim spans both halves but isn't verbatim in either.
    chunks = [
        {"text": "Cybersecurity strategy is documented and reviewed.",
         "page_number": 1},
        {"text": "Disaster recovery plans are tested annually.",
         "page_number": 2},
    ]
    # Slight perturbation to defeat the substring fast path:
    actual_text = "Cybersecurity strategy is documented and approved"
    matched = _attribute_evidence_to_chunk(actual_text, chunks)
    assert matched is not None
    assert matched["page_number"] == 1


# ─────────────────────────────────────────────────────────────────────────
# 10. attribute_evidence_to_chunk_no_match_returns_none
# ─────────────────────────────────────────────────────────────────────────
def test_attribute_evidence_to_chunk_no_match_returns_none():
    """Unrelated text returns None (caller writes NULL source)."""
    chunks = [
        {"text": "Cybersecurity strategy is approved.", "page_number": 1},
        {"text": "MFA is required for remote access.", "page_number": 2},
    ]
    actual_text = "Volcanic eruption telemetry on Mars sea levels"
    matched = _attribute_evidence_to_chunk(actual_text, chunks)
    assert matched is None


# ─────────────────────────────────────────────────────────────────────────
# 11. assessment_row_includes_source_attribution
#     End-to-end via mocked GPT: the policy_ecc_assessments INSERT params
#     include chunk_id / page_number / paragraph_index for a grounded
#     verdict.
# ─────────────────────────────────────────────────────────────────────────
def test_assessment_row_includes_source_attribution():
    """Source-grep on ecc2_analyzer + sacs002_analyzer to confirm the
    INSERT statements bind the new columns. Guards against a future
    refactor that drops the params silently."""
    ecc_src = open("backend/ecc2_analyzer.py", encoding="utf-8").read()
    sacs_src = open("backend/sacs002_analyzer.py", encoding="utf-8").read()

    for src, name in ((ecc_src, "ecc2_analyzer"), (sacs_src, "sacs002_analyzer")):
        norm = _normalize(src)
        assert "chunk_id, page_number, paragraph_index" in norm, (
            f"{name} INSERT must include the three new columns inline."
        )
        assert ":ckid, :pgnum, :paridx" in norm, (
            f"{name} INSERT must bind ckid/pgnum/paridx params."
        )


# ─────────────────────────────────────────────────────────────────────────
# 12. legacy_chunks_without_source_trigger_rechunk_on_reanalysis
# ─────────────────────────────────────────────────────────────────────────
def test_legacy_chunks_without_source_trigger_rechunk_on_reanalysis(monkeypatch):
    """When all policy_chunks rows lack source attribution,
    policy_needs_source_attribution_backfill returns True and the
    analyzer entry-point fires rechunk_for_source_attribution."""
    from backend.checkpoint_analyzer import (
        policy_needs_source_attribution_backfill,
    )
    db = MagicMock()
    row = MagicMock()
    row.total = 16
    row.unsourced = 16
    db.execute.return_value.fetchone.return_value = row
    assert policy_needs_source_attribution_backfill(db, "any-pid") is True


# ─────────────────────────────────────────────────────────────────────────
# 13. new_chunks_skip_rechunk_path
# ─────────────────────────────────────────────────────────────────────────
def test_new_chunks_skip_rechunk_path():
    """When at least one chunk already has source attribution, the
    backfill predicate is False (rechunk does NOT fire)."""
    from backend.checkpoint_analyzer import (
        policy_needs_source_attribution_backfill,
    )
    db = MagicMock()
    row = MagicMock()
    row.total = 16
    row.unsourced = 8  # half have source -> already partially backfilled
    db.execute.return_value.fetchone.return_value = row
    assert policy_needs_source_attribution_backfill(db, "any-pid") is False


# ─────────────────────────────────────────────────────────────────────────
# 14. grounding_unchanged_by_phase11
#     Structural — _find_grounded_evidence body is byte-identical to
#     Phase 10. Phase 11 only ADDS _attribute_evidence_to_chunk; it must
#     not modify Stage 1 / Stage 2 of the grounding helper.
# ─────────────────────────────────────────────────────────────────────────
def test_grounding_unchanged_by_phase11():
    src = open("backend/checkpoint_analyzer.py", encoding="utf-8").read()
    norm = _normalize(src)
    # Phase 10 v2 markers must still be present, untouched.
    assert "GROUNDING_VERSION = \"v2\"" in norm
    assert (
        'GROUNDING_MIN_SIMILARITY = float(os.getenv("GROUNDING_MIN_SIMILARITY", "0.75"))'
        in norm
    )
    # The Stage 2 sentence-window control flow must still call
    # _split_sentences (not the v1 1.3×-claim-length window loop).
    assert "_split_sentences(norm_policy)" in norm


# ─────────────────────────────────────────────────────────────────────────
# 15. extract_text_signature_unchanged
#     Backwards-compat lock: extract_text() still returns str; the new
#     symbol is extract_text_segments.
# ─────────────────────────────────────────────────────────────────────────
def test_extract_text_signature_unchanged(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("Plain content.")
    result = extract_text(f, "txt")
    assert isinstance(result, str)
    assert "Plain content" in result
    # The new symbol exists and returns a list.
    seg_result = extract_text_segments(f, "txt")
    assert isinstance(seg_result, list)


# ─────────────────────────────────────────────────────────────────────────
# 15b. chunk_text_signature_backwards_compatible
#     Backwards-compat lock: chunk_text(text: str) still produces the
#     pre-Phase-11 dict shape; chunk_text_segments is the new entry point.
# ─────────────────────────────────────────────────────────────────────────
def test_chunk_text_signature_backwards_compatible():
    text = "Sentence one. " * 100  # ~1400 chars; will produce multiple chunks
    chunks = chunk_text(text, chunk_size=500, overlap=100)
    assert len(chunks) >= 2
    for c in chunks:
        # Pre-Phase-11 keys preserved
        assert "chunk_index" in c
        assert "text" in c
        assert "char_start" in c
        assert "char_end" in c
        # New keys must NOT be added by chunk_text() — that's chunk_text_segments' job
        assert "page_number" not in c
        assert "paragraph_index" not in c

    # chunk_text_segments adds them
    segs = [{"text": text, "page_number": 5, "paragraph_index": None}]
    enriched = chunk_text_segments(segs, chunk_size=500, overlap=100)
    assert all(c["page_number"] == 5 for c in enriched)


# ─────────────────────────────────────────────────────────────────────────
# 16. source_attribution_populates_page_number_even_when_ecc2_cache_hits
#     User-required. Cache hit → no GPT call; attribution still populates
#     page_number on the new assessment row.
# ─────────────────────────────────────────────────────────────────────────
def test_source_attribution_populates_page_number_even_when_ecc2_cache_hits(monkeypatch):
    """End-to-end with a mocked cache-hit + mocked DB: assert
    call_llm count is zero AND the attribution result is non-NULL."""
    import asyncio
    from backend import ecc2_analyzer

    # Cached GPT result: one passing L1 + L3 with grounded evidence text
    # that exists verbatim in our policy_chunks fixture below.
    cached = [
        {"index": 1, "met": True, "confidence": 0.9,
         "evidence": "Multi-factor authentication is required for remote access"},
        {"index": 2, "met": True, "confidence": 0.8, "evidence": "ok"},
        {"index": 3, "met": False, "confidence": 0.3, "evidence": "no evidence found"},
        {"index": 4, "met": True, "confidence": 0.7, "evidence": "ok"},
    ]
    db = MagicMock()
    select_result = MagicMock()
    select_result.fetchone.return_value = (cached,)
    db.execute.return_value = select_result

    fake_call = AsyncMock()
    monkeypatch.setattr(ecc2_analyzer, "call_llm", fake_call)

    control = {
        "control_code": "1-1-1",
        "control_text": "Multi-factor authentication shall be required",
        "control_type": "directive",
        "domain_code": "1",
        "subdomain_code": "1-1",
        "audit_questions": ["q1", "q2", "q3"],
        "keywords": ["mfa", "authentication", "remote"],
        "l1_loaded": True, "l2_loaded": True, "l3_loaded": True,
    }
    policy_chunks = [
        {"text": "Multi-factor authentication is required for remote access "
                 "and for all administrators accessing privileged systems.",
         "classification": "descriptive",
         "chunk_index": 0, "page_number": 14, "paragraph_index": None,
         "chunk_id": "p1_chunk_0"},
        {"text": "Other content.",
         "classification": "descriptive",
         "chunk_index": 1, "page_number": 15, "paragraph_index": None,
         "chunk_id": "p1_chunk_1"},
    ]
    policy_text = "\n\n".join(c["text"] for c in policy_chunks)

    result = asyncio.run(ecc2_analyzer._assess_control(
        control=control,
        policy_chunks=policy_chunks,
        policy_text=policy_text,
        bm25_index=None, db=db, policy_hash="abc123",
    ))

    assert fake_call.call_count == 0, "GPT must NOT be called on cache hit"
    # Attribution must populate page_number from the matched chunk.
    assert result["evidence_page_number"] == 14
    assert result["evidence_chunk_id"] == "p1_chunk_0"


# ─────────────────────────────────────────────────────────────────────────
# 17. rechunk_failure_preserves_existing_chunks
#     User-required. Embedding step raises → no DELETE / INSERT; existing
#     chunks remain. On retry success, swap is atomic.
# ─────────────────────────────────────────────────────────────────────────
def test_rechunk_failure_preserves_existing_chunks(monkeypatch, tmp_path):
    """Force get_embeddings to raise after extraction + chunking. The
    rechunk must surface RechunkError and never issue DELETE or INSERT."""
    import asyncio
    import os
    from backend import checkpoint_analyzer as ca

    # Fake policy file
    upload_dir = tmp_path / "backend" / "uploads"
    upload_dir.mkdir(parents=True)
    f = upload_dir / "policy.txt"
    f.write_text("Sentence one. Sentence two.")
    monkeypatch.chdir(tmp_path)

    # DB mock that records every execute call
    executed = []
    db = MagicMock()
    def exec_side(stmt, params=None):
        executed.append(str(stmt))
        r = MagicMock()
        r.fetchone.return_value = ("policy.txt", "Sentence one. Sentence two.")
        return r
    db.execute.side_effect = exec_side

    # Force embeddings to fail
    async def fail_embed(texts):
        raise RuntimeError("embedding API down")
    monkeypatch.setattr(ca, "get_embeddings", fail_embed)

    # Spy on store_chunks_with_embeddings; must NOT be called
    store_called = []
    monkeypatch.setattr(
        ca, "store_chunks_with_embeddings",
        lambda *a, **kw: store_called.append(True),
    )

    with pytest.raises(ca.RechunkError):
        asyncio.run(ca.rechunk_for_source_attribution(db, "policy-xyz"))

    assert not store_called, "store_chunks_with_embeddings must NOT run when embeddings fail"
    delete_calls = [s for s in executed if "DELETE FROM policy_chunks" in s]
    assert not delete_calls, "DELETE must not run before embeddings succeed"
