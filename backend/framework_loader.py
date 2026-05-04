import os
import json
import uuid
import asyncio
import httpx
from datetime import datetime
from sqlalchemy import text

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Sliding-window extraction parameters. Windows must be ordered and overlapping
# so controls split across boundaries are caught by at least one window.
WINDOW_SIZE = 12000
WINDOW_OVERLAP = 2000

# Per-window retry: 1 initial attempt + 2 retries.
MAX_EXTRACT_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0


def _sliding_windows(s, window_size=WINDOW_SIZE, overlap=WINDOW_OVERLAP):
    """Yield (char_start, char_end, text) tuples in deterministic window order."""
    if not s:
        return
    if len(s) <= window_size:
        yield 0, len(s), s
        return
    step = window_size - overlap
    i = 0
    while i < len(s):
        end = min(i + window_size, len(s))
        yield i, end, s[i:end]
        if i + window_size >= len(s):
            break
        i += step


def _control_dedupe_key(code, title):
    """Stable dedupe key. Prefer normalized control_code; fall back to title."""
    code = (code or "").strip().upper()
    if code:
        return code
    title = (title or "").strip().upper()
    return f"TITLE:{title}" if title else None


async def load_framework_document(db, file_path, framework_name, source_document, force=False):
    from backend.text_extractor import extract_text
    from backend.chunker import chunk_text
    from backend.vector_store import get_embeddings

    # Resolve framework_id from frameworks table
    fw_row = db.execute(text(
        "SELECT id FROM frameworks WHERE name = :fw"
    ), {"fw": framework_name}).fetchone()
    if fw_row:
        framework_id = fw_row[0]
    else:
        framework_id = str(uuid.uuid4())
        db.execute(text(
            "INSERT INTO frameworks (id, name) VALUES (:id, :name)"
        ), {"id": framework_id, "name": framework_name})
        db.commit()

    # Pass file extension so extract_text picks the right parser
    file_ext = os.path.splitext(file_path)[1].lower()
    try:
        content = extract_text(file_path, file_ext)
    except TypeError:
        content = extract_text(file_path)

    if not content or content.startswith("[Extraction error"):
        return {"error": content or "Empty document"}

    # Larger chunks for framework docs
    chunks = chunk_text(content, chunk_size=800, overlap=200)
    if not chunks:
        return {"error": "No chunks created"}

    # Clear old chunks for this framework
    db.execute(text("DELETE FROM framework_chunks WHERE framework_id = :fwid"),
               {"fwid": framework_id})
    db.commit()

    # Embed all chunks in one batch call
    chunk_texts = [c["text"] for c in chunks]
    all_embs = await get_embeddings(chunk_texts)

    stored = 0
    for chunk, emb in zip(chunks, all_embs):
        if emb is None:
            continue
        emb_str = "[" + ",".join(str(x) for x in emb) + "]"
        db.execute(text("""
            INSERT INTO framework_chunks
            (id, framework_id, chunk_text, embedding, chunk_index,
             source_document, created_at)
            VALUES (:id, :fwid, :txt, cast(:emb as vector), :idx, :doc, :cat)
        """), {
            "id": str(uuid.uuid4()), "fwid": framework_id,
            "txt": chunk["text"], "emb": emb_str,
            "idx": chunk.get("chunk_index", 0),
            "doc": source_document, "cat": datetime.utcnow(),
        })
        stored += 1
    db.commit()
    print(f"Framework {framework_name}: {stored} chunks stored")

    result = {"framework": framework_name, "chunks_created": stored,
              "source": source_document, "status": "loaded"}

    # Auto-extract controls and generate checkpoints from the framework text
    print(f"  Extracting controls from {framework_name} (force={force})...")
    extract_info = await extract_controls_from_framework(
        db, framework_name, framework_id, content, force=force
    )
    result["controls_extracted"] = extract_info["controls_inserted"]
    result["extraction_complete"] = extract_info["extraction_complete"]
    result["failed_windows_count"] = len(extract_info["windows_failed"])
    result["failed_windows"] = extract_info["windows_failed"]
    result["extraction_warnings"] = []
    result["warning"] = None
    if not extract_info["extraction_complete"]:
        # Surface incompleteness at every level the API exposes:
        #   - status flips to "incomplete" so a UI checking only this field is correct
        #   - warning is a stable single string a UI can render as a banner
        #   - extraction_warnings is the structured list with the failure summary
        result["status"] = "incomplete"
        result["warning"] = "Framework extraction is incomplete. Some controls may be missing."
        result["extraction_warnings"].append(
            f"Extraction incomplete: {len(extract_info['windows_failed'])} of "
            f"{extract_info['windows_total']} windows failed after retries. "
            f"Cache will not be updated; re-run upload to retry."
        )

    print(f"  Generating checkpoints for {framework_name} (force={force})...")
    num_checkpoints = await generate_checkpoints_for_framework(
        db, framework_name, framework_id, content, force=force
    )
    result["checkpoints_generated"] = num_checkpoints

    return result


# ── Step 1: Extract controls from framework text via GPT ─────────────────────

async def extract_controls_from_framework(db, framework_name, framework_id, full_text, force=False):
    """Sliding-window control extraction over the full framework text.

    Each window is sent to GPT with the same prompt at temperature=0; results
    are merged and deduplicated by normalized control_code (or title fallback).

    If force=True, existing controls for this framework_id are staged for delete
    before re-extraction. The delete and the new INSERTs are committed together,
    so a failure mid-extraction rolls back to the prior state (no partial loss).
    """

    if force:
        # Stage delete; do NOT commit yet. The single db.commit() at the end of
        # this function commits delete + inserts atomically.
        deleted = db.execute(text(
            "DELETE FROM control_library WHERE framework_id = :fid"
        ), {"fid": framework_id}).rowcount
        print(f"  [fw-extract] force=True: staged delete of {deleted} existing controls")
    else:
        existing = db.execute(text(
            "SELECT COUNT(*) FROM control_library WHERE framework_id = :fid"
        ), {"fid": framework_id}).fetchone()[0]
        if existing > 0:
            print(f"    {existing} controls already exist for {framework_name}, skipping extraction")
            return {
                "controls_inserted": existing,
                "windows_total": 0,
                "windows_failed": [],
                "extraction_complete": True,
                "raw_controls": existing,
                "deduped_controls": existing,
            }

    text_len = len(full_text or "")
    windows = list(_sliding_windows(full_text or ""))
    print(f"  [fw-extract] full_text={text_len} chars, "
          f"windows={len(windows)} (size={WINDOW_SIZE}, overlap={WINDOW_OVERLAP})")

    system = """Extract ALL cybersecurity control codes and titles from this framework document.
Return ONLY valid JSON:
{
  "controls": [
    {"code": "ECC-1-1-1", "title": "Cybersecurity Governance", "severity": "High",
     "keywords": ["governance", "strategy", "board"]},
    {"code": "ECC-1-2-1", "title": "Cybersecurity Department", "severity": "High",
     "keywords": ["CISO", "department", "security team"]}
  ]
}

Rules:
- Extract EVERY control code you can find (e.g., ECC-X-X-X, A.X.X, AC-X, etc.)
- Include the full title for each control
- Set severity: Critical for data protection/incident controls, High for most, Medium for awareness/documentation
- Include 3-5 relevant keywords per control
- If you can't find structured controls, extract section headings as controls
- If the window contains no controls at all, return {"controls": []}"""

    raw_controls = []  # accumulated across all windows, in window order
    failed_windows = []  # one entry per window that exhausted retries

    for w_idx, (char_start, char_end, window_text) in enumerate(windows):
        win_controls = None
        last_reason = None

        for attempt in range(1, MAX_EXTRACT_ATTEMPTS + 1):
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    r = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                                 "Content-Type": "application/json"},
                        json={
                            "model": "gpt-4o-mini",
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content":
                                    f"FRAMEWORK: {framework_name}\n\nTEXT:\n{window_text}"},
                            ],
                            "temperature": 0.0,
                            "max_tokens": 8000,
                            "response_format": {"type": "json_object"},
                        },
                    )
                if r.status_code != 200:
                    last_reason = f"HTTP {r.status_code}: {r.text[:200]}"
                    print(f"    [fw-extract] window {w_idx+1}/{len(windows)} "
                          f"attempt {attempt}/{MAX_EXTRACT_ATTEMPTS}: failure ({last_reason})")
                else:
                    body = r.json()["choices"][0]["message"]["content"]
                    try:
                        data = json.loads(body)
                    except json.JSONDecodeError as je:
                        last_reason = f"JSONDecodeError: {je}"
                        print(f"    [fw-extract] window {w_idx+1}/{len(windows)} "
                              f"attempt {attempt}/{MAX_EXTRACT_ATTEMPTS}: failure ({last_reason})")
                    else:
                        candidate = data.get("controls")
                        if not isinstance(candidate, list):
                            last_reason = "schema: 'controls' missing or not a list"
                            print(f"    [fw-extract] window {w_idx+1}/{len(windows)} "
                                  f"attempt {attempt}/{MAX_EXTRACT_ATTEMPTS}: failure ({last_reason})")
                        else:
                            win_controls = candidate
                            print(f"    [fw-extract] window {w_idx+1}/{len(windows)} "
                                  f"attempt {attempt}/{MAX_EXTRACT_ATTEMPTS}: success "
                                  f"({len(win_controls)} controls)")
                            break  # exit retry loop
            except (httpx.TimeoutException, httpx.RequestError) as e:
                last_reason = f"network: {type(e).__name__}: {e}"
                print(f"    [fw-extract] window {w_idx+1}/{len(windows)} "
                      f"attempt {attempt}/{MAX_EXTRACT_ATTEMPTS}: failure ({last_reason})")
            except Exception as e:
                last_reason = f"unexpected: {type(e).__name__}: {e}"
                print(f"    [fw-extract] window {w_idx+1}/{len(windows)} "
                      f"attempt {attempt}/{MAX_EXTRACT_ATTEMPTS}: failure ({last_reason})")

            # Don't sleep after the last attempt
            if attempt < MAX_EXTRACT_ATTEMPTS and win_controls is None:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)

        if win_controls is None:
            # All attempts failed; record but continue with remaining windows
            failed_windows.append({
                "failed_window_index": w_idx,
                "char_start": char_start,
                "char_end": char_end,
                "reason": last_reason or "unknown",
                "retry_count": MAX_EXTRACT_ATTEMPTS - 1,
            })
            print(f"    [fw-extract] window {w_idx+1}/{len(windows)}: "
                  f"PERMANENT FAILURE after {MAX_EXTRACT_ATTEMPTS} attempts ({last_reason})")
            continue

        raw_controls.extend(win_controls)

    # Dedupe: first occurrence per normalized key wins. Window order is preserved,
    # so the inserted-control order matches the order they appear in the document.
    seen = {}
    for c in raw_controls:
        key = _control_dedupe_key(c.get("code"), c.get("title"))
        if not key:
            continue  # skip controls with neither a code nor a title
        if key not in seen:
            seen[key] = c

    deduped = list(seen.values())
    skipped_dupes = len(raw_controls) - len(deduped)
    print(f"  [fw-extract] raw={len(raw_controls)} → deduped={len(deduped)} "
          f"(skipped {skipped_dupes} duplicates across windows)")

    inserted = 0
    for ctrl in deduped:
        db.execute(text("""
            INSERT INTO control_library
            (id, control_code, title, keywords,
             severity_if_missing, framework_id, created_at)
            VALUES (:id, :cc, :title, :kw, :sev, :fid, :cat)
        """), {
            "id": str(uuid.uuid4()),
            "cc": (ctrl.get("code") or "").strip(),
            "title": (ctrl.get("title") or "").strip(),
            "kw": json.dumps(ctrl.get("keywords", [])),
            "sev": ctrl.get("severity", "High"),
            "fid": framework_id,
            "cat": datetime.utcnow(),
        })
        inserted += 1

    # Single commit covers both the (optional) delete and all inserts.
    db.commit()
    extraction_complete = (len(failed_windows) == 0)
    print(f"  [fw-extract] inserted {inserted} controls for {framework_name} "
          f"(force={force}, complete={extraction_complete}, "
          f"failed_windows={len(failed_windows)})")
    return {
        "controls_inserted": inserted,
        "windows_total": len(windows),
        "windows_failed": failed_windows,
        "extraction_complete": extraction_complete,
        "raw_controls": len(raw_controls),
        "deduped_controls": len(deduped),
    }


# ── Step 2: Generate YES/NO checkpoints for each control via GPT ─────────────

async def generate_checkpoints_for_framework(db, framework_name, framework_id, full_text, force=False):
    """Use GPT to generate YES/NO checkpoints for each control."""

    if force:
        deleted = db.execute(text(
            "DELETE FROM control_checkpoints WHERE framework = :fwid"
        ), {"fwid": framework_id}).rowcount
        db.commit()
        print(f"  [fw-checkpoints] force=True: deleted {deleted} existing checkpoints")
    else:
        existing = db.execute(text(
            "SELECT COUNT(*) FROM control_checkpoints WHERE framework = :fwid"
        ), {"fwid": framework_id}).fetchone()[0]
        if existing > 0:
            print(f"    {existing} checkpoints already exist for {framework_name}, skipping")
            return existing

    # Get all controls for this framework
    controls = db.execute(text(
        "SELECT id, control_code, title, keywords "
        "FROM control_library WHERE framework_id = :fid"
    ), {"fid": framework_id}).fetchall()

    if not controls:
        print(f"    No controls found for {framework_name}")
        return 0

    total_checkpoints = 0

    # Process controls in batches of 10 for efficiency
    for i in range(0, len(controls), 10):
        batch = controls[i:i + 10]
        batch_info = "\n".join(f"- {c[1]}: {c[2]}" for c in batch)

        system = """For each control listed, generate 3-5 specific YES/NO checkpoints
that an auditor would verify. Each checkpoint must be a concrete, testable requirement.

Return ONLY valid JSON:
{
  "checkpoints": [
    {
      "control_code": "ECC-1-1-1",
      "items": [
        {"index": 1, "requirement": "Cybersecurity strategy document exists",
         "keywords": ["strategy", "cybersecurity strategy"]},
        {"index": 2, "requirement": "Strategy approved by board/management",
         "keywords": ["board", "approved", "management", "CEO"]},
        {"index": 3, "requirement": "Annual review cycle defined",
         "keywords": ["annual", "yearly", "review cycle"]}
      ]
    }
  ]
}

Rules:
- Each checkpoint must be verifiable as YES or NO
- Keywords should be words you'd search for in a policy document
- 3-5 checkpoints per control (more for complex controls)
- Be specific: "MFA required for remote access" not "authentication exists"
- Include keywords that would appear in a compliant policy"""

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                             "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content":
                                f"FRAMEWORK: {framework_name}\n\n"
                                f"CONTROLS:\n{batch_info}\n\n"
                                f"FRAMEWORK TEXT (for context):\n{full_text[:5000]}"},
                        ],
                        "temperature": 0.0,
                        "max_tokens": 4000,
                        "response_format": {"type": "json_object"},
                    },
                )
                if r.status_code != 200:
                    print(f"    GPT error generating checkpoints "
                          f"batch {i // 10 + 1}: {r.status_code}")
                    continue

                data = json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            print(f"    Checkpoint generation error batch {i // 10 + 1}: {e}")
            continue

        for ctrl_cp in data.get("checkpoints", []):
            cc = ctrl_cp.get("control_code", "")
            for item in ctrl_cp.get("items", []):
                req = item.get("requirement", "")
                if not req:
                    continue
                db.execute(text("""
                    INSERT INTO control_checkpoints
                    (id, framework, control_code, checkpoint_index,
                     requirement, keywords, weight)
                    VALUES (:id, :fw, :cc, :idx, :req, :kw, 1.0)
                """), {
                    "id": str(uuid.uuid4()),
                    "fw": framework_id,
                    "cc": cc,
                    "idx": item.get("index", 1),
                    "req": req,
                    "kw": json.dumps(item.get("keywords", [])),
                })
                total_checkpoints += 1

        db.commit()
        print(f"    Checkpoints batch {i // 10 + 1}/"
              f"{(len(controls) + 9) // 10}: {total_checkpoints} total")

    print(f"    Generated {total_checkpoints} checkpoints "
          f"for {len(controls)} controls")

    # Sync control_library with any new checkpoint control_codes
    from backend.checkpoint_seed import ensure_control_library_sync
    ensure_control_library_sync(db)

    return total_checkpoints


# ── Vector search for framework context ──────────────────────────────────────

def get_framework_context(db, framework_name, query_embedding, top_k=5):
    emb_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    try:
        results = db.execute(text("""
            SELECT fc.chunk_text, cl.control_code, fc.section_title,
                   1 - (fc.embedding <=> cast(:emb as vector)) AS similarity
            FROM framework_chunks fc
            JOIN frameworks f ON fc.framework_id = f.id
            LEFT JOIN control_library cl ON fc.control_id = cl.id
            WHERE f.name = :fw AND fc.embedding IS NOT NULL
            ORDER BY fc.embedding <=> cast(:emb as vector)
            LIMIT :top_k
        """), {"emb": emb_str, "fw": framework_name, "top_k": top_k}).fetchall()
    except Exception:
        return []
    return [{"text": r[0], "control_code": r[1],
             "section_title": r[2], "similarity": float(r[3])} for r in results]


def get_framework_stats(db):
    results = db.execute(text("""
        SELECT f.name, COUNT(*) as chunks,
               COUNT(DISTINCT fc.source_document) as docs
        FROM framework_chunks fc
        JOIN frameworks f ON fc.framework_id = f.id
        GROUP BY f.name
    """)).fetchall()
    return {r[0]: {"chunks": r[1], "documents": r[2]} for r in results}
