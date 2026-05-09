"""Phase 10 LIVE GPT smoke - real ECC-2 + SACS-002 analysis with v2 grounding.

Captures BEFORE/AFTER status distributions and per-control flips for:
  - MID ECC-2: Enterprise_Cybersecurity_Policy_ECC.docx (16b0987f-...)
  - SACS-002: SACS002_95_Compliance_Policy.docx (41645d6e-...)

Uses the live run_ecc2_analysis / run_sacs002_analysis entry points.
The new grounding=v2 cache key field naturally segregates from prior
cache rows -> every (control, policy_hash) is a fresh GPT call.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # type: ignore
load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from backend.ecc2_analyzer import run_ecc2_analysis  # noqa: E402
from backend.sacs002_analyzer import run_sacs002_analysis  # noqa: E402
from backend import checkpoint_analyzer as ca  # noqa: E402

DB_URL = os.getenv("DATABASE_URL")
assert DB_URL
engine = create_engine(DB_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

ECC2_MID_POLICY = "16b0987f-0c45-4a21-b155-3276b3442dd2"
SACS_POLICY = "41645d6e-802f-4bfd-bdc2-bad771602f07"


def snapshot_status(db, policy_id, framework_filter):
    """Return dict {control_code: compliance_status}."""
    rows = db.execute(text("""
        SELECT control_code, compliance_status
        FROM policy_ecc_assessments
        WHERE policy_id::text = :pid
          AND framework_id = :fw
        ORDER BY control_code
    """), {"pid": policy_id, "fw": framework_filter}).fetchall()
    return {r[0]: r[1] for r in rows}


def status_counts(snapshot):
    counts = {"compliant": 0, "partial": 0, "non_compliant": 0, "other": 0}
    for s in snapshot.values():
        if s in counts:
            counts[s] += 1
        else:
            counts["other"] += 1
    return counts


def cache_count(db):
    r = db.execute(text("SELECT COUNT(*) FROM ecc2_verification_cache")).fetchone()
    return r[0]


def diff_snapshots(before, after, label):
    print(f"\n=== {label} flips ===")
    flips = []
    for cc in sorted(set(before) | set(after)):
        b = before.get(cc, "(missing)")
        a = after.get(cc, "(missing)")
        if b != a:
            flips.append((cc, b, a))
    print(f"  total flips: {len(flips)}")
    bc = status_counts(before)
    ac = status_counts(after)
    print(f"  BEFORE: compliant={bc['compliant']:3d} partial={bc['partial']:3d} "
          f"non_compliant={bc['non_compliant']:3d}")
    print(f"  AFTER : compliant={ac['compliant']:3d} partial={ac['partial']:3d} "
          f"non_compliant={ac['non_compliant']:3d}")
    print(f"  delta : compliant={ac['compliant']-bc['compliant']:+d} "
          f"partial={ac['partial']-bc['partial']:+d} "
          f"non_compliant={ac['non_compliant']-bc['non_compliant']:+d}")

    # Categorize flips
    def cat(b, a):
        order = {"non_compliant": 0, "partial": 1, "compliant": 2}
        if b not in order or a not in order:
            return "other"
        return "demoted" if order[a] < order[b] else "upgraded"

    demoted = [f for f in flips if cat(f[1], f[2]) == "demoted"]
    upgraded = [f for f in flips if cat(f[1], f[2]) == "upgraded"]
    other = [f for f in flips if cat(f[1], f[2]) == "other"]
    print(f"  demoted: {len(demoted)}  upgraded: {len(upgraded)}  other: {len(other)}")
    print("  --- demotions (first 15) ---")
    for cc, b, a in demoted[:15]:
        print(f"    {cc:10} {b:15} -> {a}")
    if upgraded:
        print("  --- UPGRADES (must explain) ---")
        for cc, b, a in upgraded:
            print(f"    {cc:10} {b:15} -> {a}")
    return flips, demoted, upgraded


async def run_live_smoke():
    print(f"GROUNDING_VERSION = {ca.GROUNDING_VERSION!r}")
    print(f"GROUNDING_MIN_SIMILARITY = {ca.GROUNDING_MIN_SIMILARITY}")
    print(f"RAG_MIN_RELEVANCE_SCORE = {ca.RAG_MIN_RELEVANCE_SCORE}")

    # ECC-2 MID
    print("\n" + "#" * 60)
    print(f"# ECC-2 MID: {ECC2_MID_POLICY}")
    print("#" * 60)
    db = Session()
    try:
        before_ecc = snapshot_status(db, ECC2_MID_POLICY, "ECC-2:2024")
        cache_before_ecc = cache_count(db)
        print(f"BEFORE: {len(before_ecc)} control assessments | "
              f"cache_rows={cache_before_ecc}")
        print(f"BEFORE counts: {status_counts(before_ecc)}")

        t0 = time.time()
        try:
            await run_ecc2_analysis(db, ECC2_MID_POLICY)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"ECC-2 analysis failed: {e!r}")
            raise
        ecc_runtime = time.time() - t0

        after_ecc = snapshot_status(db, ECC2_MID_POLICY, "ECC-2:2024")
        cache_after_ecc = cache_count(db)
        print(f"\nECC-2 runtime: {ecc_runtime:.1f}s")
        print(f"cache_rows BEFORE={cache_before_ecc}, AFTER={cache_after_ecc}, "
              f"new={cache_after_ecc - cache_before_ecc}")
        ecc_flips, ecc_demoted, ecc_upgraded = diff_snapshots(
            before_ecc, after_ecc, "ECC-2 MID")
    finally:
        db.close()

    # SACS-002
    print("\n" + "#" * 60)
    print(f"# SACS-002: {SACS_POLICY}")
    print("#" * 60)
    db = Session()
    try:
        before_sacs = snapshot_status(db, SACS_POLICY, "SACS-002")
        print(f"BEFORE: {len(before_sacs)} control assessments")
        print(f"BEFORE counts: {status_counts(before_sacs)}")

        t0 = time.time()
        try:
            await run_sacs002_analysis(db, SACS_POLICY)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"SACS-002 analysis failed: {e!r}")
            raise
        sacs_runtime = time.time() - t0

        after_sacs = snapshot_status(db, SACS_POLICY, "SACS-002")
        print(f"\nSACS-002 runtime: {sacs_runtime:.1f}s")
        sacs_flips, sacs_demoted, sacs_upgraded = diff_snapshots(
            before_sacs, after_sacs, "SACS-002")
    finally:
        db.close()

    # Verify the new cache key shape was used
    print("\n=== Cache key shape verification ===")
    db = Session()
    try:
        # We can't read the raw key string (it's hashed), but we can confirm
        # the new rows count grew by ~200 (one per ECC-2 control), which
        # means each control got a cache miss and wrote a fresh row under
        # the v2 key. If pre-Phase-10 rows had been reused, no new rows
        # would have been added.
        new_rows_added = cache_after_ecc - cache_before_ecc
        print(f"  new ecc2_verification_cache rows added: {new_rows_added}")
        if new_rows_added < 100:
            print("  WARNING: too few new cache rows - possible stale-cache reuse?")
        else:
            print("  OK: substantial new rows -> grounding=v2 segregation working")

        # Acceptance summary
        print("\n=== ACCEPTANCE CHECK ===")
        all_ok = True
        if ecc_upgraded:
            print(f"  FAIL: ECC-2 has {len(ecc_upgraded)} unexpected upgrades")
            all_ok = False
        if sacs_upgraded:
            print(f"  FAIL: SACS-002 has {len(sacs_upgraded)} unexpected upgrades")
            all_ok = False
        # Tighter-or-equal expectation: any upgrade is suspect.
        # Compliant count must not increase.
        ecc_compliant_before = status_counts(before_ecc)["compliant"]
        ecc_compliant_after = status_counts(after_ecc)["compliant"]
        if ecc_compliant_after > ecc_compliant_before:
            print(f"  FAIL: ECC-2 compliant count increased "
                  f"{ecc_compliant_before} -> {ecc_compliant_after}")
            all_ok = False
        sacs_compliant_before = status_counts(before_sacs)["compliant"]
        sacs_compliant_after = status_counts(after_sacs)["compliant"]
        if sacs_compliant_after > sacs_compliant_before:
            print(f"  FAIL: SACS-002 compliant count increased "
                  f"{sacs_compliant_before} -> {sacs_compliant_after}")
            all_ok = False
        if all_ok:
            print("  PASS: no unexpected upgrades; compliant counts non-increasing")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run_live_smoke())
