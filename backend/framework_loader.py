import os
import json
import uuid
import httpx
from datetime import datetime
from sqlalchemy import text

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


async def load_framework_document(db, file_path, framework_name, source_document):
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
    print(f"  Extracting controls from {framework_name}...")
    num_controls = await extract_controls_from_framework(
        db, framework_name, framework_id, content
    )
    result["controls_extracted"] = num_controls

    print(f"  Generating checkpoints for {framework_name}...")
    num_checkpoints = await generate_checkpoints_for_framework(
        db, framework_name, framework_id, content
    )
    result["checkpoints_generated"] = num_checkpoints

    return result


# ── Step 1: Extract controls from framework text via GPT ─────────────────────

async def extract_controls_from_framework(db, framework_name, framework_id, full_text):
    """Use GPT to extract control codes and titles from framework text."""

    # Check if controls already exist for this framework
    existing = db.execute(text(
        "SELECT COUNT(*) FROM control_library WHERE framework_id = :fid"
    ), {"fid": framework_id}).fetchone()[0]

    if existing > 0:
        print(f"    {existing} controls already exist for {framework_name}, skipping extraction")
        return existing

    # Use first ~15000 chars which usually contains the control listing
    sample_text = full_text[:15000]

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
- If you can't find structured controls, extract section headings as controls"""

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
                            f"FRAMEWORK: {framework_name}\n\nTEXT:\n{sample_text}"},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 4000,
                    "response_format": {"type": "json_object"},
                },
            )
            if r.status_code != 200:
                print(f"    GPT error extracting controls: {r.status_code}")
                return 0

            data = json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"    Control extraction error: {e}")
        return 0

    controls = data.get("controls", [])

    for ctrl in controls:
        # Skip if this control_code already exists
        exists = db.execute(text(
            "SELECT id FROM control_library "
            "WHERE control_code = :cc AND framework_id = :fid"
        ), {"cc": ctrl["code"], "fid": framework_id}).fetchone()

        if exists:
            continue

        db.execute(text("""
            INSERT INTO control_library
            (id, control_code, title, keywords,
             severity_if_missing, framework_id, created_at)
            VALUES (:id, :cc, :title, :kw, :sev, :fid, :cat)
        """), {
            "id": str(uuid.uuid4()),
            "cc": ctrl["code"],
            "title": ctrl["title"],
            "kw": json.dumps(ctrl.get("keywords", [])),
            "sev": ctrl.get("severity", "High"),
            "fid": framework_id,
            "cat": datetime.utcnow(),
        })

    db.commit()
    print(f"    Extracted {len(controls)} controls from {framework_name}")
    return len(controls)


# ── Step 2: Generate YES/NO checkpoints for each control via GPT ─────────────

async def generate_checkpoints_for_framework(db, framework_name, framework_id, full_text):
    """Use GPT to generate YES/NO checkpoints for each control."""

    # Check if checkpoints already exist
    existing = db.execute(text(
        "SELECT COUNT(*) FROM control_checkpoints WHERE framework = :fw"
    ), {"fw": framework_name}).fetchone()[0]

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
                    "fw": framework_name,
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
