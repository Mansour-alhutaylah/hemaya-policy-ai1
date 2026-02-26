from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional

import httpx
from sqlalchemy.orm import Session

from .ai_config import HF_API_TOKEN, MODELS, TOP_K_RERANK, TOP_K_RETRIEVAL
from .vector_store import get_embeddings, search_similar_chunks

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Internal helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _extract_rerank_score(score_data) -> float:
    """
    Extract a single relevance float from one HF text-classification response entry.

    HF Inference API may return per-pair results in any of these shapes:
        float / int
            — raw relevance score directly
        {"label": str, "score": float}
            — single-label dict
        [{"label": "LABEL_0", "score": float}, {"label": "LABEL_1", "score": float}]
            — binary classifier output; LABEL_1 is the positive (relevant) class
    """
    if isinstance(score_data, (int, float)):
        return float(score_data)

    if isinstance(score_data, dict):
        return float(score_data.get("score", 0.0))

    if isinstance(score_data, list) and score_data:
        # Prefer LABEL_1 — the positive/relevant class for binary rerankers
        for entry in score_data:
            if isinstance(entry, dict) and entry.get("label", "").upper() == "LABEL_1":
                return float(entry["score"])
        # Fallback: highest score across all labels
        scores = [entry.get("score", 0.0) for entry in score_data if isinstance(entry, dict)]
        return float(max(scores)) if scores else 0.0

    return 0.0


def _parse_llm_json(llm_response: str) -> dict:
    """
    Extract and parse the first JSON object found in an LLM response string.
    Returns a fallback dict if no valid JSON is present.
    """
    try:
        start = llm_response.find("{")
        end = llm_response.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(llm_response[start:end])
    except (json.JSONDecodeError, ValueError):
        pass

    return {
        "status": "Non-Compliant",
        "confidence": 0.3,
        "evidence": "",
        "rationale": llm_response.strip() or "No response from model.",
        "recommendation": "Manual review required — AI could not parse a structured result.",
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RERANKER — picks the best chunks from initial retrieval
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def rerank_chunks(
    query: str,
    chunks: List[dict],
    top_k: int = TOP_K_RERANK,
) -> List[dict]:
    """
    Use BGE-reranker-v2-m3 to rerank retrieved chunks by relevance to query.

    Args:
        query:  The search query or control description string.
        chunks: Candidate chunks from search_similar_chunks().
        top_k:  Number of top-ranked chunks to return.

    Returns:
        Subset of chunks sorted by descending rerank_score, length <= top_k.
    """
    if not chunks:
        return []

    # Reranker expects [query, document] pairs
    pairs = [[query, chunk["text"]] for chunk in chunks]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                MODELS["reranker"]["endpoint"],
                headers={"Authorization": f"Bearer {HF_API_TOKEN}"},
                json={"inputs": pairs, "options": {"wait_for_model": True}},
            )
            if response.status_code == 503:
                logger.warning("Reranker returned 503 — returning top-%d chunks without reranking", top_k)
                return chunks[:top_k]
            response.raise_for_status()
            raw_scores: list = response.json()
    except Exception as exc:
        logger.warning("Reranker failed (%s) — returning top-%d chunks without reranking", exc, top_k)
        return chunks[:top_k]

    # Attach relevance scores without mutating the caller's dicts
    scored = []
    for chunk, score_data in zip(chunks, raw_scores):
        enriched = dict(chunk)
        enriched["rerank_score"] = _extract_rerank_score(score_data)
        scored.append(enriched)

    scored.sort(key=lambda c: c["rerank_score"], reverse=True)
    return scored[:top_k]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LLM — Qwen2.5-3B-Instruct compliance judgment
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def call_llm(prompt: str) -> str:
    """
    Send a prompt to Qwen2.5-7B-Instruct via the HuggingFace Inference API.

    Returns:
        The generated text string (prompt excluded via return_full_text=False).

    Raises:
        httpx.HTTPStatusError: on non-2xx API response.
    """
    _fallback = '{"status": "Non-Compliant", "confidence": 0.0, "evidence": "", "rationale": "AI service unavailable — retry later.", "recommendation": "Re-run analysis when the AI service is available."}'

    for attempt in range(2):
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                MODELS["llm"]["endpoint"],
                headers={"Authorization": f"Bearer {HF_API_TOKEN}"},
                json={
                    "inputs": prompt,
                    "parameters": {
                        "max_new_tokens": MODELS["llm"]["max_new_tokens"],
                        "temperature": MODELS["llm"]["temperature"],
                        "return_full_text": False,
                    },
                    "options": {"wait_for_model": True},
                },
            )
            if response.status_code == 503:
                if attempt == 0:
                    logger.warning("LLM returned 503 — waiting 10s before retry")
                    await asyncio.sleep(10)
                    continue
                logger.error("LLM still unavailable after retry — returning fallback")
                return _fallback
            response.raise_for_status()
            result = response.json()
            break
    else:
        return _fallback

    # HF text-generation: [{"generated_text": "..."}]
    if isinstance(result, list) and result:
        return result[0].get("generated_text", "")
    return str(result)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN PIPELINE: per-control analysis
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def analyze_control_compliance(
    db: Session,
    policy_id: str,
    control: dict,
) -> dict:
    """
    Run the full Retrieve → Rerank → Generate pipeline for one control.

    Args:
        db:         SQLAlchemy session.
        policy_id:  UUID string of the policy to search within.
        control:    Dict with keys: control_code, title, keywords,
                    framework, severity_if_missing.

    Returns:
        Dict with keys: status, confidence, evidence, rationale,
        recommendation, control_code, framework, retrieved_chunks,
        reranked_chunks.
    """
    # Build a rich query from available fields (ControlLibrary has no description)
    keywords_str = " ".join(control.get("keywords") or [])
    control_query = (
        f"{control['control_code']}: {control['title']}. {keywords_str}".strip()
    )

    # ── STEP 1: embed the query and retrieve top-K chunks ──────────────────
    query_embedding = (await get_embeddings([control_query], is_query=True))[0]
    retrieved = search_similar_chunks(
        db,
        query_embedding,
        policy_id=policy_id,
        top_k=TOP_K_RETRIEVAL,
    )

    # ── STEP 2: rerank to keep the most relevant evidence ──────────────────
    best_chunks = await rerank_chunks(control_query, retrieved, top_k=TOP_K_RERANK)

    if not best_chunks:
        # Policy has no indexed chunks yet — return a safe default
        logger.warning(
            "No chunks found for policy %s — was it indexed?", policy_id
        )
        return {
            "status": "Non-Compliant",
            "confidence": 0.0,
            "evidence": "",
            "rationale": "No indexed policy text found. Upload and index the policy first.",
            "recommendation": "Re-upload and index the policy document.",
            "control_code": control["control_code"],
            "framework": control.get("framework", ""),
            "retrieved_chunks": 0,
            "reranked_chunks": 0,
        }

    # ── STEP 3: build the compliance judgment prompt ────────────────────────
    evidence_text = "\n---\n".join(c["text"] for c in best_chunks)

    prompt = (
        "<|im_start|>system\n"
        "You are a cybersecurity compliance auditor for Saudi Arabian organizations.\n"
        "Analyze whether the given policy text satisfies the specified security control.\n\n"
        "Respond in this EXACT JSON format (no extra text before or after):\n"
        "{\n"
        '  "status": "Compliant" | "Partial" | "Non-Compliant",\n'
        '  "confidence": 0.0 to 1.0,\n'
        '  "evidence": "Quote the specific text that supports your judgment",\n'
        '  "rationale": "Explain WHY this control is or is not covered",\n'
        '  "recommendation": "If not fully compliant, what should be added"\n'
        "}\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"CONTROL: {control['control_code']} - {control['title']}\n"
        f"KEYWORDS: {keywords_str}\n\n"
        "POLICY TEXT (relevant excerpts):\n"
        f"{evidence_text}\n\n"
        "Judge whether this policy text satisfies the control requirement.\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )

    # ── STEP 4: get the LLM judgment ───────────────────────────────────────
    llm_response = await call_llm(prompt)

    # ── STEP 5: parse the structured JSON from the response ────────────────
    result = _parse_llm_json(llm_response)

    # Enforce valid status values in case the model drifts
    if result.get("status") not in {"Compliant", "Partial", "Non-Compliant"}:
        result["status"] = "Non-Compliant"

    result["control_code"] = control["control_code"]
    result["framework"] = control.get("framework", "")
    result["retrieved_chunks"] = len(retrieved)
    result["reranked_chunks"] = len(best_chunks)

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FULL ANALYSIS: all controls across all frameworks
# Called by POST /api/functions/analyze_policy
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_full_analysis(
    db: Session,
    policy_id: str,
    frameworks: List[str],
) -> dict:
    """
    Run compliance analysis for every control in every requested framework.

    Replaces the keyword-matching logic in analyze_policy with full RAG.

    Args:
        db:         SQLAlchemy session.
        policy_id:  UUID string of the policy being analyzed.
        frameworks: List of framework names (e.g. ["NCA ECC", "ISO 27001"]).

    Returns:
        {
            "NCA ECC": {
                "score":          72.5,
                "total_controls": 20,
                "compliant":      10,
                "partial":        5,
                "non_compliant":  5,
                "details": [
                    {
                        "control_code":     "ECC-1-1",
                        "framework":        "NCA ECC",
                        "status":           "Compliant",
                        "confidence":       0.91,
                        "evidence":         "...",
                        "rationale":        "...",
                        "recommendation":   "",
                        "retrieved_chunks": 10,
                        "reranked_chunks":  3,
                        "severity_if_missing": "High",
                    },
                    ...
                ],
            },
            ...
        }
    """
    from .models import ControlLibrary  # local import avoids circular deps at module load

    results_by_framework: dict = {}

    for framework in frameworks:
        controls = (
            db.query(ControlLibrary)
            .filter(ControlLibrary.framework == framework)
            .all()
        )

        if not controls:
            logger.warning("No controls found for framework '%s'", framework)
            results_by_framework[framework] = {
                "score": 0.0,
                "total_controls": 0,
                "compliant": 0,
                "partial": 0,
                "non_compliant": 0,
                "details": [],
            }
            continue

        framework_results: list[dict] = []
        for control in controls:
            control_dict = {
                "control_code": control.control_code,
                "title": control.title,
                "keywords": control.keywords or [],
                "framework": framework,
                "severity_if_missing": control.severity_if_missing or "Medium",
            }
            result = await analyze_control_compliance(db, policy_id, control_dict)
            # Carry severity through so main.py can use it when creating Gap rows
            result["severity_if_missing"] = control_dict["severity_if_missing"]
            framework_results.append(result)

        total = len(framework_results)
        compliant = sum(1 for r in framework_results if r["status"] == "Compliant")
        partial = sum(1 for r in framework_results if r["status"] == "Partial")
        non_compliant = sum(1 for r in framework_results if r["status"] == "Non-Compliant")
        score = ((compliant + partial * 0.5) / total * 100) if total > 0 else 0.0

        results_by_framework[framework] = {
            "score": round(score, 1),
            "total_controls": total,
            "compliant": compliant,
            "partial": partial,
            "non_compliant": non_compliant,
            "details": framework_results,
        }

        logger.info(
            "Framework %s: %.1f%% (%d/%d compliant)",
            framework, score, compliant, total,
        )

    return results_by_framework


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHAT: RAG-powered policy assistant
# Called by POST /api/functions/chat_assistant
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def chat_with_context(
    db: Session,
    message: str,
    policy_id: Optional[str] = None,
) -> str:
    """
    Answer a user question using evidence retrieved from indexed policy documents.

    Replaces the keyword-matching chat_assistant logic with full RAG.

    Args:
        db:        SQLAlchemy session.
        message:   The user's question (Arabic or English).
        policy_id: Optional — restrict context to a single policy.
                   If None, searches across all indexed policies.

    Returns:
        The model's answer as a plain string.
    """
    query_embedding = (await get_embeddings([message], is_query=True))[0]
    retrieved = search_similar_chunks(
        db, query_embedding, policy_id=policy_id, top_k=10
    )
    best_chunks = await rerank_chunks(message, retrieved, top_k=5)

    context = (
        "\n---\n".join(c["text"] for c in best_chunks)
        if best_chunks
        else "No relevant policy text found in the knowledge base."
    )

    prompt = (
        "<|im_start|>system\n"
        "You are Hemaya AI, a cybersecurity compliance assistant specializing in "
        "NCA ECC, ISO 27001, and NIST 800-53 frameworks for Saudi Arabian organizations.\n"
        "Answer questions based on the organization's actual policy documents provided below.\n"
        "If the context does not contain enough information, say so clearly rather than guessing.\n"
        "Respond in the same language the user writes in (Arabic or English).\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        "Context from organization's policies:\n"
        f"{context}\n\n"
        f"Question: {message}\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )

    return await call_llm(prompt)
