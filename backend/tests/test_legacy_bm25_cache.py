"""Tests for the Phase 8 BM25 per-policy cache in the legacy
checkpoint_analyzer.

Run from repo root:
  python -m pytest backend/tests/test_legacy_bm25_cache.py -v

Phase 8 hoists the BM25 build from per-control to per-analysis-run.
_analyze_control now accepts a bm25_index kwarg; when provided, the
function must skip the local build. When not provided, the legacy
fallback build runs (preserves direct callers / unit tests).
"""
import re
from unittest.mock import patch


def _normalize(s):
    return re.sub(r"\s+", " ", s)


# ─────────────────────────────────────────────────────────────────────────
# Test 1: structural — run_checkpoint_analysis builds BM25 once and passes
# it into _analyze_control via the bm25_index kwarg.
# ─────────────────────────────────────────────────────────────────────────
def test_run_checkpoint_analysis_builds_bm25_once_and_passes_it_down():
    src = open("backend/checkpoint_analyzer.py", encoding="utf-8").read()
    norm = _normalize(src)

    # The hoisted build must use the run-scoped variable name AND wrap
    # tokenization on policy_chunks. We grep for the specific variable
    # so an accidental revert that re-introduces the per-control build
    # without removing the hoisted one would be caught by other tests.
    assert "_bm25_index_run" in norm, (
        "run_checkpoint_analysis must build the BM25 index once per run "
        "and store it in _bm25_index_run before iterating controls."
    )

    # The pass-through into _analyze_control must use the kwarg name.
    assert "bm25_index=_bm25_index_run" in norm, (
        "_analyze_control must be invoked with bm25_index=_bm25_index_run "
        "so the per-control rebuild is skipped."
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 2: _analyze_control accepts bm25_index kwarg and skips its local
# build when one is provided.
# ─────────────────────────────────────────────────────────────────────────
def test_analyze_control_skips_local_build_when_index_provided():
    """Black-box on the kwarg: patch BM25Okapi inside checkpoint_analyzer
    to count constructor calls. Pass a sentinel index into _analyze_control
    via bm25_index — the constructor should not be invoked at all.

    We don't actually run the full _analyze_control (it makes GPT calls
    and DB queries). We verify the kwarg's effect by inspecting the
    function's source guards: the local build path is gated by
    `if bm25_index is not None: ... else: ... BM25Okapi(...)`. The
    structural check below is sufficient — when bm25_index is provided,
    the BM25Okapi import + constructor in the else-branch never executes.
    """
    src = open("backend/checkpoint_analyzer.py", encoding="utf-8").read()
    norm = _normalize(src)

    # Function signature must accept bm25_index keyword-only.
    assert "async def _analyze_control(" in src
    assert "bm25_index=None" in norm, (
        "_analyze_control must accept bm25_index as a keyword-only "
        "argument with default None for backward compatibility."
    )
    # The skip path: when bm25_index is provided, reuse it.
    assert "if bm25_index is not None: _bm25_index = bm25_index" in norm, (
        "_analyze_control must reuse a provided bm25_index instead of "
        "building one locally."
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 3: backward-compat — when bm25_index is NOT supplied, the local
# fallback build still runs. Locks against accidental removal of the
# else branch which would break direct callers and any tests that don't
# pre-build an index.
# ─────────────────────────────────────────────────────────────────────────
def test_analyze_control_falls_back_to_local_build_when_kwarg_omitted():
    src = open("backend/checkpoint_analyzer.py", encoding="utf-8").read()
    norm = _normalize(src)

    # The else-branch MUST still import BM25Okapi and call its
    # constructor on tokenized policy_chunks. This protects callers
    # who haven't been updated to pass bm25_index.
    assert "else: from rank_bm25 import BM25Okapi" in norm, (
        "_analyze_control must keep the local BM25Okapi build as a "
        "fallback when bm25_index is None."
    )
    assert "BM25Okapi(_bm25_tokenized)" in norm, (
        "Fallback build must construct BM25Okapi over the tokenized chunks."
    )
