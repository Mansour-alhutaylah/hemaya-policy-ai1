"""
Framework Knowledge Base Loader
Processes NCA ECC, ISO 27001, and NIST 800-53 reference documents
and stores them as searchable chunks for the RAG pipeline.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from backend.chunker import chunk_text
from backend.vector_store import get_embeddings

FRAMEWORK_MAPPING = {
    "NCA ECC": ["nca", "ecc", "essential cybersecurity controls"],
    "ISO 27001": ["iso", "27001", "information security management"],
    "NIST 800-53": ["nist", "800-53", "security and privacy controls"],
}


def detect_framework(filename: str, content: str) -> str:
    """Auto-detect which framework a document belongs to."""
    filename_lower = filename.lower()
    content_lower = content[:2000].lower()

    for framework, keywords in FRAMEWORK_MAPPING.items():
        for kw in keywords:
            if kw in filename_lower or kw in content_lower:
                return framework
    return "Unknown"


async def load_framework_document(
    db,
    file_path: str,
    framework_name: str,
    source_document: str,
) -> dict:
    """
    Process a framework reference document:
    1. Extract text
    2. Chunk the text (larger chunks for richer framework context)
    3. Embed each chunk
    4. Store in framework_chunks table
    """
    from backend.text_extractor import extract_text

    ext = Path(file_path).suffix.lower()
    content = extract_text(file_path, ext)

    if not content or content.startswith("[Extraction error"):
        return {"error": content or "Empty document"}

    # Larger chunks for framework docs (600 chars) so each chunk has rich context
    chunks = chunk_text(content, chunk_size=600, overlap=150)
    if not chunks:
        return {"error": "No chunks created from document"}

    chunk_texts = [c["text"] for c in chunks]

    # Process in batches of 20 (HuggingFace input limits)
    all_embeddings: list = []
    for i in range(0, len(chunk_texts), 20):
        batch = chunk_texts[i : i + 20]
        batch_embeddings = await get_embeddings(batch)
        all_embeddings.extend(batch_embeddings)

    # Store in framework_chunks table
    for chunk, embedding in zip(chunks, all_embeddings):
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        db.execute(
            text("""
                INSERT INTO framework_chunks
                (id, framework_name, chunk_text, embedding, chunk_index,
                 source_document, created_at)
                VALUES (:id, :framework, :chunk_text, :embedding, :chunk_index,
                        :source_doc, :created_at)
            """),
            {
                "id": str(uuid.uuid4()),
                "framework": framework_name,
                "chunk_text": chunk["text"],
                "embedding": embedding_str,
                "chunk_index": chunk["chunk_index"],
                "source_doc": source_document,
                "created_at": datetime.utcnow(),
            },
        )

    db.commit()

    return {
        "framework": framework_name,
        "chunks_created": len(chunks),
        "source": source_document,
        "status": "loaded",
    }


def get_framework_context(
    db,
    framework_name: str,
    query_embedding: list,
    top_k: int = 5,
) -> list:
    """
    Search framework_chunks for relevant reference text.
    Used during analysis to compare org policy against framework requirements.

    Returns list of dicts: text, control_code, section_title, similarity
    """
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    try:
        results = db.execute(
            text("""
                SELECT chunk_text, control_code, section_title,
                       1 - (embedding <=> cast(:embedding as vector)) AS similarity
                FROM framework_chunks
                WHERE framework_name = :framework
                ORDER BY embedding <=> cast(:embedding as vector)
                LIMIT :top_k
            """),
            {
                "embedding": embedding_str,
                "framework": framework_name,
                "top_k": top_k,
            },
        ).fetchall()
    except Exception:
        # Table may not exist yet — return empty list gracefully
        return []

    return [
        {
            "text": r[0],
            "control_code": r[1],
            "section_title": r[2],
            "similarity": float(r[3]) if r[3] is not None else 0.0,
        }
        for r in results
    ]


def get_framework_stats(db) -> dict:
    """Get stats about loaded framework documents."""
    try:
        results = db.execute(
            text("""
                SELECT framework_name, COUNT(*) AS chunk_count,
                       COUNT(DISTINCT source_document) AS doc_count
                FROM framework_chunks
                GROUP BY framework_name
            """)
        ).fetchall()
    except Exception:
        return {}

    return {r[0]: {"chunks": int(r[1]), "documents": int(r[2])} for r in results}
