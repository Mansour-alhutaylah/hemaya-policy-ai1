from __future__ import annotations

from typing import List

from .ai_config import CHUNK_OVERLAP, CHUNK_SIZE


def _find_split_point(text: str, start: int, end: int, min_advance: int) -> int:
    """
    Return the best index to split at within text[start:end].

    Priority (highest to lowest):
        1. Paragraph boundary  ("\n\n")
        2. Line boundary       ("\n")
        3. Sentence boundary   (". ")
        4. Word boundary       (" ")
        5. Hard cut at `end`   (last resort — walks forward to next whitespace
                                so we avoid splitting mid-word where possible)

    The returned index is always > min_advance so the caller always advances.
    """
    window = text[start:end]

    for sep in ("\n\n", "\n", ". ", " "):
        pos = window.rfind(sep)
        if pos == -1:
            continue
        split_at = start + pos + len(sep)
        if split_at > min_advance:
            return split_at

    # Hard fallback: scan forward from `end` for the next whitespace so we
    # never split inside a word (handles URLs, long Arabic tokens, etc.).
    for i in range(end, min(end + 50, len(text))):
        if text[i] in " \n\t":
            return i + 1

    return end  # absolute last resort (unavoidable mid-word split)


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[dict]:
    """
    Split *text* into overlapping chunks of ~chunk_size characters.

    Splits preferentially at paragraph → sentence → word boundaries.
    Text content is never modified (no lowercasing, no stripping).

    Returns:
        [
            {
                "chunk_index": 0,
                "text":        "The information security policy...",
                "char_start":  0,
                "char_end":    498,
            },
            ...
        ]
    """
    if not text or not text.strip():
        return []

    # Edge case: whole document fits in a single chunk
    if len(text) <= chunk_size:
        return [
            {
                "chunk_index": 0,
                "text": text,
                "char_start": 0,
                "char_end": len(text),
            }
        ]

    raw: list[dict] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            # Remaining text fits in one final chunk
            tail = text[start:]
            if tail.strip():
                raw.append(
                    {"text": tail, "char_start": start, "char_end": len(text)}
                )
            break

        # The split point must be strictly past (start + overlap) so the
        # next window's start (= split_point - overlap) is always > start.
        min_advance = start + overlap + 1
        split_point = _find_split_point(text, start, end, min_advance)

        chunk = text[start:split_point]
        if chunk.strip():
            raw.append(
                {"text": chunk, "char_start": start, "char_end": split_point}
            )

        next_start = split_point - overlap
        # Safety guard: always move forward even if overlap is large
        if next_start <= start:
            next_start = split_point
        start = next_start

    # Assign final sequential indices (some raw entries may have been skipped
    # if they were whitespace-only, so we number them here rather than in-loop)
    return [{"chunk_index": i, **c} for i, c in enumerate(raw)]


def prepare_chunks_for_storage(policy_id: str, chunks: List[dict]) -> List[dict]:
    """
    Enrich chunk dicts with identifiers needed for database insertion.

    Adds to each chunk (without mutating the originals):
        - "policy_id": the owning policy's ID
        - "chunk_id":  "<policy_id>_chunk_<chunk_index>"

    Args:
        policy_id: Unique identifier of the policy document.
        chunks:    Output of chunk_text().

    Returns:
        List of enriched chunk dicts ready for DB insertion.
    """
    result = []
    for chunk in chunks:
        enriched = dict(chunk)  # shallow copy — do not mutate caller's data
        enriched["policy_id"] = policy_id
        enriched["chunk_id"] = f"{policy_id}_chunk_{chunk['chunk_index']}"
        result.append(enriched)
    return result
