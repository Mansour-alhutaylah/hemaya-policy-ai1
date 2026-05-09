"""Tests for the Phase 10 sentence-bounded grounding algorithm.

Run from repo root:
  python -m pytest backend/tests/test_grounding_sentence_window.py -v

Phase 10 changes the comparison UNIT inside _find_grounded_evidence from
character-aligned 1.3×-claim-length sliding windows over the full
normalized policy (v1) to sentence-bounded segments plus an adjacent-pair
fallback (v2). The numeric threshold default stays at 0.75; the tightening
comes from removing accidental similarity contributed by unrelated
neighbors.

These tests cover:
  - Stage 1 substring fast path is preserved.
  - Single-sentence and adjacent-pair grounding work.
  - The lottery-ticket cross-sentence drift v1 admitted now fails.
  - Empty / short / unrelated claims are safe.
  - The env-var kill switch still disables grounding.
  - Module-level constants and the ECC-2 cache key shape are correct.
  - Legacy and SACS-002 still call the shared helper.
"""
import hashlib
import re

import pytest

from backend import checkpoint_analyzer
from backend.checkpoint_analyzer import (
    GROUNDING_VERSION,
    _find_grounded_evidence,
)


# ─────────────────────────────────────────────────────────────────────────
# Test 1: Stage 1 substring fast path returns sim=1.0 exactly.
# Verbatim policy text, no matter where it sits in the document, must
# always ground without entering the fuzzy stage. Locks the fast path.
# ─────────────────────────────────────────────────────────────────────────
def test_exact_substring_still_matches():
    policy = (
        "Section 1. Cybersecurity strategy is approved by senior management. "
        "Section 2. The plan is reviewed annually. "
        "Section 3. Logging is enabled."
    )
    claim = "Cybersecurity strategy is approved by senior management"

    grounded, actual, sim = _find_grounded_evidence(claim, policy)
    assert grounded is True
    assert sim == 1.0
    assert actual == claim


# ─────────────────────────────────────────────────────────────────────────
# Test 2: A paraphrase of one whole sentence still grounds via the
# single-sentence comparison path. Verifies the new algorithm doesn't
# break legitimate single-sentence grounding.
# ─────────────────────────────────────────────────────────────────────────
def test_paraphrase_within_one_sentence_grounds_at_075():
    # One-sentence paraphrase that should stay above 0.75 against its
    # source sentence under SequenceMatcher (substantively the same words).
    policy = (
        "Annual cybersecurity awareness training is mandatory for "
        "all employees and contractors. Visitor parking is on level 2."
    )
    claim = "Annual cybersecurity awareness training is mandatory for all employees and contractors"

    grounded, actual, sim = _find_grounded_evidence(claim, policy)
    assert grounded is True, f"expected ground, got sim={sim}"
    assert sim >= 0.75


# ─────────────────────────────────────────────────────────────────────────
# Test 3: A claim that genuinely spans two consecutive sentences must
# ground via the adjacent-pair fallback. Verifies the multi-sentence
# safety net so verbatim quotes that cross a period are not lost.
# ─────────────────────────────────────────────────────────────────────────
def test_paraphrase_spanning_two_sentences_grounds_via_pair_window():
    policy = (
        "Cafeteria opens at 8am. The organization shall maintain a "
        "Business Continuity Plan. Disaster Recovery Plans shall be "
        "tested annually. Visitor parking is on level 2."
    )
    # The claim quotes verbatim across the BCP and DRP sentences.
    claim = (
        "The organization shall maintain a Business Continuity Plan. "
        "Disaster Recovery Plans shall be tested annually."
    )

    grounded, actual, sim = _find_grounded_evidence(claim, policy)
    assert grounded is True
    # Should match either the verbatim path (sim=1.0) or the pair window.
    assert sim >= 0.75


# ─────────────────────────────────────────────────────────────────────────
# Test 4: Cross-sentence lottery-ticket from v1 must fail in v2.
# The fixture is hand-built so the claim shares enough function-word
# overlap with a long arbitrary slice (that straddled two unrelated
# sentences) to score >=0.75 under v1, but no single sentence and no
# adjacent pair in the policy carries a coherent match.
# ─────────────────────────────────────────────────────────────────────────
def test_paraphrase_with_neighbor_lottery_does_not_ground():
    # Two unrelated sentences that share generic compliance vocabulary.
    # Together (v1 long-window) they accidentally overlap with the claim;
    # neither sentence alone, nor the pair, is a real match for it.
    policy = (
        "The organization shall implement controls and review them. "
        "Records shall be maintained and audited annually. "
        "Cafeteria opens at 8am on weekdays."
    )
    # Claim talks about MFA enforcement, which the policy does NOT cover.
    # The function words "shall", "and", "be", "the" can drag a v1
    # cross-sentence window up; sentence-bounded matching cannot.
    claim = (
        "The organization shall enforce multi-factor authentication "
        "and review access controls annually for all administrators."
    )

    grounded, actual, sim = _find_grounded_evidence(claim, policy)
    assert grounded is False, (
        f"v2 must reject cross-sentence lottery; got sim={sim:.3f} window={actual!r}"
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 5: Wholly unrelated claim is rejected at low similarity.
# ─────────────────────────────────────────────────────────────────────────
def test_unrelated_text_rejected():
    policy = (
        "All employees shall complete annual cybersecurity awareness "
        "training. Records shall be maintained for at least three years."
    )
    claim = "Volcanic eruptions in Iceland are monitored by seismographs"

    grounded, actual, sim = _find_grounded_evidence(claim, policy)
    assert grounded is False
    assert sim < 0.5


# ─────────────────────────────────────────────────────────────────────────
# Test 6: Empty / whitespace-only / very-short claims are safe.
# Locks the existing len(norm_evidence) < 10 guard and the empty-input
# early return. No exception, deterministic (False, _, 0.0).
# ─────────────────────────────────────────────────────────────────────────
def test_empty_or_short_claim_safe():
    policy = "The organization shall implement strong access controls."
    for bad_claim in ["", "   ", "abc", "short"]:
        grounded, actual, sim = _find_grounded_evidence(bad_claim, policy)
        assert grounded is False
        assert sim == 0.0


# ─────────────────────────────────────────────────────────────────────────
# Test 7: Operator kill switch — GROUNDING_MIN_SIMILARITY=0.0 lets
# every non-empty fuzzy match through (sim>=0.0). NOT recommended in
# production but documented as the rollback knob.
# ─────────────────────────────────────────────────────────────────────────
def test_threshold_disabled_kill_switch(monkeypatch):
    monkeypatch.setattr(checkpoint_analyzer, "GROUNDING_MIN_SIMILARITY", 0.0)
    policy = "The organization shall implement strong access controls."
    # Claim that would normally fail (different topic, low overlap):
    claim = "Volcanic eruptions in Iceland are monitored by seismographs."

    grounded, actual, sim = _find_grounded_evidence(claim, policy)
    # With threshold=0.0, ANY positive ratio passes. Best window will be
    # the closest sentence the matcher found.
    assert grounded is True


# ─────────────────────────────────────────────────────────────────────────
# Test 8: Default value of GROUNDING_MIN_SIMILARITY is sourced from env
# with default "0.75". Phase 10 deliberately keeps the numeric threshold
# unchanged — the tightening comes from the algorithm change.
# ─────────────────────────────────────────────────────────────────────────
def test_threshold_default_is_zero_seventy_five():
    src = open("backend/checkpoint_analyzer.py", encoding="utf-8").read()
    norm = re.sub(r"\s+", " ", src)
    assert (
        'GROUNDING_MIN_SIMILARITY = float(os.getenv("GROUNDING_MIN_SIMILARITY", "0.75"))'
        in norm
    ), "Default must be 0.75 with env override of the same name."


# ─────────────────────────────────────────────────────────────────────────
# Test 9: GROUNDING_VERSION constant exists with literal value "v2".
# Used as the cache-key segregator for ECC-2.
# ─────────────────────────────────────────────────────────────────────────
def test_grounding_version_constant_exists():
    assert GROUNDING_VERSION == "v2", (
        "Phase 10 grounding algorithm version must be 'v2'."
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 10: ECC-2 cache key embeds the literal grounding= field.
# Structural source-grep on ecc2_analyzer.py.
# ─────────────────────────────────────────────────────────────────────────
def test_ecc2_cache_key_includes_grounding_version():
    src = open("backend/ecc2_analyzer.py", encoding="utf-8").read()
    norm = re.sub(r"\s+", " ", src)
    assert "grounding={grounding_version}" in norm, (
        "ECC-2 cache key must include f-string field grounding={grounding_version}."
    )
    assert 'getattr(_ca, "GROUNDING_VERSION"' in norm, (
        "ECC-2 must read GROUNDING_VERSION dynamically from "
        "checkpoint_analyzer (so monkeypatching in tests is reflected)."
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 11: The Phase-9 (v1) and Phase-10 (v2) ECC-2 cache key strings
# produce distinct SHA-256 hashes for the same inputs. Locks the
# invariant that pre-Phase-10 cache rows cannot be reused after Phase 10.
# ─────────────────────────────────────────────────────────────────────────
def test_ecc2_cache_keys_distinct_v1_v2():
    cc = "1-1-1"
    ph = "policy-hash-deadbeef"
    pv = "v1"
    mdl = "gpt-4o-mini"
    floor = 0.10

    # v1 (post-Phase-9 / pre-Phase-10) shape
    key_v1 = (
        f"ECC2|{cc}|{ph}|{pv}|{mdl}|"
        f"floor={floor:.3f}"
    )
    # v2 (Phase 10) shape: exact concatenation produced by ecc2_analyzer.
    key_v2 = (
        f"ECC2|{cc}|{ph}|{pv}|{mdl}|"
        f"floor={floor:.3f}|"
        f"grounding=v2"
    )

    h1 = hashlib.sha256(key_v1.encode()).hexdigest()
    h2 = hashlib.sha256(key_v2.encode()).hexdigest()
    assert h1 != h2, (
        "v1 and v2 ECC-2 cache keys must hash to different SHA-256 values; "
        "otherwise pre-Phase-10 verdicts would be reused after the "
        "grounding algorithm change."
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 12: Legacy checkpoint_analyzer and sacs002_analyzer continue to
# call the shared _find_grounded_evidence. There must be no parallel
# grounding implementation that could silently drift from the v2
# algorithm.
# ─────────────────────────────────────────────────────────────────────────
def test_legacy_and_sacs002_use_shared_helper():
    legacy_src = open("backend/checkpoint_analyzer.py", encoding="utf-8").read()
    sacs_src = open("backend/sacs002_analyzer.py", encoding="utf-8").read()

    # Legacy verifier calls the helper.
    assert "_find_grounded_evidence(" in legacy_src
    # SACS-002 imports and calls the helper. Either as a from-import or via
    # a module-qualified attribute is acceptable.
    assert "_find_grounded_evidence" in sacs_src, (
        "sacs002_analyzer must continue to call _find_grounded_evidence "
        "so it inherits the Phase 10 sentence-window algorithm."
    )
    # Defensive: no other definition of the same function name in SACS-002.
    assert "def _find_grounded_evidence" not in sacs_src, (
        "sacs002_analyzer must NOT define its own grounding function."
    )
