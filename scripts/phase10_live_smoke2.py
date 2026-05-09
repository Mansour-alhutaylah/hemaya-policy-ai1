"""Phase 10 LIVE smoke - part 2.

The first run completed ECC-2 successfully but crashed on a cosmetic Unicode
arrow print AFTER the analysis (DB commits already happened). This driver:
  - Reads ECC-2 AFTER state from the DB (no re-run)
  - Reads cache row count delta vs BEFORE=967
  - Runs SACS-002 analysis cleanly (forcing UTF-8 stdout to avoid the same
    cp1252 print bug)
  - Diffs and reports.

ECC-2 BEFORE (captured during the first smoke run):
  compliant=65 partial=40 non_compliant=95
  cache_rows=967
SACS-002 BEFORE (captured during DB recon):
  compliant=19 partial=26 non_compliant=47
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import time
from pathlib import Path

# Force UTF-8 stdout BEFORE any prints from imported analyzers reach it.
# Windows default cp1252 cannot render the analyzer's right-arrow glyphs.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # type: ignore
load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from backend.sacs002_analyzer import run_sacs002_analysis  # noqa: E402
from backend import checkpoint_analyzer as ca  # noqa: E402

DB_URL = os.getenv("DATABASE_URL")
assert DB_URL
engine = create_engine(DB_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

ECC2_MID_POLICY = "16b0987f-0c45-4a21-b155-3276b3442dd2"
SACS_POLICY = "41645d6e-802f-4bfd-bdc2-bad771602f07"

# Captured from run 1
ECC_BEFORE = {"compliant": 65, "partial": 40, "non_compliant": 95}
SACS_BEFORE = {"compliant": 19, "partial": 26, "non_compliant": 47}
ECC_CACHE_BEFORE = 967


def snapshot(db, policy_id, fw):
    rows = db.execute(text("""
        SELECT control_code, compliance_status
        FROM policy_ecc_assessments
        WHERE policy_id::text = :pid AND framework_id = :fw
        ORDER BY control_code
    """), {"pid": policy_id, "fw": fw}).fetchall()
    return {r[0]: r[1] for r in rows}


def counts(snap):
    c = {"compliant": 0, "partial": 0, "non_compliant": 0, "other": 0}
    for s in snap.values():
        c[s if s in c else "other"] += 1
    return c


def diff(before_counts, after_snap, before_snap=None):
    ac = counts(after_snap)
    print(f"  BEFORE: compliant={before_counts['compliant']:3d} "
          f"partial={before_counts['partial']:3d} "
          f"non_compliant={before_counts['non_compliant']:3d}")
    print(f"  AFTER : compliant={ac['compliant']:3d} "
          f"partial={ac['partial']:3d} "
          f"non_compliant={ac['non_compliant']:3d}")
    print(f"  delta : compliant={ac['compliant']-before_counts['compliant']:+d} "
          f"partial={ac['partial']-before_counts['partial']:+d} "
          f"non_compliant={ac['non_compliant']-before_counts['non_compliant']:+d}")
    if before_snap is None:
        return ac, None, None, None
    flips = []
    for cc in sorted(set(before_snap) | set(after_snap)):
        b = before_snap.get(cc, "(missing)")
        a = after_snap.get(cc, "(missing)")
        if b != a:
            flips.append((cc, b, a))
    order = {"non_compliant": 0, "partial": 1, "compliant": 2}
    demoted = [f for f in flips if f[1] in order and f[2] in order and order[f[2]] < order[f[1]]]
    upgraded = [f for f in flips if f[1] in order and f[2] in order and order[f[2]] > order[f[1]]]
    other = [f for f in flips if f not in demoted and f not in upgraded]
    print(f"  total flips: {len(flips)}  demoted: {len(demoted)}  upgraded: {len(upgraded)}  other: {len(other)}")
    if demoted:
        print("  --- demotions (all) ---")
        for cc, b, a in demoted:
            print(f"    {cc:10} {b:15} -> {a}")
    if upgraded:
        print("  --- UPGRADES (require explanation) ---")
        for cc, b, a in upgraded:
            print(f"    {cc:10} {b:15} -> {a}")
    return ac, flips, demoted, upgraded


async def main():
    print(f"GROUNDING_VERSION = {ca.GROUNDING_VERSION!r}")
    print(f"GROUNDING_MIN_SIMILARITY = {ca.GROUNDING_MIN_SIMILARITY}")
    print(f"RAG_MIN_RELEVANCE_SCORE = {ca.RAG_MIN_RELEVANCE_SCORE}")

    # ---- ECC-2 AFTER (already ran in smoke v1) ---------------------------
    print("\n" + "#" * 60)
    print(f"# ECC-2 MID: {ECC2_MID_POLICY}")
    print("#" * 60)
    db = Session()
    try:
        ecc_after = snapshot(db, ECC2_MID_POLICY, "ECC-2:2024")
        ecc_cache_after = db.execute(text("SELECT COUNT(*) FROM ecc2_verification_cache")).fetchone()[0]
        print(f"  cache_rows BEFORE={ECC_CACHE_BEFORE}, AFTER={ecc_cache_after}, "
              f"new={ecc_cache_after - ECC_CACHE_BEFORE}")
        # We don't have per-control BEFORE for ECC-2 (only counts).
        # Diff at count level only; flips count not available.
        ecc_after_counts, _, _, _ = diff(ECC_BEFORE, ecc_after, before_snap=None)
    finally:
        db.close()

    # ---- SACS-002 (now) --------------------------------------------------
    print("\n" + "#" * 60)
    print(f"# SACS-002: {SACS_POLICY}")
    print("#" * 60)
    db = Session()
    try:
        sacs_before_snap = snapshot(db, SACS_POLICY, "SACS-002")
        print(f"  BEFORE rows: {len(sacs_before_snap)}")
        t0 = time.time()
        try:
            await run_sacs002_analysis(db, SACS_POLICY)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"  SACS-002 analysis failed: {type(e).__name__}: {str(e)[:300]}")
            raise
        sacs_runtime = time.time() - t0
        sacs_after_snap = snapshot(db, SACS_POLICY, "SACS-002")
        print(f"  SACS-002 runtime: {sacs_runtime:.1f}s")
        sacs_after_counts, sacs_flips, sacs_demoted, sacs_upgraded = diff(
            SACS_BEFORE, sacs_after_snap, before_snap=sacs_before_snap
        )
    finally:
        db.close()

    # ---- ACCEPTANCE ------------------------------------------------------
    print("\n" + "=" * 60)
    print("ACCEPTANCE CHECK")
    print("=" * 60)
    fails = []
    if ecc_after_counts["compliant"] > ECC_BEFORE["compliant"]:
        fails.append(f"ECC-2 compliant increased: {ECC_BEFORE['compliant']} -> {ecc_after_counts['compliant']}")
    new_cache = ecc_cache_after - ECC_CACHE_BEFORE
    if new_cache < 100:
        fails.append(f"ECC-2 new cache rows too few ({new_cache}); possible stale-cache reuse")
    if sacs_upgraded:
        fails.append(f"SACS-002 has {len(sacs_upgraded)} unexpected upgrades")
    if sacs_after_counts["compliant"] > SACS_BEFORE["compliant"]:
        fails.append(f"SACS-002 compliant increased: {SACS_BEFORE['compliant']} -> {sacs_after_counts['compliant']}")

    if fails:
        print("FAIL:")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("PASS:")
        print(f"  - ECC-2 compliant non-increasing: {ECC_BEFORE['compliant']} -> {ecc_after_counts['compliant']}")
        print(f"  - ECC-2 new grounding=v2 cache rows: {new_cache}")
        print(f"  - SACS-002 compliant non-increasing: {SACS_BEFORE['compliant']} -> {sacs_after_counts['compliant']}")
        print(f"  - SACS-002 cache: N/A (no verification cache by design)")


if __name__ == "__main__":
    asyncio.run(main())
