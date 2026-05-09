"""Phase 11 smoke - backfill + cache-hit attribution + API shape.

Uses the MID policy (16b0987f-...) which has 16 chunks with NULL
page_number from Phase 10's prior runs. Triggers ECC-2 analysis, which
fires rechunk_for_source_attribution exactly once, then a second
analysis run to validate the cache-hit path.

Note on "fresh upload" coverage: the upload route uses the same
extract_text_segments + chunk_text_segments + store_chunks_with_embeddings
pipeline as the backfill rechunk path. If backfill populates
page_number correctly, a fresh PDF upload does too by construction.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import time
from pathlib import Path

# Force UTF-8 stdout for Windows cp1252 console safety (Phase 10 hotfix
# replaced print glyphs but tee/pipe scenarios still benefit from this).
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # type: ignore
load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from backend.ecc2_analyzer import run_ecc2_analysis  # noqa: E402
from backend import checkpoint_analyzer as ca  # noqa: E402

DB_URL = os.getenv("DATABASE_URL")
assert DB_URL
engine = create_engine(DB_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

POLICY_ID = "16b0987f-0c45-4a21-b155-3276b3442dd2"


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def apply_phase11_ddl(db):
    """Idempotent additive DDL — same statements ensure_pgvector_columns runs at startup."""
    statements = [
        "ALTER TABLE policy_chunks ADD COLUMN IF NOT EXISTS page_number INT NULL",
        "ALTER TABLE policy_chunks ADD COLUMN IF NOT EXISTS paragraph_index INT NULL",
        "ALTER TABLE policy_ecc_assessments ADD COLUMN IF NOT EXISTS chunk_id VARCHAR NULL",
        "ALTER TABLE policy_ecc_assessments ADD COLUMN IF NOT EXISTS page_number INT NULL",
        "ALTER TABLE policy_ecc_assessments ADD COLUMN IF NOT EXISTS paragraph_index INT NULL",
    ]
    for stmt in statements:
        try:
            db.execute(text(stmt))
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"  [DDL] {stmt[:60]}... -> {e}")


def chunk_stats(db, pid):
    r = db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE page_number IS NOT NULL) AS with_page,
               COUNT(*) FILTER (WHERE paragraph_index IS NOT NULL) AS with_para,
               COUNT(*) FILTER (WHERE page_number IS NULL AND paragraph_index IS NULL) AS null_both
        FROM policy_chunks WHERE policy_id = :pid
    """), {"pid": pid}).fetchone()
    return {"total": r.total, "with_page": r.with_page,
            "with_para": r.with_para, "null_both": r.null_both}


def assessment_stats(db, pid):
    r = db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE page_number IS NOT NULL) AS with_page,
               COUNT(*) FILTER (WHERE paragraph_index IS NOT NULL) AS with_para,
               COUNT(*) FILTER (WHERE chunk_id IS NOT NULL) AS with_chunk_id
        FROM policy_ecc_assessments
        WHERE policy_id::text = :pid AND framework_id = 'ECC-2:2024'
    """), {"pid": pid}).fetchone()
    return {"total": r.total, "with_page": r.with_page,
            "with_para": r.with_para, "with_chunk_id": r.with_chunk_id}


def grounded_assessment_count(db, pid):
    """Count assessments with grounded evidence (status=compliant or partial)."""
    r = db.execute(text("""
        SELECT COUNT(*) FROM policy_ecc_assessments
        WHERE policy_id::text = :pid AND framework_id = 'ECC-2:2024'
          AND compliance_status IN ('compliant', 'partial')
    """), {"pid": pid}).fetchone()
    return r[0]


def cache_count(db):
    r = db.execute(text("SELECT COUNT(*) FROM ecc2_verification_cache")).fetchone()
    return r[0]


def sample_assessment_json(db, pid, limit=3):
    """Mimic the API JSON shape an entity endpoint would return."""
    rows = db.execute(text("""
        SELECT control_code, compliance_status, evidence_text,
               chunk_id, page_number, paragraph_index, confidence_score
        FROM policy_ecc_assessments
        WHERE policy_id::text = :pid AND framework_id = 'ECC-2:2024'
          AND page_number IS NOT NULL
        ORDER BY control_code
        LIMIT :lim
    """), {"pid": pid, "lim": limit}).fetchall()
    return [dict(zip(r._fields, r)) for r in rows]


async def main():
    print("Phase 11 smoke - source attribution end-to-end")
    print(f"GROUNDING_VERSION={ca.GROUNDING_VERSION!r}")
    print(f"GROUNDING_MIN_SIMILARITY={ca.GROUNDING_MIN_SIMILARITY}")
    print(f"RAG_MIN_RELEVANCE_SCORE={ca.RAG_MIN_RELEVANCE_SCORE}")
    print(f"target policy: {POLICY_ID}")

    # Apply DDL (idempotent)
    section("Apply Phase 11 DDL (idempotent)")
    db = Session()
    try:
        apply_phase11_ddl(db)
        print("  DDL applied")
    finally:
        db.close()

    # BEFORE state
    section("BEFORE")
    db = Session()
    try:
        cs = chunk_stats(db, POLICY_ID)
        ass = assessment_stats(db, POLICY_ID)
        cache_before = cache_count(db)
        grounded_before = grounded_assessment_count(db, POLICY_ID)
        print(f"  policy_chunks: total={cs['total']} with_page={cs['with_page']} "
              f"with_para={cs['with_para']} null_both={cs['null_both']}")
        print(f"  policy_ecc_assessments: total={ass['total']} "
              f"with_page={ass['with_page']} with_chunk_id={ass['with_chunk_id']}")
        print(f"  ecc2_verification_cache rows: {cache_before}")
        print(f"  grounded (compliant+partial) assessments: {grounded_before}")
    finally:
        db.close()

    # ── BACKFILL CHECK ────────────────────────────────────────────────────
    # Run 1: rechunk fires + analysis runs.
    section("RUN 1: backfill + analysis (expect rechunk + GPT calls)")
    db = Session()
    try:
        t0 = time.time()
        await run_ecc2_analysis(db, POLICY_ID)
        db.commit()
        run1_secs = time.time() - t0
        print(f"  RUN 1 done in {run1_secs:.1f}s")
    finally:
        db.close()

    # Verify rechunk populated chunks + assessments
    db = Session()
    try:
        cs1 = chunk_stats(db, POLICY_ID)
        ass1 = assessment_stats(db, POLICY_ID)
        cache_after1 = cache_count(db)
        grounded_after1 = grounded_assessment_count(db, POLICY_ID)
        print(f"  policy_chunks AFTER RUN 1: total={cs1['total']} "
              f"with_page={cs1['with_page']} with_para={cs1['with_para']} "
              f"null_both={cs1['null_both']}")
        print(f"  policy_ecc_assessments AFTER RUN 1: total={ass1['total']} "
              f"with_page={ass1['with_page']} with_chunk_id={ass1['with_chunk_id']}")
        print(f"  cache rows BEFORE={cache_before} AFTER RUN 1={cache_after1} "
              f"new={cache_after1 - cache_before}")
        print(f"  grounded assessments AFTER RUN 1: {grounded_after1}")
    finally:
        db.close()

    # ── CACHE-HIT CHECK ───────────────────────────────────────────────────
    # Run 2: chunks already source-aware -> no rechunk; cache populated -> GPT not called
    # but page_number must still populate via post-hoc match on cached evidence.
    section("RUN 2: cache-hit (expect no GPT, page_number persists)")

    # Capture call_llm count via instrumentation
    from backend import ecc2_analyzer as _ecc
    original_call_llm = _ecc.call_llm
    call_count = {"n": 0}
    async def counted_llm(*args, **kwargs):
        call_count["n"] += 1
        return await original_call_llm(*args, **kwargs)
    _ecc.call_llm = counted_llm

    db = Session()
    try:
        t0 = time.time()
        await run_ecc2_analysis(db, POLICY_ID)
        db.commit()
        run2_secs = time.time() - t0
        print(f"  RUN 2 done in {run2_secs:.1f}s")
    finally:
        db.close()
        _ecc.call_llm = original_call_llm

    db = Session()
    try:
        cs2 = chunk_stats(db, POLICY_ID)
        ass2 = assessment_stats(db, POLICY_ID)
        cache_after2 = cache_count(db)
        grounded_after2 = grounded_assessment_count(db, POLICY_ID)
        print(f"  call_llm count during RUN 2: {call_count['n']}")
        print(f"  policy_chunks AFTER RUN 2: total={cs2['total']} "
              f"with_page={cs2['with_page']} (must equal RUN 1)")
        print(f"  policy_ecc_assessments AFTER RUN 2: total={ass2['total']} "
              f"with_page={ass2['with_page']} (must equal RUN 1)")
        print(f"  cache rows AFTER RUN 2={cache_after2} "
              f"(should equal RUN 1 if cache-hit path served everything)")
    finally:
        db.close()

    # ── API SHAPE CHECK ───────────────────────────────────────────────────
    section("API JSON shape sample (3 grounded controls with page_number)")
    db = Session()
    try:
        sample = sample_assessment_json(db, POLICY_ID, limit=3)
        for row in sample:
            print(f"  {row['control_code']:10} | "
                  f"{row['compliance_status']:14} | "
                  f"page={row['page_number']!s:>4} | "
                  f"chunk_id={row['chunk_id'] or 'NULL':30}")
            print(f"             evidence: {(row['evidence_text'] or '')[:90]!r}")
    finally:
        db.close()

    # ── ACCEPTANCE ────────────────────────────────────────────────────────
    section("ACCEPTANCE")
    fails = []
    # 1. After RUN 1, chunks must have page_number populated (PDF -> 16 chunks all with page).
    if cs1["with_page"] < cs["total"] - 2:
        # Allow off-by-2 tolerance for whitespace-only segments dropped by extractor.
        fails.append(
            f"backfill: expected most chunks to have page_number after RUN 1, "
            f"got {cs1['with_page']}/{cs1['total']}"
        )
    # 2. Grounded assessments must have page_number populated.
    if ass1["with_page"] == 0 and grounded_after1 > 0:
        fails.append(
            f"attribution: {grounded_after1} grounded assessments but "
            f"page_number populated on 0 - post-hoc match never wrote anything"
        )
    # 3. RUN 2 must NOT call GPT (cache hit path).
    if call_count["n"] > 0:
        fails.append(
            f"cache-hit: GPT was called {call_count['n']} times in RUN 2; "
            f"expected 0 (cache should serve every control)"
        )
    # 4. RUN 2 must NOT change cache row count (no new fresh GPT writes).
    if cache_after2 > cache_after1:
        fails.append(
            f"cache-hit: cache rows grew from {cache_after1} to {cache_after2} in RUN 2; "
            f"expected unchanged (post-hoc attribution doesn't write cache)"
        )
    # 5. RUN 2 chunks/assessments must match RUN 1 (page_number persisted).
    if cs2["with_page"] != cs1["with_page"]:
        fails.append(
            f"persistence: chunk page_number count changed RUN1={cs1['with_page']} "
            f"-> RUN2={cs2['with_page']}"
        )
    if ass2["with_page"] != ass1["with_page"]:
        fails.append(
            f"persistence: assessment page_number count changed "
            f"RUN1={ass1['with_page']} -> RUN2={ass2['with_page']}"
        )
    # 6. API JSON shape must include the new fields.
    if sample and (
        "chunk_id" not in sample[0] or "page_number" not in sample[0]
        or "paragraph_index" not in sample[0]
    ):
        fails.append("API: sample row missing new fields")

    if fails:
        print("FAIL:")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("PASS:")
        print(f"  - backfill rechunked {cs1['total']} chunks, "
              f"{cs1['with_page']} have page_number")
        print(f"  - grounded assessments with page_number: "
              f"{ass1['with_page']}/{grounded_after1}")
        print(f"  - RUN 2 cache-hit: GPT calls={call_count['n']}, cache rows unchanged")
        print(f"  - new fields appear in API JSON shape")


if __name__ == "__main__":
    asyncio.run(main())
