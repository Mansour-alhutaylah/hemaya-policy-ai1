import os
import uuid
from datetime import datetime
from sqlalchemy import text


async def load_framework_document(db, file_path, framework_name, source_document):
    from backend.text_extractor import extract_text
    from backend.chunker import chunk_text
    from backend.vector_store import get_embeddings

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
    db.execute(text("DELETE FROM framework_chunks WHERE framework_name = :fw"),
               {"fw": framework_name})
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
            (id, framework_name, chunk_text, embedding, chunk_index, source_document, created_at)
            VALUES (:id, :fw, :txt, cast(:emb as vector), :idx, :doc, :cat)
        """), {
            "id": str(uuid.uuid4()), "fw": framework_name,
            "txt": chunk["text"], "emb": emb_str,
            "idx": chunk.get("chunk_index", 0),
            "doc": source_document, "cat": datetime.utcnow(),
        })
        stored += 1
    db.commit()
    print(f"Framework {framework_name}: {stored} chunks stored")
    return {"framework": framework_name, "chunks_created": stored,
            "source": source_document, "status": "loaded"}


def get_framework_context(db, framework_name, query_embedding, top_k=5):
    emb_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    try:
        results = db.execute(text("""
            SELECT chunk_text, control_code, section_title,
                   1 - (embedding <=> cast(:emb as vector)) AS similarity
            FROM framework_chunks
            WHERE framework_name = :fw AND embedding IS NOT NULL
            ORDER BY embedding <=> cast(:emb as vector)
            LIMIT :top_k
        """), {"emb": emb_str, "fw": framework_name, "top_k": top_k}).fetchall()
    except Exception:
        return []
    return [{"text": r[0], "control_code": r[1],
             "section_title": r[2], "similarity": float(r[3])} for r in results]


def get_framework_stats(db):
    results = db.execute(text("""
        SELECT framework_name, COUNT(*) as chunks,
               COUNT(DISTINCT source_document) as docs
        FROM framework_chunks GROUP BY framework_name
    """)).fetchall()
    return {r[0]: {"chunks": r[1], "documents": r[2]} for r in results}
