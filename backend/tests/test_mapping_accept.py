"""Tests for the Phase 6 mapping-accept idempotency.

Run from repo root:  python -m pytest backend/tests/test_mapping_accept.py -v

The accept_mapping endpoint must be safe to call twice on the same
mapping_id. Backend defense is the partial unique index
uq_gaps_mapping_id (gaps.mapping_id WHERE mapping_id IS NOT NULL) plus
INSERT ... ON CONFLICT DO NOTHING in the accept path.
"""
import re


def _normalize(s):
    return re.sub(r"\s+", " ", s)


# ─────────────────────────────────────────────────────────────────────────
# Test 1: accept_mapping uses ON CONFLICT against the partial unique index.
# Locks the contract that prevents the double-accept race.
# ─────────────────────────────────────────────────────────────────────────
def test_accept_mapping_uses_on_conflict():
    src = open("backend/main.py", encoding="utf-8").read()
    norm = _normalize(src)

    # The endpoint must exist and use ON CONFLICT.
    assert "@app.post(\"/api/mappings/{mapping_id}/accept\")" in src
    assert "ON CONFLICT (mapping_id) WHERE mapping_id IS NOT NULL DO NOTHING" in norm, (
        "accept_mapping must use ON CONFLICT (mapping_id) WHERE mapping_id IS NOT NULL "
        "DO NOTHING to remain idempotent under double-call / network retry."
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 2: the legacy check-then-insert pattern is gone.
# Locks against accidental revert that re-introduces the race.
# ─────────────────────────────────────────────────────────────────────────
def test_accept_mapping_no_longer_uses_check_then_insert():
    src = open("backend/main.py", encoding="utf-8").read()
    norm = _normalize(src)
    # The pre-Phase-6 implementation queried "SELECT id FROM gaps WHERE
    # policy_id = :pid AND control_id = :cid AND framework_id = :fid LIMIT 1"
    # before deciding whether to INSERT. That pattern must not remain in the
    # accept flow.
    assert "SELECT id FROM gaps WHERE policy_id = :pid AND control_id = :cid" not in norm, (
        "accept_mapping must not pre-check via SELECT; the ON CONFLICT path "
        "is now authoritative."
    )


# ─────────────────────────────────────────────────────────────────────────
# Test 3: the response shape is preserved.
# accept_mapping still returns {status: 'accepted', gap_created: bool}.
# gap_created is True when this call produced the gap, False on idempotent
# repeat or when the gap was already created.
# ─────────────────────────────────────────────────────────────────────────
def test_accept_mapping_response_shape():
    src = open("backend/main.py", encoding="utf-8").read()
    norm = _normalize(src)
    # Final return statement still returns gap_created flag.
    assert 'return {"status": "accepted", "gap_created": gap_created}' in norm, (
        "Response shape must remain {status, gap_created} so the frontend's "
        "toast logic continues to work."
    )
    # gap_created derives from rowcount of the INSERT, which is 0 on conflict.
    assert "gap_created = (res.rowcount == 1)" in norm, (
        "gap_created must derive from INSERT rowcount, not from a pre-check."
    )
