import os
import json
import uuid
import asyncio
import httpx
from datetime import datetime
from sqlalchemy import text

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Persistent client for all framework-extraction GPT calls (120 s timeout
# because window extraction prompts can return large JSON payloads).
_openai_client = httpx.AsyncClient(
    timeout=120.0,
    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
)

# Sliding-window extraction parameters. Windows must be ordered and overlapping
# so controls split across boundaries are caught by at least one window.
WINDOW_SIZE = 12000
WINDOW_OVERLAP = 2000

# Per-window retry: 1 initial attempt + 2 retries.
MAX_EXTRACT_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0

# Per-checkpoint-batch retry: same shape, but with linearly increasing
# backoff (1 s after attempt 1, 2 s after attempt 2). Retries cover transient
# failure modes (5xx, 429, timeouts, malformed JSON, wrong schema). Permanent
# 4xx (except 429) are not retried.
MAX_CHECKPOINT_ATTEMPTS = 3
CHECKPOINT_RETRY_BACKOFF_SECONDS = 1.0


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
        emb_str = json.dumps(emb)
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
    cp_info = await generate_checkpoints_for_framework(
        db, framework_name, framework_id, content, force=force,
        control_window_map=extract_info.get("control_window_map", {}),
    )
    result["checkpoints_generated"] = cp_info["total_checkpoints"]
    result["failed_checkpoint_batches"] = cp_info["failed_batches"]
    result["failed_checkpoint_batches_count"] = len(cp_info["failed_batches"])

    # If any checkpoint batch failed, the framework has controls without
    # checkpoints — those controls will silently report no findings during
    # analysis ("fake coverage"). Treat this the same as a failed extraction
    # window: flip extraction_complete=False so file_hash is NOT persisted
    # (main.py:/upload/frameworks gates the cache on this flag) and surface
    # the failure to the UI. Recovery requires re-uploading with force=true.
    if cp_info["failed_batches"]:
        result["extraction_complete"] = False
        result["status"] = "incomplete"
        result["warning"] = (result.get("warning")
                             or "Framework extraction is incomplete. "
                                "Some controls may be missing.")
        result["extraction_warnings"].append(
            f"Checkpoint generation incomplete: "
            f"{len(cp_info['failed_batches'])} batch(es) failed "
            f"({sum(len(b['control_codes']) for b in cp_info['failed_batches'])} "
            f"control(s) without checkpoints). "
            f"Cache will not be updated; re-upload with force=true to retry."
        )

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

    # Maps control_code → the window text it was first found in.
    # Passed to generate_checkpoints_for_framework so GPT gets the
    # right section context instead of always using full_text[:5000].
    _window_for_code = {}

    for w_idx, (char_start, char_end, window_text) in enumerate(windows):
        win_controls = None
        last_reason = None

        for attempt in range(1, MAX_EXTRACT_ATTEMPTS + 1):
            try:
                r = await _openai_client.post(
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

        # Tag each control with its source window so we can pass the
        # right context during checkpoint generation (Fix 8).
        for ctrl in win_controls:
            code = (ctrl.get("code") or "").strip()
            if code and code not in _window_for_code:
                _window_for_code[code] = window_text
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
    skipped_conflict = 0
    for ctrl in deduped:
        # ON CONFLICT (framework_id, control_code) DO NOTHING relies on the
        # uq_control_library_framework_code constraint. Defends against:
        #   - residual duplicates from interrupted force=true runs
        #   - concurrent uploads of the same framework
        #   - the check-then-insert race in ensure_control_library_sync
        # On conflict, rowcount==0 and we count it as skipped rather than
        # silently overcount inserted.
        res = db.execute(text("""
            INSERT INTO control_library
            (id, control_code, title, keywords,
             severity_if_missing, framework_id, created_at)
            VALUES (:id, :cc, :title, :kw, :sev, :fid, :cat)
            ON CONFLICT (framework_id, control_code) DO NOTHING
        """), {
            "id": str(uuid.uuid4()),
            "cc": (ctrl.get("code") or "").strip(),
            "title": (ctrl.get("title") or "").strip(),
            "kw": json.dumps(ctrl.get("keywords", [])),
            "sev": ctrl.get("severity", "High"),
            "fid": framework_id,
            "cat": datetime.utcnow(),
        })
        if res.rowcount == 1:
            inserted += 1
        else:
            skipped_conflict += 1

    # Single commit covers both the (optional) delete and all inserts.
    db.commit()
    extraction_complete = (len(failed_windows) == 0)
    print(f"  [fw-extract] inserted {inserted} controls for {framework_name} "
          f"(force={force}, complete={extraction_complete}, "
          f"failed_windows={len(failed_windows)}, "
          f"skipped_conflict={skipped_conflict})")
    return {
        "controls_inserted": inserted,
        "controls_skipped_conflict": skipped_conflict,
        "windows_total": len(windows),
        "windows_failed": failed_windows,
        "extraction_complete": extraction_complete,
        "raw_controls": len(raw_controls),
        "deduped_controls": len(deduped),
        # Maps control_code → source window text; consumed by
        # generate_checkpoints_for_framework for section-aware context.
        "control_window_map": _window_for_code,
    }


# ── Step 2: Generate YES/NO checkpoints for each control via GPT ─────────────

async def _run_checkpoint_batch_loop(
    framework_name, framework_id, controls, full_text, control_window_map
):
    """Pure GPT batch loop. NO database writes — returns
    (pending_rows, failed_batches). The caller decides whether to INSERT
    pending_rows and whether to commit or rollback the surrounding
    transaction. Used by both the bulk path
    (generate_checkpoints_for_framework) and the repair path
    (generate_missing_checkpoints_for_framework).
    """
    failed_batches = []
    pending_rows = []

    for i in range(0, len(controls), 10):
        batch = controls[i:i + 10]
        batch_info = "\n".join(f"- {c[1]}: {c[2]}" for c in batch)

        # Section-aware context: use the source window of the first control
        # in this batch.  Controls are ordered by document position (window
        # order is preserved by extract_controls_from_framework), so the
        # first control's window is a good proxy for the whole batch.
        # Falls back to the first 5000 chars of the full text when no map
        # is available (e.g., force=False path that skipped extraction).
        first_code = batch[0][1] if batch else ""
        batch_context = (
            (control_window_map or {}).get(first_code)
            or (full_text or "")[:5000]
        )

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

        batch_index = i // 10 + 1
        batch_codes = [c[1] for c in batch]
        data = None  # set to a dict with valid 'checkpoints' on success
        last_reason = None
        attempts_used = 0
        permanent = False  # set to True for non-retryable 4xx responses

        for attempt in range(1, MAX_CHECKPOINT_ATTEMPTS + 1):
            attempts_used = attempt
            r = None
            # Transport guard: HTTP / network errors → retryable.
            try:
                r = await _openai_client.post(
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
                                f"FRAMEWORK TEXT (for context):\n{batch_context}"},
                        ],
                        "temperature": 0.0,
                        "max_tokens": 4000,
                        "response_format": {"type": "json_object"},
                    },
                )
            except Exception as e:
                last_reason = f"transport: {type(e).__name__}: {e}"
                print(f"    [fw-checkpoints] batch {batch_index} "
                      f"attempt {attempt}/{MAX_CHECKPOINT_ATTEMPTS}: failure ({last_reason})")
            else:
                if r.status_code != 200:
                    last_reason = f"HTTP {r.status_code}: {r.text[:200]}"
                    # Permanent 4xx (except 429 rate limit) — stop retrying.
                    if 400 <= r.status_code < 500 and r.status_code != 429:
                        permanent = True
                    print(f"    [fw-checkpoints] batch {batch_index} "
                          f"attempt {attempt}/{MAX_CHECKPOINT_ATTEMPTS}: failure ({last_reason})"
                          f"{' [permanent]' if permanent else ''}")
                else:
                    # JSON guard: explicit JSONDecodeError → retryable.
                    try:
                        candidate = json.loads(r.json()["choices"][0]["message"]["content"])
                    except json.JSONDecodeError as e:
                        last_reason = f"JSONDecodeError: {e}"
                        print(f"    [fw-checkpoints] batch {batch_index} "
                              f"attempt {attempt}/{MAX_CHECKPOINT_ATTEMPTS}: failure ({last_reason})")
                    except Exception as e:
                        last_reason = f"response_parse: {type(e).__name__}: {e}"
                        print(f"    [fw-checkpoints] batch {batch_index} "
                              f"attempt {attempt}/{MAX_CHECKPOINT_ATTEMPTS}: failure ({last_reason})")
                    else:
                        # Schema guard: wrong shape → retryable (LLM blip).
                        if not isinstance(candidate.get("checkpoints"), list):
                            last_reason = "schema: 'checkpoints' missing or not a list"
                            print(f"    [fw-checkpoints] batch {batch_index} "
                                  f"attempt {attempt}/{MAX_CHECKPOINT_ATTEMPTS}: failure ({last_reason})")
                        else:
                            data = candidate
                            print(f"    [fw-checkpoints] batch {batch_index} "
                                  f"attempt {attempt}/{MAX_CHECKPOINT_ATTEMPTS}: success "
                                  f"({len(data['checkpoints'])} control entries)")
                            break  # success — exit retry loop

            if permanent:
                break  # don't retry hard 4xx

            # Don't sleep after the last attempt.
            if attempt < MAX_CHECKPOINT_ATTEMPTS:
                await asyncio.sleep(CHECKPOINT_RETRY_BACKOFF_SECONDS * attempt)

        if data is None:
            # All attempts exhausted (or stopped early on permanent 4xx).
            failed_batches.append({
                "batch_index": batch_index,
                "control_codes": batch_codes,
                "reason": last_reason or "unknown",
                "retry_count": max(0, attempts_used - 1),
            })
            print(f"    [fw-checkpoints] batch {batch_index}: PERMANENT FAILURE "
                  f"after {attempts_used} attempt(s) ({last_reason})")
            continue

        # Buffer this batch's rows; do NOT execute INSERT yet.
        for ctrl_cp in data.get("checkpoints", []):
            cc = ctrl_cp.get("control_code", "")
            for item in ctrl_cp.get("items", []):
                req = item.get("requirement", "")
                if not req:
                    continue
                pending_rows.append({
                    "id": str(uuid.uuid4()),
                    "fw": framework_id,
                    "cc": cc,
                    "idx": item.get("index", 1),
                    "req": req,
                    "kw": json.dumps(item.get("keywords", [])),
                })
        print(f"    [fw-checkpoints] batch {i // 10 + 1}/"
              f"{(len(controls) + 9) // 10}: buffered "
              f"(pending_rows={len(pending_rows)})")

    return pending_rows, failed_batches


# Reused INSERT statement for control_checkpoints (single source of truth so
# the bulk and repair paths cannot drift apart on column ordering / weights).
_INSERT_CHECKPOINT_SQL = """
    INSERT INTO control_checkpoints
    (id, framework, control_code, checkpoint_index,
     requirement, keywords, weight)
    VALUES (:id, :fw, :cc, :idx, :req, :kw, 1.0)
"""


async def generate_checkpoints_for_framework(
    db, framework_name, framework_id, full_text, force=False, control_window_map=None
):
    """Use GPT to generate YES/NO checkpoints for each control.

    Atomic execution model (Phase 2): if force=True the DELETE is staged,
    not committed. All generated checkpoint rows are buffered in memory and
    INSERTed only after every batch succeeds. If any batch fails, the
    transaction is rolled back, restoring the prior checkpoint state. This
    eliminates the partial-write hazard where some batches' checkpoints
    persisted while others failed silently.

    control_window_map: dict mapping control_code → the source window text
    that control was extracted from.  When provided, GPT receives the
    actual section of the document the control lives in rather than always
    getting the first 5000 characters of the full text.
    """
    if force:
        # Stage delete inside the same transaction as the inserts. NO commit
        # here — function-level commit at the end commits DELETE + inserts
        # atomically. On any batch failure we db.rollback() and the prior
        # checkpoints are preserved.
        deleted = db.execute(text(
            "DELETE FROM control_checkpoints WHERE framework = :fwid"
        ), {"fwid": framework_id}).rowcount
        print(f"  [fw-checkpoints] force=True: staged delete of {deleted} "
              f"existing checkpoints (will commit on success)")
    else:
        existing = db.execute(text(
            "SELECT COUNT(*) FROM control_checkpoints WHERE framework = :fwid"
        ), {"fwid": framework_id}).fetchone()[0]
        if existing > 0:
            print(f"    {existing} checkpoints already exist for {framework_name}, skipping")
            return {"total_checkpoints": existing, "failed_batches": []}

    controls = db.execute(text(
        "SELECT id, control_code, title, keywords "
        "FROM control_library WHERE framework_id = :fid"
    ), {"fid": framework_id}).fetchall()

    if not controls:
        print(f"    No controls found for {framework_name}")
        return {"total_checkpoints": 0, "failed_batches": []}

    pending_rows, failed_batches = await _run_checkpoint_batch_loop(
        framework_name, framework_id, controls, full_text, control_window_map
    )

    if failed_batches:
        # Atomic execution: any batch failure → rollback the staged DELETE and
        # discard all buffered rows. Old checkpoints (if any) are preserved.
        db.rollback()
        print(f"    [fw-checkpoints] ABORT: {len(failed_batches)} batch(es) failed; "
              f"rolled back staged DELETE and discarded {len(pending_rows)} "
              f"pending checkpoint(s). Prior state preserved.")
        return {"total_checkpoints": 0, "failed_batches": failed_batches}

    # All batches succeeded. INSERT every buffered row, then commit the
    # DELETE+INSERTs together.
    for params in pending_rows:
        db.execute(text(_INSERT_CHECKPOINT_SQL), params)
    db.commit()
    total_checkpoints = len(pending_rows)
    print(f"    Generated {total_checkpoints} checkpoints "
          f"for {len(controls)} controls "
          f"(atomic, failed_batches=0)")

    from backend.checkpoint_seed import ensure_control_library_sync
    ensure_control_library_sync(db)

    return {"total_checkpoints": total_checkpoints,
            "failed_batches": failed_batches}


async def generate_missing_checkpoints_for_framework(db, framework_name, framework_id):
    """Phase-4 repair: generate checkpoints ONLY for controls that currently
    have ZERO checkpoints. Existing controls and existing checkpoints are
    untouched. No DELETE.

    Atomic per-run: if any batch fails, db.rollback() is called and no new
    checkpoints are persisted. The framework remains in its prior state and
    the caller can retry.

    Source context is reassembled from framework_chunks (ordered by
    chunk_index) — the same text the original extraction had access to.
    Returns:
        {"total_checkpoints_added": int,
         "controls_repaired": int,
         "controls_missing_before": int,
         "failed_batches": list}
    """
    missing = db.execute(text("""
        SELECT cl.id, cl.control_code, cl.title, cl.keywords
        FROM control_library cl
        WHERE cl.framework_id = :fid
          AND NOT EXISTS (
              SELECT 1 FROM control_checkpoints cc
              WHERE cc.framework = cl.framework_id::text
              AND cc.control_code = cl.control_code
          )
        ORDER BY cl.control_code
    """), {"fid": framework_id}).fetchall()

    if not missing:
        print(f"  [fw-repair] {framework_name}: no missing checkpoints; nothing to do")
        return {"total_checkpoints_added": 0,
                "controls_repaired": 0,
                "controls_missing_before": 0,
                "failed_batches": []}

    print(f"  [fw-repair] {framework_name}: "
          f"{len(missing)} control(s) without checkpoints")

    # Reassemble framework source text from the persisted chunks.
    chunks = db.execute(text(
        "SELECT chunk_text FROM framework_chunks "
        "WHERE framework_id = :fid ORDER BY chunk_index"
    ), {"fid": framework_id}).fetchall()
    full_text = "\n\n".join(c[0] for c in chunks if c[0])
    print(f"  [fw-repair] {framework_name}: "
          f"{len(chunks)} chunk(s), {len(full_text)} chars of context")

    pending_rows, failed_batches = await _run_checkpoint_batch_loop(
        framework_name, framework_id, missing, full_text, None
    )

    if failed_batches:
        # No DELETE was staged in this path — rollback discards any uncommitted
        # state from helper-side reads/writes and keeps existing data intact.
        db.rollback()
        print(f"  [fw-repair] ABORT: {len(failed_batches)} batch(es) failed; "
              f"discarded {len(pending_rows)} pending checkpoint(s). "
              f"No changes to {framework_name}.")
        return {"total_checkpoints_added": 0,
                "controls_repaired": 0,
                "controls_missing_before": len(missing),
                "failed_batches": failed_batches}

    for params in pending_rows:
        db.execute(text(_INSERT_CHECKPOINT_SQL), params)
    db.commit()

    # Distinct control_codes that received at least one new checkpoint.
    repaired = len({p["cc"] for p in pending_rows if p["cc"]})

    print(f"  [fw-repair] {framework_name}: "
          f"added {len(pending_rows)} checkpoint(s) across "
          f"{repaired}/{len(missing)} control(s)")

    return {"total_checkpoints_added": len(pending_rows),
            "controls_repaired": repaired,
            "controls_missing_before": len(missing),
            "failed_batches": []}


# ── Vector search for framework context ──────────────────────────────────────

def get_framework_context(db, framework_name, query_embedding, top_k=5):
    emb_str = json.dumps(query_embedding)
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
