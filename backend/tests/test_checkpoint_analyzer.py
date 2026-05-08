"""Tests for the analysis-side filter that excludes non-active controls.

Run from repo root:  python -m pytest backend/tests/test_checkpoint_analyzer.py -v

The analyzer must only load checkpoints whose parent control_library row
has status='active' or NULL (NULL = legacy backward-compat). This is the
defense against analysis silently scoring against flagged / archived /
needs_review controls.
"""
import re


def _normalize(s):
    """Collapse whitespace so multi-line SQL strings match reliably."""
    return re.sub(r"\s+", " ", s)


# ─────────────────────────────────────────────────────────────────────────
# Test 1: the SQL that loads checkpoints for analysis must JOIN
# control_library and filter on status.
# ─────────────────────────────────────────────────────────────────────────
def test_analyzer_loads_only_active_controls_sql_contract():
    src = open("backend/checkpoint_analyzer.py", encoding="utf-8").read()
    norm = _normalize(src)

    # The analysis SELECT must come FROM control_checkpoints aliased cc
    assert "FROM control_checkpoints cc" in norm, (
        "Analyzer must alias control_checkpoints as cc (JOIN target)"
    )

    # And JOIN control_library aliased cl on the framework + control_code pair
    assert "JOIN control_library cl" in norm, (
        "Analyzer must JOIN control_library to filter by status"
    )
    assert "ON cl.framework_id::text = cc.framework" in norm, (
        "JOIN condition on framework_id must match cc.framework"
    )
    assert "AND cl.control_code = cc.control_code" in norm, (
        "JOIN condition must also match control_code"
    )

    # Status filter — backward compat: NULL is treated as active.
    assert "cl.status IS NULL OR cl.status = 'active'" in norm, (
        "Filter must be (cl.status IS NULL OR cl.status = 'active') — "
        "NULL kept for backward compatibility with legacy controls"
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 2: the older raw SELECT that bypassed control_library is gone.
# Locks against an accidental revert that would re-introduce the
# unfiltered load path.
# ─────────────────────────────────────────────────────────────────────────
def test_analyzer_no_longer_uses_unjoined_select():
    src = open("backend/checkpoint_analyzer.py", encoding="utf-8").read()
    norm = _normalize(src)

    # The pre-Phase-5 SELECT had this exact shape (single line, no JOIN):
    #   FROM control_checkpoints WHERE framework=:fwid
    # We accept it ONLY when followed by "AND control_code" (the admin
    # display path in main.py uses a different form, but the analyzer's
    # main load must not match this exact pattern anymore).
    assert "FROM control_checkpoints WHERE framework=:fwid ORDER BY" not in norm, (
        "Analyzer must not load checkpoints without the control_library JOIN"
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 3: ECC-2 analyzer is unaffected (different tables).
# ─────────────────────────────────────────────────────────────────────────
def test_ecc2_analyzer_does_not_touch_control_checkpoints():
    src = open("backend/ecc2_analyzer.py", encoding="utf-8").read()
    # ECC-2 uses ecc_ai_checkpoints / ecc_framework, not control_checkpoints.
    # If this test ever fails, the structured-framework path has been
    # rewired to share tables with the legacy path and the readiness gate
    # allowlist (_STRUCTURED_FRAMEWORKS) needs review.
    assert "control_checkpoints" not in src
    assert "control_library" not in src
