"""Tests for the Phase 9 RAG relevance floor in _find_relevant_sections.

Run from repo root:
  python -m pytest backend/tests/test_rag_relevance_floor.py -v

The retrieval scorer combines normalized keyword + BM25 signals and
produces a per-query relative score (top chunk ≈ 1.0). Phase 9 adds a
RAG_MIN_RELEVANCE_SCORE floor that filters chunks whose combined score
falls below the threshold. Default is 0.10. Setting it to 0.0 disables
the floor and restores the legacy fallback.
"""
import re

import pytest

from backend import checkpoint_analyzer
from backend.checkpoint_analyzer import _find_relevant_sections


def _normalize(s):
    return re.sub(r"\s+", " ", s)


def _chunks(*texts, classifications=None):
    """Build the {text, classification} dicts the scorer expects."""
    if classifications is None:
        classifications = ["descriptive"] * len(texts)
    return [{"text": t, "classification": c}
            for t, c in zip(texts, classifications)]


# ─────────────────────────────────────────────────────────────────────────
# Test 1: Low-score chunks are filtered when the default floor is active.
# Synthesizes a clear signal (one chunk with all keywords) and clear noise
# (chunks unrelated to the requirement). With the floor at 0.10 the noise
# chunks are dropped from the returned focused_text.
# ─────────────────────────────────────────────────────────────────────────
def test_low_score_chunks_are_filtered(monkeypatch):
    monkeypatch.setattr(checkpoint_analyzer, "RAG_MIN_RELEVANCE_SCORE", 0.10)
    chunks = _chunks(
        # Strong: contains every keyword
        "The cybersecurity strategy is approved by senior management and reviewed annually.",
        # Pure noise: nothing related to the requirement
        "The cafeteria opens at 8am on weekdays.",
        "Building access cards expire after one year.",
        "Annual leave entitlement is 21 days for full-time employees.",
    )
    requirement = "Cybersecurity strategy approved by senior management"
    keywords = ["cybersecurity", "strategy", "approved", "senior", "management"]

    focused, quality = _find_relevant_sections(
        chunks, requirement, keywords, bm25=None, offset=0
    )
    # Top scorer is included; pure-noise chunks should not be.
    assert "cybersecurity strategy is approved" in focused
    assert "cafeteria" not in focused
    assert "leave entitlement" not in focused
    assert quality > 0.5  # top chunk dominates the per-query score


# ─────────────────────────────────────────────────────────────────────────
# Test 2: When every chunk scores high (multiple genuine matches), all of
# them are kept — the floor only excludes the bottom of the distribution.
# ─────────────────────────────────────────────────────────────────────────
def test_high_score_chunks_are_kept(monkeypatch):
    monkeypatch.setattr(checkpoint_analyzer, "RAG_MIN_RELEVANCE_SCORE", 0.10)
    chunks = _chunks(
        "Cybersecurity strategy approved by senior management.",
        "Senior management reviews the cybersecurity strategy annually.",
        "Cybersecurity policies are documented and approved.",
        "Senior management approves all cybersecurity decisions.",
    )
    requirement = "Cybersecurity strategy approved by senior management"
    keywords = ["cybersecurity", "strategy", "approved", "senior", "management"]

    focused, quality = _find_relevant_sections(
        chunks, requirement, keywords, bm25=None, offset=0
    )
    # All four chunks contain the keywords — none should be filtered.
    for c in chunks:
        assert c["text"] in focused, f"chunk dropped unexpectedly: {c['text']!r}"
    assert quality >= 0.5


# ─────────────────────────────────────────────────────────────────────────
# Test 3: When NO chunk passes the threshold, return ("", 0.0) cleanly.
# Empty result is a deliberate "no relevant evidence" signal — downstream
# GPT verifier handles it correctly.
# ─────────────────────────────────────────────────────────────────────────
def test_no_chunks_passing_threshold_returns_empty(monkeypatch):
    # Force a very strict floor so even a moderately-relevant chunk is filtered.
    monkeypatch.setattr(checkpoint_analyzer, "RAG_MIN_RELEVANCE_SCORE", 0.99)
    chunks = _chunks(
        "Cafeteria menu changes weekly.",
        "Visitor parking is on the second floor.",
        "Office supplies budget is reviewed quarterly.",
    )
    requirement = "Cybersecurity strategy approved by senior management"
    keywords = ["cybersecurity", "strategy", "approved"]

    focused, quality = _find_relevant_sections(
        chunks, requirement, keywords, bm25=None, offset=0
    )
    assert focused == "", "Empty result expected when no chunk passes the floor"
    assert quality == 0.0
    # Most importantly: no exception.


# ─────────────────────────────────────────────────────────────────────────
# Test 4: With RAG_MIN_RELEVANCE_SCORE=0.0 the legacy "fewer than 3
# selected → return all chunks" fallback still fires. Locks backward
# compatibility for any operator who needs to disable the floor.
# ─────────────────────────────────────────────────────────────────────────
def test_threshold_disabled_preserves_legacy_fallback(monkeypatch):
    monkeypatch.setattr(checkpoint_analyzer, "RAG_MIN_RELEVANCE_SCORE", 0.0)
    chunks = _chunks(
        "Cafeteria opens at 8am.",
        "Visitor parking is reserved.",
    )
    requirement = "Cybersecurity strategy approved by senior management"
    keywords = ["cybersecurity", "strategy"]

    focused, _ = _find_relevant_sections(
        chunks, requirement, keywords, bm25=None, offset=0
    )
    # Legacy fallback returns all chunks joined when fewer than 3 are
    # selected, regardless of relevance.
    for c in chunks:
        assert c["text"] in focused, (
            "Legacy fallback must include every chunk when "
            "RAG_MIN_RELEVANCE_SCORE=0.0 and selected count < 3"
        )


# ─────────────────────────────────────────────────────────────────────────
# Test 5: Default constant value is 0.10, sourced from env with that
# fallback default. Locks the documented behavior.
# ─────────────────────────────────────────────────────────────────────────
def test_threshold_default_is_zero_one():
    # Read the source to assert both the env default and the constant binding
    # are correct. (We can't reliably re-import the module here because it's
    # cached and may have been mutated by other tests.)
    src = open("backend/checkpoint_analyzer.py", encoding="utf-8").read()
    norm = _normalize(src)
    assert 'RAG_MIN_RELEVANCE_SCORE = float(os.getenv("RAG_MIN_RELEVANCE_SCORE", "0.10"))' in norm, (
        "Default must be 0.10 with env override of the same name."
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 6: ECC-2 and SACS-002 inherit the floor through their continued
# use of _find_relevant_sections. Locks the boundary against accidental
# divergence (e.g., a future commit that introduces a parallel scorer in
# either structured analyzer would silently bypass the floor).
# ─────────────────────────────────────────────────────────────────────────
def test_ecc2_and_sacs002_use_find_relevant_sections():
    ecc2_src = open("backend/ecc2_analyzer.py", encoding="utf-8").read()
    sacs_src = open("backend/sacs002_analyzer.py", encoding="utf-8").read()

    assert "from backend.checkpoint_analyzer import" in ecc2_src
    assert "_find_relevant_sections" in ecc2_src, (
        "ecc2_analyzer must call _find_relevant_sections so the Phase 9 "
        "relevance floor applies to ECC-2 retrieval too."
    )
    assert "_find_relevant_sections" in sacs_src, (
        "sacs002_analyzer must call _find_relevant_sections so the Phase 9 "
        "relevance floor applies to SACS-002 retrieval too."
    )
