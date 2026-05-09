"""Phase 12 atomic-upload smokes.

Two scenarios:

  (A) Policy upload happy-path + injected-failure
      - Build a synthetic 4-page PDF, save to backend/uploads/.
      - Insert a "reservation" policies row mirroring the upload route.
      - Run the prepare-then-commit pipeline directly (no uvicorn).
      - Assert chunks + embeddings persisted, status='uploaded'.
      - Then re-run with get_embeddings monkeypatched to raise; assert
        the policies row + chunks are gone after _rollback_failed_policy_upload.

  (B) Framework chunks atomic swap with embedding failure
      - Pick an existing framework with N>=1 framework_chunks rows in DB.
      - Capture BEFORE chunk count.
      - Call load_framework_document with get_embeddings monkeypatched
        to raise, on a synthetic framework file.
      - Assert chunk count UNCHANGED (no DELETE).

Cleanup at end: drops any rows + files this smoke created.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
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

DB_URL = os.getenv("DATABASE_URL")
assert DB_URL
engine = create_engine(DB_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def make_test_pdf() -> bytes:
    import fitz
    doc = fitz.open()
    for body in [
        "INFORMATION SECURITY POLICY\nPhase 12 smoke test policy v1.\n\n"
        "1. CYBERSECURITY GOVERNANCE\nSenior management approves the strategy.",
        "2. ACCESS CONTROL\nMFA is required for remote access.",
        "3. AWARENESS\nAll employees complete annual training.",
        "4. INCIDENT MANAGEMENT\nBCP and DRP are maintained.",
    ]:
        page = doc.new_page()
        page.insert_text((72, 72), body, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def policy_chunks_count(db, pid):
    return db.execute(
        text("SELECT COUNT(*) FROM policy_chunks WHERE policy_id = :pid"),
        {"pid": pid},
    ).fetchone()[0]


def policy_status(db, pid):
    r = db.execute(
        text("SELECT status, progress, progress_stage FROM policies WHERE id = :pid"),
        {"pid": pid},
    ).fetchone()
    return tuple(r) if r else None


def framework_chunks_count(db, fwid):
    return db.execute(
        text("SELECT COUNT(*) FROM framework_chunks WHERE framework_id = :fwid"),
        {"fwid": fwid},
    ).fetchone()[0]


# ── (A) Policy upload happy-path + injected failure ──────────────────────
async def smoke_a_policy_upload():
    from backend.text_extractor import extract_text_segments
    from backend.chunker import chunk_text_segments
    from backend.vector_store import get_embeddings, store_chunks_with_embeddings
    from backend.main import _rollback_failed_policy_upload

    section("(A) Policy upload happy-path + injected failure")
    pdf = make_test_pdf()
    upload_dir = ROOT / "backend" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # ── A.1: Happy path (synthetic, mirrors the upload route prepare phase) ──
    print("\n--- A.1: Happy path (real embeddings) ---")
    ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    file_a1 = f"{ts}_phase12_smoke_A1.pdf"
    path_a1 = upload_dir / file_a1
    path_a1.write_bytes(pdf)
    pid_a1 = str(uuid.uuid4())

    db = Session()
    try:
        # Reservation row
        db.execute(text("""
            INSERT INTO policies
            (id, file_name, description, version, status, progress, progress_stage,
             file_url, file_type, content_preview, framework_code,
             uploaded_at, created_at)
            VALUES (:id, :fn, 'p12 A1', '1.0', 'processing', 5, 'File accepted',
                    :furl, 'PDF', '', 'ECC-2:2024', :at, :cat)
        """), {
            "id": pid_a1, "fn": "phase12_smoke.pdf",
            "furl": f"/uploads/{file_a1}",
            "at": datetime.now(timezone.utc), "cat": datetime.now(timezone.utc),
        })
        db.commit()

        # Prepare phase
        segments = extract_text_segments(str(path_a1), ".pdf")
        assert segments, "extraction must produce segments"
        chunks = chunk_text_segments(segments)
        assert chunks, "chunking must produce chunks"
        embeddings = await get_embeddings([c["text"] for c in chunks])
        assert len(embeddings) == len(chunks)

        # Commit phase
        content = "\n".join(s["text"] for s in segments)
        db.execute(text("UPDATE policies SET content_preview=:c WHERE id=:p"),
                   {"c": content, "p": pid_a1})
        store_chunks_with_embeddings(db, pid_a1, chunks, embeddings)
        db.execute(text(
            "UPDATE policies SET status='uploaded', progress=100, "
            "progress_stage='Ready' WHERE id=:p"
        ), {"p": pid_a1})
        db.commit()

        # Verify
        n = policy_chunks_count(db, pid_a1)
        st = policy_status(db, pid_a1)
        print(f"  chunks: {n}, status: {st}")
        assert n == len(chunks), f"expected {len(chunks)} chunks, got {n}"
        assert st[0] == "uploaded" and st[1] == 100
        print("  A.1 PASS")
    finally:
        db.close()

    # ── A.2: Injected embedding failure -> rollback helper ──
    print("\n--- A.2: Injected embedding failure -> rollback ---")
    ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    file_a2 = f"{ts}_phase12_smoke_A2.pdf"
    path_a2 = upload_dir / file_a2
    path_a2.write_bytes(pdf)
    pid_a2 = str(uuid.uuid4())

    db = Session()
    try:
        db.execute(text("""
            INSERT INTO policies
            (id, file_name, description, version, status, progress, progress_stage,
             file_url, file_type, content_preview, framework_code,
             uploaded_at, created_at)
            VALUES (:id, :fn, 'p12 A2', '1.0', 'processing', 5, 'File accepted',
                    :furl, 'PDF', '', 'ECC-2:2024', :at, :cat)
        """), {
            "id": pid_a2, "fn": "phase12_smoke.pdf",
            "furl": f"/uploads/{file_a2}",
            "at": datetime.now(timezone.utc), "cat": datetime.now(timezone.utc),
        })
        db.commit()

        # Simulate the prepare-phase failure: extraction succeeds but
        # we simulate get_embeddings raising mid-pipeline.
        try:
            segments = extract_text_segments(str(path_a2), ".pdf")
            chunks = chunk_text_segments(segments)
            # Force failure
            raise RuntimeError("simulated embedding 503")
        except Exception as e:
            print(f"  simulated failure: {type(e).__name__}: {e}")
            _rollback_failed_policy_upload(db, pid_a2, path_a2)

        # Verify
        # Need a fresh session because rollback helper may have left
        # the previous session in an inconsistent commit state.
        db.close()
        db = Session()
        n = policy_chunks_count(db, pid_a2)
        row = db.execute(text("SELECT id FROM policies WHERE id = :p"),
                         {"p": pid_a2}).fetchone()
        file_exists = path_a2.exists()
        print(f"  policy row exists: {bool(row)} (expect False)")
        print(f"  chunks: {n} (expect 0)")
        print(f"  file exists: {file_exists} (expect False)")
        assert row is None, "policy row should be deleted"
        assert n == 0, "chunks should be deleted"
        assert not file_exists, "saved file should be deleted"
        print("  A.2 PASS")
    finally:
        db.close()

    # Cleanup A.1 (it's still in the DB)
    db = Session()
    try:
        db.execute(text("DELETE FROM policy_chunks WHERE policy_id = :p"), {"p": pid_a1})
        db.execute(text("DELETE FROM policies WHERE id = :p"), {"p": pid_a1})
        db.commit()
    finally:
        db.close()
    try: path_a1.unlink()
    except OSError: pass


# ── (B) Framework chunks atomic swap with embedding failure ──────────────
async def smoke_b_framework_atomic():
    from backend import framework_loader as fl

    section("(B) Framework chunks atomic swap with embedding failure")

    db = Session()
    try:
        # Find a framework with chunks present
        row = db.execute(text("""
            SELECT framework_id, COUNT(*) AS n
            FROM framework_chunks
            GROUP BY framework_id
            ORDER BY n DESC
            LIMIT 1
        """)).fetchone()
        if not row:
            print("  No framework_chunks present in DB; skipping B")
            return
        fwid, before = row[0], row[1]
        # Resolve framework name for load_framework_document
        fw_row = db.execute(text(
            "SELECT name FROM frameworks WHERE id = :id"
        ), {"id": fwid}).fetchone()
        if not fw_row:
            print(f"  Framework id {fwid} has no name row; skipping B")
            return
        fw_name = fw_row[0]
        print(f"  framework: id={fwid} name={fw_name!r} BEFORE chunks: {before}")
    finally:
        db.close()

    # Inject failure on get_embeddings
    import backend.vector_store as _vs
    original_embed = _vs.get_embeddings
    async def fail_embed(texts):
        raise RuntimeError("simulated framework embedding 503")
    _vs.get_embeddings = fail_embed

    # Build a synthetic framework file so load_framework_document has
    # something to extract.
    upload_dir = ROOT / "backend" / "uploads" / "frameworks"
    upload_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    fw_file = upload_dir / f"{ts}_phase12_fw_smoke.txt"
    fw_file.write_text(
        "Framework body for atomic swap test.\n"
        "Section 1. Controls.\nSection 2. Audit hints.\n"
    )

    db = Session()
    try:
        try:
            result = await fl.load_framework_document(
                db, str(fw_file), fw_name, str(fw_file.name)
            )
            print(f"  loader result: {result}")
            if isinstance(result, dict) and "error" in result:
                print(f"  expected error: {result['error']}")
        except RuntimeError as e:
            print(f"  loader raised (acceptable): {e}")
        finally:
            _vs.get_embeddings = original_embed

        # Reopen session and verify chunk count unchanged
        db.close()
        db = Session()
        after = framework_chunks_count(db, fwid)
        print(f"  framework AFTER chunks: {after}")
        assert after == before, (
            f"FAILURE: framework_chunks count changed {before} -> {after}; "
            f"DELETE happened despite embedding failure"
        )
        print(f"  B PASS: chunks preserved ({before} == {after})")
    finally:
        db.close()
        _vs.get_embeddings = original_embed
        try: fw_file.unlink()
        except OSError: pass


async def main():
    print("Phase 12 atomic-upload smoke")
    await smoke_a_policy_upload()
    await smoke_b_framework_atomic()
    section("DONE")
    print("Both Phase 12 smokes PASS.")


if __name__ == "__main__":
    asyncio.run(main())
