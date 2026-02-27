from __future__ import annotations

import logging
from typing import List, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from .ai_config import TOP_K_RETRIEVAL

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_pgvector(embedding: List[float]) -> str:
    """Format a float list as the pgvector literal '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_embeddings(texts: list) -> list:
    """
    Embed a batch of texts using OpenAI text-embedding-3-small (1536 dimensions).

    Args:
        texts: Strings to embed.

    Returns:
        List of 1536-dim float vectors, one per input text.

    Raises:
        Exception: on non-200 response from the OpenAI API.
    """
    from .ai_config import OPENAI_API_KEY

    if not texts:
        return []

    all_embeddings = []
    for i in range(0, len(texts), 20):
        batch = texts[i : i + 20]
        # OpenAI rejects empty strings — replace with a placeholder
        batch = [t.strip() if t.strip() else "empty" for t in batch]

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": "text-embedding-3-small", "input": batch},
            )
            if response.status_code != 200:
                raise Exception(
                    f"OpenAI embedding error ({response.status_code}): "
                    f"{response.text[:500]}"
                )
            data = response.json()
            batch_embeddings = [item["embedding"] for item in data["data"]]
            all_embeddings.extend(batch_embeddings)

    return all_embeddings


def store_chunks_with_embeddings(
    db: Session,
    policy_id: str,
    chunks: List[dict],
    embeddings: List[List[float]],
) -> None:
    """
    Persist chunk texts and their vector embeddings to policy_chunks.

    Args:
        db:         SQLAlchemy session (from get_db()).
        policy_id:  UUID string of the owning policy.
        chunks:     Output of chunker.chunk_text().
        embeddings: Parallel list of 1536-dim vectors from get_embeddings().
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) "
            "must have the same length."
        )

    for chunk, embedding in zip(chunks, embeddings):
        db.execute(
            text("""
                INSERT INTO policy_chunks
                    (policy_id, chunk_index, chunk_text,
                     embedding, char_start, char_end)
                VALUES
                    (:policy_id, :chunk_index, :chunk_text,
                     :embedding::vector, :char_start, :char_end)
            """),
            {
                "policy_id": policy_id,
                "chunk_index": chunk["chunk_index"],
                "chunk_text": chunk["text"],
                "embedding": _to_pgvector(embedding),
                "char_start": chunk["char_start"],
                "char_end": chunk["char_end"],
            },
        )

    db.commit()
    logger.info(
        "Stored %d chunks for policy %s", len(chunks), policy_id
    )


def search_similar_chunks(
    db: Session,
    query_embedding: List[float],
    policy_id: Optional[str] = None,
    top_k: int = TOP_K_RETRIEVAL,
) -> List[dict]:
    """
    Retrieve the top-k chunks most similar to a query embedding.

    Uses cosine distance (<=> operator) with the HNSW index for fast ANN search.
    Similarity is returned as a float in [0, 1] where 1.0 = identical.

    Args:
        db:              SQLAlchemy session.
        query_embedding: 1536-dim vector from get_embeddings().
        policy_id:       Optional — restrict search to a single policy document.
        top_k:           Number of results to return.

    Returns:
        List of dicts sorted by descending similarity:
            {
                "text":        str,
                "chunk_index": int,
                "policy_id":   str,
                "similarity":  float,   # cosine similarity in [0, 1]
            }
    """
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    if policy_id:
        rows = db.execute(
            text("""
                SELECT chunk_text, chunk_index, policy_id,
                       1 - (embedding <=> cast(:embedding as vector)) AS similarity
                FROM policy_chunks
                WHERE policy_id = :policy_id
                ORDER BY embedding <=> cast(:embedding as vector)
                LIMIT :top_k
            """),
            {"embedding": embedding_str, "policy_id": policy_id, "top_k": top_k},
        ).fetchall()
    else:
        rows = db.execute(
            text("""
                SELECT chunk_text, chunk_index, policy_id,
                       1 - (embedding <=> cast(:embedding as vector)) AS similarity
                FROM policy_chunks
                ORDER BY embedding <=> cast(:embedding as vector)
                LIMIT :top_k
            """),
            {"embedding": embedding_str, "top_k": top_k},
        ).fetchall()

    return [
        {
            "text": row[0],
            "chunk_index": row[1],
            "policy_id": str(row[2]),
            "similarity": float(row[3]),
        }
        for row in rows
    ]


def delete_policy_chunks(db: Session, policy_id: str) -> int:
    """
    Delete all chunks belonging to a policy.

    The policy_chunks table has ON DELETE CASCADE on policy_id, so chunks
    are removed automatically when the policy row itself is deleted.
    Call this explicitly when re-indexing a policy without deleting it.

    Args:
        db:        SQLAlchemy session.
        policy_id: UUID string of the policy whose chunks to delete.

    Returns:
        Number of rows deleted.
    """
    result = db.execute(
        text("DELETE FROM policy_chunks WHERE policy_id = :pid"),
        {"pid": policy_id},
    )
    db.commit()
    deleted = result.rowcount
    logger.info("Deleted %d chunks for policy %s", deleted, policy_id)
    return deleted
