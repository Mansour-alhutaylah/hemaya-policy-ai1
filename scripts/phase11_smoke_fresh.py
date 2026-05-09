"""Phase 11 self-contained smoke against a synthetic fresh PDF policy.

The original phase11_smoke.py target (16b0987f-...) has its source file
in cloud storage / a different machine, so the local backend/uploads/
dir is missing the file and rechunk correctly errors. This smoke
sidesteps that by:

  1. Building a small in-memory PDF with cybersecurity-relevant content.
  2. Saving it under backend/uploads/<timestamp>_phase11_smoke.pdf.
  3. Inserting a policies row with framework_code='ECC-2:2024'.
  4. Auto-embedding the policy via the legacy path so chunks are created
     with NULL page_number — simulating a pre-Phase-11 uploaded policy.
  5. Running ECC-2 analysis -> backfill rechunk fires -> chunks get
     page_number; analysis runs; assessments get source attribution.
  6. Running ECC-2 analysis a SECOND time -> cache hit, no GPT.
  7. API JSON shape check.
  8. Full cleanup of the test policy + chunks + assessments + file.

Verifies every Phase 11 acceptance criterion the user listed, end-to-end,
without depending on production-stored files.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

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


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def make_test_pdf() -> bytes:
    """Tiny 4-page PDF with policy-style content that ECC-2 controls
    will plausibly match against. Returns raw PDF bytes."""
    import fitz  # PyMuPDF
    doc = fitz.open()

    pages = [
        # Page 1
        "INFORMATION SECURITY POLICY\n"
        "Phase 11 Smoke Test Policy v1.0\n\n"
        "1. CYBERSECURITY GOVERNANCE\n"
        "Cybersecurity strategy is approved by senior management and "
        "reviewed annually. The Chief Information Security Officer "
        "(CISO) is responsible for overseeing the information security "
        "program.",
        # Page 2
        "2. ACCESS CONTROL\n"
        "Multi-factor authentication is required for all remote access "
        "and for administrators accessing privileged systems. Access "
        "rights are reviewed every six months. User accounts are "
        "created through the IT helpdesk following a formal request "
        "process.",
        # Page 3
        "3. AWARENESS AND TRAINING\n"
        "All employees shall complete annual cybersecurity awareness "
        "training. Training topics include phishing, social "
        "engineering, password hygiene, and incident reporting. Records "
        "of training completion are retained for at least three years.",
        # Page 4
        "4. INCIDENT MANAGEMENT\n"
        "The organization shall maintain Business Continuity Plans "
        "(BCP) and Disaster Recovery Plans (DRP). DRPs shall be tested "
        "annually. Incident response procedures are documented and "
        "communicated to all relevant personnel.",
    ]
    for body in pages:
        page = doc.new_page()
        page.insert_text((72, 72), body, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def stats(db, pid):
    chunk_row = db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE page_number IS NOT NULL) AS with_page,
               COUNT(*) FILTER (WHERE page_number IS NULL AND paragraph_index IS NULL) AS null_both
        FROM policy_chunks WHERE policy_id = :pid
    """), {"pid": pid}).fetchone()
    ass_row = db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE page_number IS NOT NULL) AS with_page,
               COUNT(*) FILTER (WHERE chunk_id IS NOT NULL) AS with_chunk_id,
               COUNT(*) FILTER (WHERE compliance_status IN ('compliant', 'partial')) AS grounded
        FROM policy_ecc_assessments
        WHERE policy_id::text = :pid AND framework_id = 'ECC-2:2024'
    """), {"pid": pid}).fetchone()
    return {"chunks": dict(zip(chunk_row._fields, chunk_row)),
            "ass":    dict(zip(ass_row._fields,   ass_row))}


async def main():
    print("Phase 11 self-contained smoke - synthetic fresh PDF + backfill + cache-hit")
    print(f"GROUNDING_VERSION={ca.GROUNDING_VERSION!r}")
    print(f"GROUNDING_MIN_SIMILARITY={ca.GROUNDING_MIN_SIMILARITY}")
    print(f"RAG_MIN_RELEVANCE_SCORE={ca.RAG_MIN_RELEVANCE_SCORE}")

    # ── SETUP ────────────────────────────────────────────────────────────
    section("SETUP: synthesize PDF, insert policy row, save file locally")
    pdf_bytes = make_test_pdf()
    print(f"  synthetic PDF: {len(pdf_bytes)} bytes, 4 pages")

    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    file_name_orig = "phase11_smoke.pdf"
    file_name_disk = f"{timestamp}_{file_name_orig}"
    upload_dir = ROOT / "backend" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = upload_dir / file_name_disk
    pdf_path.write_bytes(pdf_bytes)
    print(f"  saved to {pdf_path}")

    policy_id = str(uuid.uuid4())
    print(f"  policy_id: {policy_id}")

    db = Session()
    try:
        db.execute(text("""
            INSERT INTO policies
            (id, file_name, description, version, status, progress, progress_stage,
             file_url, file_type, content_preview, framework_code,
             uploaded_at, created_at)
            VALUES
            (:id, :fn, :desc, '1.0', 'uploaded', 100, 'Ready',
             :furl, 'PDF', :prev, 'ECC-2:2024',
             :at, :cat)
        """), {
            "id": policy_id, "fn": file_name_orig,
            "desc": "Phase 11 smoke test policy",
            "furl": f"/uploads/{file_name_disk}",
            "prev": "Phase 11 smoke (synthetic content)",
            "at": datetime.now(timezone.utc), "cat": datetime.now(timezone.utc),
        })
        db.commit()
        print(f"  policies row inserted")
    finally:
        db.close()

    cleanup_done = False

    async def cleanup():
        nonlocal cleanup_done
        if cleanup_done:
            return
        cleanup_done = True
        section("CLEANUP")
        d = Session()
        try:
            d.execute(text("DELETE FROM policy_ecc_assessments WHERE policy_id::text = :pid"),
                      {"pid": policy_id})
            d.execute(text("DELETE FROM gaps WHERE policy_id::text = :pid"),
                      {"pid": policy_id})
            d.execute(text("DELETE FROM compliance_results WHERE policy_id::text = :pid"),
                      {"pid": policy_id})
            d.execute(text("DELETE FROM policy_chunks WHERE policy_id = :pid"),
                      {"pid": policy_id})
            d.execute(text("DELETE FROM policies WHERE id = :pid"),
                      {"pid": policy_id})
            d.commit()
            print(f"  DB rows deleted for {policy_id}")
        except Exception as e:
            d.rollback()
            print(f"  cleanup DB error: {e}")
        finally:
            d.close()
        try:
            pdf_path.unlink()
            print(f"  file removed: {pdf_path}")
        except OSError as e:
            print(f"  file cleanup error: {e}")

    try:
        # ── BEFORE ───────────────────────────────────────────────────────
        section("BEFORE: no chunks yet (fresh policy)")
        db = Session()
        try:
            s = stats(db, policy_id)
            print(f"  chunks: {s['chunks']}")
            print(f"  assessments: {s['ass']}")
        finally:
            db.close()

        # ── RUN 1 ────────────────────────────────────────────────────────
        # Auto-embed (legacy, NULL page) -> backfill rechunk fires ->
        # chunks get page_number -> analysis runs -> attribution writes.
        section("RUN 1: auto-embed + backfill rechunk + ECC-2 analysis")
        db = Session()
        gpt_calls = {"n": 0}
        from backend import ecc2_analyzer as _ecc
        original = _ecc.call_llm
        async def counted_llm(*a, **kw):
            gpt_calls["n"] += 1
            return await original(*a, **kw)
        _ecc.call_llm = counted_llm
        try:
            t0 = time.time()
            await run_ecc2_analysis(db, policy_id)
            db.commit()
            run1_secs = time.time() - t0
            print(f"  RUN 1 done in {run1_secs:.1f}s")
            print(f"  GPT calls during RUN 1: {gpt_calls['n']}")
            s1 = stats(db, policy_id)
            print(f"  chunks AFTER RUN 1: {s1['chunks']}")
            print(f"  assessments AFTER RUN 1: {s1['ass']}")
        finally:
            _ecc.call_llm = original
            db.close()

        # ── RUN 2 ────────────────────────────────────────────────────────
        # Chunks already source-aware; cache populated. Expect 0 GPT calls.
        section("RUN 2: cache-hit (no GPT, page_number persists)")
        db = Session()
        gpt_calls_run2 = {"n": 0}
        async def counted_llm_2(*a, **kw):
            gpt_calls_run2["n"] += 1
            return await original(*a, **kw)
        _ecc.call_llm = counted_llm_2
        try:
            t0 = time.time()
            await run_ecc2_analysis(db, policy_id)
            db.commit()
            run2_secs = time.time() - t0
            print(f"  RUN 2 done in {run2_secs:.1f}s")
            print(f"  GPT calls during RUN 2: {gpt_calls_run2['n']}")
            s2 = stats(db, policy_id)
            print(f"  chunks AFTER RUN 2: {s2['chunks']}")
            print(f"  assessments AFTER RUN 2: {s2['ass']}")
        finally:
            _ecc.call_llm = original
            db.close()

        # ── API JSON shape ───────────────────────────────────────────────
        section("API JSON shape sample")
        db = Session()
        try:
            rows = db.execute(text("""
                SELECT control_code, compliance_status, evidence_text,
                       chunk_id, page_number, paragraph_index, confidence_score
                FROM policy_ecc_assessments
                WHERE policy_id::text = :pid AND framework_id = 'ECC-2:2024'
                  AND page_number IS NOT NULL
                ORDER BY control_code
                LIMIT 5
            """), {"pid": policy_id}).fetchall()
            for r in rows:
                d = dict(zip(r._fields, r))
                print(f"  {d['control_code']:10} | {d['compliance_status']:14} | "
                      f"page={d['page_number']!s:>4} | chunk_id={d['chunk_id']}")
                print(f"             evidence: {(d['evidence_text'] or '')[:80]!r}")
        finally:
            db.close()

        # ── ACCEPTANCE ───────────────────────────────────────────────────
        section("ACCEPTANCE")
        fails = []
        if s1["chunks"]["with_page"] == 0:
            fails.append("RUN 1: chunks have NO page_number after backfill rechunk")
        if s1["chunks"]["null_both"] == s1["chunks"]["total"]:
            fails.append("RUN 1: every chunk still has NULL page AND NULL paragraph")
        if s1["ass"]["grounded"] > 0 and s1["ass"]["with_page"] == 0:
            fails.append(
                f"RUN 1: {s1['ass']['grounded']} grounded assessments but 0 have "
                f"page_number -> attribution did not flow to assessments"
            )
        if gpt_calls_run2["n"] > 0:
            fails.append(f"RUN 2: GPT was called {gpt_calls_run2['n']} times "
                         f"(expected 0 - cache should serve)")
        if s2["chunks"]["with_page"] != s1["chunks"]["with_page"]:
            fails.append(f"RUN 2: chunk page_number count drifted "
                         f"{s1['chunks']['with_page']} -> {s2['chunks']['with_page']}")
        if s2["ass"]["with_page"] != s1["ass"]["with_page"]:
            fails.append(f"RUN 2: assessment page_number count drifted "
                         f"{s1['ass']['with_page']} -> {s2['ass']['with_page']}")

        if fails:
            print("FAIL:")
            for f in fails:
                print(f"  - {f}")
            await cleanup()
            sys.exit(1)
        else:
            print("PASS:")
            print(f"  - backfill rechunked {s1['chunks']['total']} chunks; "
                  f"{s1['chunks']['with_page']} have page_number")
            print(f"  - {s1['ass']['grounded']} grounded assessments; "
                  f"{s1['ass']['with_page']} have page_number "
                  f"(chunk_id on {s1['ass']['with_chunk_id']})")
            print(f"  - RUN 2 cache-hit: GPT calls = {gpt_calls_run2['n']}")
            print(f"  - persistence: chunks {s1['chunks']['with_page']} == "
                  f"{s2['chunks']['with_page']}, assessments {s1['ass']['with_page']} == "
                  f"{s2['ass']['with_page']}")
            await cleanup()

    except Exception as e:
        print(f"\nUNCAUGHT: {type(e).__name__}: {e}")
        import traceback as _tb
        _tb.print_exc()
        await cleanup()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
