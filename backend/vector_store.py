from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

import httpx
import numpy as np
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from .ai_config import HF_API_TOKEN, MODELS, TOP_K_RETRIEVAL

logger = logging.getLogger(__name__)

# BGE recommends this prefix on query strings (NOT on document chunks).
# It improves retrieval quality for asymmetric search (query vs passage).
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_pgvector(embedding: List[float]) -> str:
    """Format a float list as the pgvector literal '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"


def _pool_single(raw) -> List[float]:
    """
    Normalize one text's HF feature-extraction output to a flat 1-D vector.

    HF Inference API can return any of these shapes for a single text:
        - List[float]              — already a flat sentence embedding
        - List[List[float]]        — (seq_len, hidden); mean-pool over tokens
    Both are handled correctly here.
    """
    arr = np.array(raw, dtype=np.float32)
    if arr.ndim == 1:
        return arr.tolist()
    # ndim == 2: (seq_len, hidden_dim) — mean-pool to get sentence vector
    return arr.mean(axis=0).tolist()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_embeddings(
    texts: List[str],
    is_query: bool = False,
) -> List[List[float]]:
    """
    Embed a batch of texts using BGE-base-en-v1.5 via HuggingFace Inference API.

    Args:
        texts:    Strings to embed.
        is_query: True when embedding a search query (adds BGE instruction
                  prefix). False for document chunks being indexed.

    Returns:
        List of 768-dim float vectors, one per input text.

    Raises:
        httpx.HTTPStatusError: on non-2xx response from the HF API.
    """
    if not texts:
        return []

    inputs = (
        [_QUERY_PREFIX + t for t in texts] if is_query else list(texts)
    )

    raw: list = []
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    MODELS["embeddings"]["endpoint"],
                    headers={"Authorization": f"Bearer {HF_API_TOKEN}"},
                    json={"inputs": inputs, "options": {"wait_for_model": True}},
                )
                if response.status_code == 503:
                    if attempt == 0:
                        logger.warning("Embedding model returned 503 — waiting 10s before retry")
                        await asyncio.sleep(10)
                        continue
                    raise HTTPException(
                        status_code=502,
                        detail="Embedding service unavailable after retry (503)",
                    )
                response.raise_for_status()
                raw = response.json()
                break
        except HTTPException:
            raise
        except httpx.HTTPStatusError as exc:
            logger.error("HuggingFace embedding API error: %s", exc)
            raise HTTPException(
                status_code=502,
                detail=f"Embedding model unavailable: {exc.response.status_code}",
            ) from exc
        except httpx.RequestError as exc:
            logger.error("HuggingFace embedding API request failed: %s", exc)
            raise HTTPException(
                status_code=502,
                detail="Could not reach the embedding model. Check your network or HF token.",
            ) from exc

    # raw is a list with one entry per input text.
    # Each entry is either List[float] or List[List[float]] depending on
    # whether the model returns CLS/mean-pooled or per-token hidden states.
    return [_pool_single(item) for item in raw]


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
        embeddings: Parallel list of 768-dim vectors from get_embeddings().
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
        query_embedding: 768-dim vector from get_embeddings(is_query=True).
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
    vec_str = _to_pgvector(query_embedding)
    params: dict = {"top_k": top_k, "query_embedding": vec_str}

    filter_clause = ""
    if policy_id:
        filter_clause = "WHERE policy_id = :policy_id"
        params["policy_id"] = policy_id

    # Use a CTE so the vector literal is cast once and reused for both the
    # ORDER BY and the SELECT — avoids redundant work and repeated casting.
    rows = db.execute(
        text(f"""
            WITH q AS (
                SELECT :query_embedding::vector AS vec
            )
            SELECT
                chunk_text,
                chunk_index,
                policy_id::text,
                1 - (embedding <=> (SELECT vec FROM q)) AS similarity
            FROM policy_chunks
            {filter_clause}
            ORDER BY embedding <=> (SELECT vec FROM q)
            LIMIT :top_k
        """),
        params,
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
