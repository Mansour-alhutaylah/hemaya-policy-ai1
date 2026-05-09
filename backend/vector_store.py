import os
import json
import uuid
import httpx
from datetime import datetime
from sqlalchemy import text

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Persistent client — one TLS session reused across all embedding calls.
# Eliminates 100-250 ms TLS handshake overhead per request.
_openai_client = httpx.AsyncClient(
    timeout=60.0,
    limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
)


async def get_embeddings(texts: list) -> list:
    if not texts:
        return []

    # Clean empty strings
    cleaned = [t.strip() if t and t.strip() else "empty" for t in texts]
    all_embs = []

    # Batch 50 at a time for speed
    for i in range(0, len(cleaned), 50):
        batch = cleaned[i:i+50]
        resp = await _openai_client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": "text-embedding-3-small", "input": batch},
        )
        if resp.status_code != 200:
            raise Exception(f"Embedding error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        all_embs.extend([d["embedding"] for d in data["data"]])

    return all_embs


def store_chunks_with_embeddings(db, policy_id, chunks, embeddings):
    from backend.structured_extractor import classify_sentence

    for chunk, emb in zip(chunks, embeddings):
        if emb is None:
            continue
        emb_str = json.dumps(emb)  # ~6x faster than ",".join(str(x) for x in emb)
        classification = classify_sentence(chunk["text"])
        # Phase 11: write source attribution columns when the chunk dict
        # carries them. Pre-Phase-11 chunk dicts (no page_number /
        # paragraph_index keys) -> NULL, matching the column default.
        db.execute(text("""
            INSERT INTO policy_chunks
            (id, policy_id, chunk_index, chunk_text, embedding,
             char_start, char_end, classification,
             page_number, paragraph_index, created_at)
            VALUES (:id, :pid, :idx, :txt, cast(:emb as vector),
                    :cs, :ce, :cls,
                    :pgnum, :paridx, :cat)
        """), {
            "id": str(uuid.uuid4()), "pid": policy_id,
            "idx": chunk.get("chunk_index", 0), "txt": chunk["text"],
            "emb": emb_str, "cs": chunk.get("char_start", 0),
            "ce": chunk.get("char_end", 0), "cls": classification,
            "pgnum":  chunk.get("page_number"),
            "paridx": chunk.get("paragraph_index"),
            "cat": datetime.utcnow(),
        })
    db.commit()
    print(f"Stored {len(chunks)} chunks for policy {policy_id}")


def search_similar_chunks(db, query_embedding, policy_id=None, top_k=10):
    emb_str = json.dumps(query_embedding)

    sql = """
        SELECT chunk_text, chunk_index, policy_id,
               1 - (embedding <=> cast(:emb as vector)) AS similarity
        FROM policy_chunks
        WHERE embedding IS NOT NULL
    """
    params = {"emb": emb_str, "top_k": top_k}

    if policy_id:
        sql += " AND policy_id = :pid"
        params["pid"] = policy_id

    sql += " ORDER BY embedding <=> cast(:emb as vector) LIMIT :top_k"

    results = db.execute(text(sql), params).fetchall()
    return [{"text": r[0], "chunk_index": r[1],
             "policy_id": r[2], "similarity": float(r[3])} for r in results]


def delete_policy_chunks(db, policy_id):
    db.execute(text("DELETE FROM policy_chunks WHERE policy_id = :pid"),
               {"pid": policy_id})
    db.commit()
