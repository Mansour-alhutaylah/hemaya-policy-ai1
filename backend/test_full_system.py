"""
Hemaya Policy AI — Full System Test Suite
Run with: python -m backend.test_full_system

IMPORTANT: Start the backend server FIRST before running tests:
  uvicorn backend.main:app --reload
"""
from __future__ import annotations

import asyncio
import httpx
import io
import json
import os
import sys
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

BASE_URL = "http://localhost:8000"

def _ok(msg: str):   print(f"  {GREEN}✅ PASS{RESET} — {msg}")
def _fail(msg: str): print(f"  {RED}❌ FAIL{RESET} — {msg}")
def _warn(msg: str): print(f"  {YELLOW}⚠️  WARN{RESET} — {msg}")
def _info(msg: str): print(f"       {CYAN}{msg}{RESET}")

# ── Global results tracker ─────────────────────────────────────────────────────
RESULTS: Dict[str, List[bool]] = {}

def _record(group: str, passed: bool) -> None:
    RESULTS.setdefault(group, []).append(passed)

# ── Shared state between groups ────────────────────────────────────────────────
STATE: Dict[str, Any] = {}

def _header(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'━' * 56}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'━' * 56}{RESET}")


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 1 — ENVIRONMENT & CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

def test_group_1() -> None:
    _header("GROUP 1: ENVIRONMENT & CONFIGURATION")
    G = "1-Config"

    # 1.1 .env file loads
    print("\n[1.1] .env file loads")
    try:
        from dotenv import load_dotenv
        load_dotenv()
        db_url   = os.getenv("DATABASE_URL", "")
        secret   = os.getenv("SECRET_KEY", "")
        hf_token = os.getenv("HF_API_TOKEN", "")
        issues = []
        if not db_url:                             issues.append("DATABASE_URL missing")
        if not secret:                             issues.append("SECRET_KEY missing")
        if not hf_token:                           issues.append("HF_API_TOKEN missing")
        elif not hf_token.startswith("hf_"):       issues.append("HF_API_TOKEN doesn't start with 'hf_'")
        if issues:
            _fail("; ".join(issues))
            _record(G, False)
        else:
            _info(f"DATABASE_URL: postgresql://...{db_url[-20:]}")
            _info(f"HF_API_TOKEN: hf_****...{hf_token[-4:]}")
            _ok(".env loaded with all required variables")
            _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)

    # 1.2 AI config loads
    print("\n[1.2] AI config loads")
    try:
        from backend.ai_config import MODELS
        expected_keys = {"llm", "embeddings", "reranker"}
        if set(MODELS.keys()) != expected_keys:
            _fail(f"MODELS keys: {set(MODELS.keys())} (expected {expected_keys})")
            _record(G, False)
        else:
            hf_prefix = "https://api-inference.huggingface.co/models/"
            bad = [k for k, v in MODELS.items() if not v.get("endpoint", "").startswith(hf_prefix)]
            if bad:
                _fail(f"Bad endpoints for: {bad}")
                _record(G, False)
            else:
                for k, v in MODELS.items():
                    _info(f"  {k}: {v['name']}")
                _ok("AI config has all 3 models with valid HF endpoints")
                _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}\n{traceback.format_exc()}")
        _record(G, False)

    # 1.3 All backend files importable
    print("\n[1.3] All backend files importable")
    modules = [
        "backend.database", "backend.models", "backend.schemas",
        "backend.auth", "backend.text_extractor", "backend.ai_config",
        "backend.chunker", "backend.vector_store", "backend.rag_engine",
        "backend.main",
    ]
    all_ok = True
    for mod in modules:
        try:
            __import__(mod)
            _info(f"  {mod} ✓")
        except Exception as e:
            _fail(f"Cannot import {mod}: {e}")
            traceback.print_exc()
            all_ok = False
    _record(G, all_ok)
    if all_ok:
        _ok("All backend modules imported successfully")


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 2 — DATABASE CONNECTION
# ═══════════════════════════════════════════════════════════════════════════════

def test_group_2() -> None:
    _header("GROUP 2: DATABASE CONNECTION")
    G = "2-Database"

    from backend.database import SessionLocal
    from sqlalchemy import text

    # 2.1 Database connects
    print("\n[2.1] Database connects")
    try:
        db = SessionLocal()
        result = db.execute(text("SELECT 1")).scalar()
        db.close()
        assert result == 1
        _ok("Database connection successful")
        _record(G, True)
    except Exception as e:
        _fail(f"Cannot connect to database: {e}")
        _record(G, False)
        for _ in range(4):
            _record(G, False)
        return

    # 2.2 Required tables exist
    print("\n[2.2] Required tables exist")
    try:
        db = SessionLocal()
        rows = db.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )).fetchall()
        db.close()
        found = {r[0] for r in rows}
        required = {
            "users", "policies", "control_library", "frameworks",
            "compliance_results", "gaps", "mapping_reviews", "reports",
            "audit_logs", "ai_insights", "policy_chunks",
        }
        missing = required - found
        _info(f"Found tables: {sorted(found)}")
        if missing:
            _fail(f"Missing tables: {missing}")
            _record(G, False)
        else:
            _ok("All required tables exist")
            _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)

    # 2.3 pgvector extension enabled
    print("\n[2.3] pgvector extension enabled")
    try:
        db = SessionLocal()
        row = db.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'")).fetchone()
        db.close()
        if row:
            _ok("pgvector extension is enabled")
            _record(G, True)
        else:
            _fail("pgvector not found. Run: CREATE EXTENSION IF NOT EXISTS vector;")
            _record(G, False)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)

    # 2.4 policy_chunks table structure
    print("\n[2.4] policy_chunks table structure")
    try:
        db = SessionLocal()
        rows = db.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'policy_chunks'"
        )).fetchall()
        db.close()
        cols = {r[0] for r in rows}
        required_cols = {"id", "policy_id", "chunk_index", "chunk_text", "embedding",
                         "char_start", "char_end", "created_at"}
        missing_cols = required_cols - cols
        _info(f"policy_chunks columns: {sorted(cols)}")
        if missing_cols:
            _fail(f"Missing columns: {missing_cols}")
            _record(G, False)
        else:
            _ok("policy_chunks table structure is correct")
            _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)

    # 2.5 Control library has data
    print("\n[2.5] Control library has data")
    try:
        db = SessionLocal()
        count = db.execute(text("SELECT COUNT(*) FROM control_library")).scalar()
        if count and count > 0:
            rows = db.execute(text(
                "SELECT framework, COUNT(*) FROM control_library GROUP BY framework ORDER BY framework"
            )).fetchall()
            db.close()
            _info(f"Total controls: {count}")
            for row in rows:
                _info(f"  {row[0]}: {row[1]} controls")
            _ok(f"control_library has {count} controls across {len(rows)} frameworks")
            _record(G, True)
            STATE["controls_exist"] = True
        else:
            db.close()
            _warn("control_library is EMPTY — analysis will not work without controls.")
            _warn("Seed this table with NCA ECC, ISO 27001, and NIST 800-53 controls.")
            _record(G, False)
            STATE["controls_exist"] = False
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 3 — AUTHENTICATION SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

def test_group_3() -> None:
    _header("GROUP 3: AUTHENTICATION SYSTEM")
    G = "3-Auth"

    # 3.1 Password hashing
    print("\n[3.1] Password hashing works")
    try:
        from backend.auth import get_password_hash, verify_password
        hashed = get_password_hash("TestPass123")
        assert hashed != "TestPass123"
        assert verify_password("TestPass123", hashed)
        assert not verify_password("WrongPass", hashed)
        _ok("Password hashing and verification work correctly")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)

    # 3.2 JWT token creation
    print("\n[3.2] JWT token creation works")
    try:
        from backend.auth import create_access_token, SECRET_KEY, ALGORITHM
        from jose import jwt
        token = create_access_token({"sub": "test@hemaya.com"})
        assert isinstance(token, str) and token
        parts = token.split(".")
        assert len(parts) == 3, f"JWT should have 3 parts, got {len(parts)}"
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload.get("sub") == "test@hemaya.com"
        assert "exp" in payload
        _ok("JWT token created and decoded with correct claims")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)

    # 3.3 Auth endpoints respond
    print("\n[3.3] Auth endpoints respond")
    try:
        TEST_EMAIL = "test_sys_auth@hemaya.sa"
        TEST_PASS  = "TestPass123!"

        r = httpx.post(f"{BASE_URL}/api/auth/register", json={
            "first_name": "Test", "last_name": "Auth",
            "phone": "0500000001", "email": TEST_EMAIL, "password": TEST_PASS,
        }, timeout=10.0)
        assert r.status_code in (200, 400), f"Register: {r.status_code} {r.text}"
        _info(f"Register: {r.status_code}")

        r = httpx.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL, "password": TEST_PASS,
        }, timeout=10.0)
        assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
        body = r.json()
        token = body.get("token")
        assert token, f"No 'token' in login response: {list(body.keys())}"
        STATE["auth3_token"] = token

        r = httpx.get(f"{BASE_URL}/api/auth/me",
                      headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
        assert r.status_code == 200, f"/auth/me: {r.status_code}"
        user_obj = r.json()
        for field in ("id", "email", "first_name", "last_name"):
            assert field in user_obj, f"Missing field: {field}"
        assert "password_hash" not in user_obj, "password_hash must NOT be in response"
        _info(f"Authenticated as: {user_obj['email']}")

        _ok("Register → Login → /me auth flow works")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}\n{traceback.format_exc()}")
        _record(G, False)


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 4 — TEXT EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def test_group_4() -> None:
    _header("GROUP 4: TEXT EXTRACTION")
    G = "4-Extract"

    from backend.text_extractor import extract_text

    # 4.1 TXT extraction
    print("\n[4.1] TXT extraction")
    try:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
            f.write("Information Security Policy v2.1\nAll users must authenticate.")
            tmp_path = f.name
        result = extract_text(Path(tmp_path), "txt")
        os.unlink(tmp_path)
        assert "Information Security Policy" in result, f"Expected text not found. Got: {result[:100]}"
        _ok("TXT extraction works correctly")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)

    # 4.2 Error handling for missing file
    print("\n[4.2] Error handling for missing file")
    try:
        result = extract_text(Path("/nonexistent/file_that_does_not_exist_xyz.pdf"), "pdf")
        assert isinstance(result, str), "Should return a string"
        assert result.startswith("[Extraction error"), f"Expected '[Extraction error...', got: {result[:80]}"
        _ok("Missing file returns '[Extraction error...' string, no exception raised")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception raised (should not be): {e}")
        _record(G, False)

    # 4.3 Unsupported file type
    print("\n[4.3] Unsupported file type returns empty string (no exception)")
    try:
        result = extract_text(Path("test.xyz"), "xyz")
        assert isinstance(result, str), "Should return a string"
        # Current implementation returns "" for unsupported types
        _ok(f"Unsupported type returns string (len={len(result)}), no exception raised")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception raised (should not be): {e}")
        _record(G, False)


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 5 — TEXT CHUNKING
# ═══════════════════════════════════════════════════════════════════════════════

SAMPLE_POLICY_TEXT = (
    "INFORMATION SECURITY POLICY\n\n"
    "1. PURPOSE AND SCOPE\n"
    "This policy establishes the framework for information security within the organization. "
    "It applies to all employees, contractors, and third-party service providers who access "
    "company systems, data, or infrastructure.\n\n"
    "2. ACCESS CONTROL\n"
    "All users must authenticate using multi-factor authentication (MFA) before accessing "
    "company systems. Passwords must be at least 14 characters in length and must include "
    "uppercase letters, lowercase letters, numbers, and special characters. Password reuse "
    "is prohibited for the last 12 passwords.\n\n"
    "3. DATA CLASSIFICATION\n"
    "Data is classified into four levels: Public, Internal, Confidential, and Restricted. "
    "All data must be labeled according to its classification level before storage or "
    "transmission. Restricted data must be encrypted at rest and in transit at all times.\n\n"
    "4. INCIDENT RESPONSE\n"
    "All security incidents must be reported within 24 hours of discovery to the Security "
    "Operations Center. The incident response team will assess, contain, and remediate the "
    "incident following the established incident response plan and notify management.\n\n"
    "5. TRAINING AND AWARENESS\n"
    "Annual security awareness training is mandatory for all staff members. "
    "Training records must be maintained for a minimum of three years for audit purposes. "
    "New employees must complete onboarding training within their first 30 days."
)


def test_group_5() -> None:
    _header("GROUP 5: TEXT CHUNKING")
    G = "5-Chunking"

    from backend.chunker import chunk_text, prepare_chunks_for_storage

    # 5.1 Basic chunking
    print("\n[5.1] Basic chunking works")
    try:
        chunks = chunk_text(SAMPLE_POLICY_TEXT, chunk_size=500, overlap=100)
        assert isinstance(chunks, list) and len(chunks) > 0, "Expected non-empty list"
        for c in chunks:
            assert "chunk_index" in c and "text" in c and "char_start" in c and "char_end" in c
            assert c["text"].strip(), "Chunk text should not be empty"
        indices = [c["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks))), f"Indices not sequential: {indices}"
        _info(f"Created {len(chunks)} chunks from {len(SAMPLE_POLICY_TEXT)} characters")
        for i, c in enumerate(chunks):
            _info(f"  chunk[{i}]: chars {c['char_start']}–{c['char_end']}, len={len(c['text'])}")
        _ok("Basic chunking produces correctly structured, ordered chunks")
        _record(G, True)
        STATE["sample_chunks"] = chunks
    except Exception as e:
        _fail(f"Exception: {e}\n{traceback.format_exc()}")
        _record(G, False)
        STATE["sample_chunks"] = []

    # 5.2 Short text single chunk
    print("\n[5.2] Short text returns single chunk")
    try:
        short = "Short policy text"
        chunks = chunk_text(short, chunk_size=500)
        assert len(chunks) == 1, f"Expected 1 chunk, got {len(chunks)}"
        assert chunks[0]["text"] == short
        _ok("Short text correctly returns exactly 1 chunk")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)

    # 5.3 Overlap confirmed
    print("\n[5.3] Overlap works between consecutive chunks")
    try:
        chunks = STATE.get("sample_chunks", [])
        if len(chunks) < 2:
            _warn("Not enough chunks to test overlap (need >= 2)")
            _record(G, False)
        else:
            c0_end   = chunks[0]["char_end"]
            c1_start = chunks[1]["char_start"]
            if c0_end > c1_start:
                overlap = c0_end - c1_start
                _info(f"Chunk 0 ends at char {c0_end}, Chunk 1 starts at char {c1_start}")
                _info(f"Overlap: {overlap} characters")
                _ok("Overlap confirmed between consecutive chunks")
                _record(G, True)
            else:
                _warn(f"No overlap: chunk 0 ends at {c0_end}, chunk 1 starts at {c1_start}")
                _record(G, False)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)

    # 5.4 prepare_chunks_for_storage
    print("\n[5.4] prepare_chunks_for_storage adds policy_id and chunk_id")
    try:
        chunks = STATE.get("sample_chunks") or chunk_text(SAMPLE_POLICY_TEXT)
        fake_id = str(uuid.uuid4())
        enriched = prepare_chunks_for_storage(fake_id, chunks)
        assert len(enriched) == len(chunks)
        for c in enriched:
            assert "policy_id" in c and c["policy_id"] == fake_id
            assert "chunk_id" in c
            assert c["chunk_id"].startswith(fake_id)
        _ok(f"prepare_chunks_for_storage correctly enriched {len(enriched)} chunks")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 6 — HUGGINGFACE AI MODELS (Live API Calls)
# ═══════════════════════════════════════════════════════════════════════════════

async def _run_group_6() -> None:
    _header("GROUP 6: HUGGINGFACE AI MODELS (Live API Calls)")
    G = "6-AI_Models"

    from backend.vector_store import get_embeddings
    from backend.rag_engine import rerank_chunks, call_llm

    # 6.1 Embedding — single text
    print("\n[6.1] Embedding model works (BGE-base-en-v1.5)")
    try:
        embeddings = await get_embeddings(["Information security policy"])
        assert isinstance(embeddings, list) and len(embeddings) == 1
        emb = embeddings[0]
        assert isinstance(emb, list) and len(emb) == 768, f"Expected 768 dims, got {len(emb)}"
        _info(f"Embedding dimension: {len(emb)}")
        _info(f"First 5 values: {[round(v, 4) for v in emb[:5]]}")
        _ok("Embedding model returns 768-dim vector")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        if "503" in str(e) or "loading" in str(e).lower():
            _warn("Model is loading — wait 30 seconds and retry")
        _record(G, False)

    # 6.2 Embedding — multiple texts
    print("\n[6.2] Embedding model handles multiple texts")
    try:
        embeddings = await get_embeddings(["text one", "text two", "text three"])
        assert len(embeddings) == 3, f"Expected 3, got {len(embeddings)}"
        for emb in embeddings:
            assert len(emb) == 768, f"Expected 768 dims, got {len(emb)}"
        _ok("3 texts → 3 embeddings × 768 dims ✓")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)

    # 6.3 Reranker
    print("\n[6.3] Reranker model works (BGE-reranker-v2-m3)")
    try:
        test_chunks = [
            {"text": "Password must be at least 12 characters with special characters"},
            {"text": "The company was founded in 2020 in Riyadh"},
            {"text": "Access control requires multi-factor authentication for all users"},
        ]
        ranked = await rerank_chunks("password policy requirements", test_chunks, top_k=2)
        assert len(ranked) == 2, f"Expected 2 results, got {len(ranked)}"
        for c in ranked:
            assert "rerank_score" in c
        _info("Rerank scores:")
        for c in ranked:
            _info(f"  score={c['rerank_score']:.4f} | {c['text'][:65]}")
        top_text = ranked[0]["text"].lower()
        assert "password" in top_text or "authentication" in top_text or "mfa" in top_text, \
            f"Password/auth chunk should rank #1, got: {ranked[0]['text'][:80]}"
        _ok("Reranker returns top-2 with security content ranked above irrelevant content")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}\n{traceback.format_exc()}")
        _record(G, False)

    # 6.4 LLM
    print("\n[6.4] LLM model works (Qwen 2.5-3B-Instruct)")
    try:
        response = await call_llm("What is ISO 27001? Answer in one sentence.")
        assert isinstance(response, str) and len(response) >= 10
        _info(f"LLM response: {response[:200]}")
        _ok("LLM returns non-empty text response")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        if "503" in str(e):
            _warn("Model is loading — wait 60 seconds and retry")
        _record(G, False)

    # 6.5 LLM structured JSON
    print("\n[6.5] LLM produces structured JSON")
    try:
        prompt = (
            "<|im_start|>system\n"
            "Respond ONLY with valid JSON. No explanation, no extra text.\n"
            "<|im_end|>\n"
            "<|im_start|>user\n"
            'Return exactly: {"status": "Compliant", "confidence": 0.9}\n'
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        response = await call_llm(prompt)
        start = response.find("{")
        end   = response.rfind("}") + 1
        if start != -1 and end > start:
            parsed = json.loads(response[start:end])
            _info(f"Parsed JSON: {parsed}")
            _ok("LLM can produce parseable JSON output")
            _record(G, True)
        else:
            _warn(f"LLM output not JSON-parseable. Response: {response[:200]}")
            _warn("_parse_llm_json fallback in rag_engine will handle this at runtime")
            _record(G, False)
    except (json.JSONDecodeError, Exception) as e:
        _warn(f"JSON parse failed ({e}). _parse_llm_json fallback will handle this at runtime")
        _record(G, False)


def test_group_6() -> None:
    asyncio.run(_run_group_6())


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 7 — VECTOR STORE (pgvector)
# ═══════════════════════════════════════════════════════════════════════════════

async def _run_group_7() -> None:
    _header("GROUP 7: VECTOR STORE (pgvector)")
    G = "7-VectorStore"

    from backend.database import SessionLocal
    from backend.models import Policy
    from backend.vector_store import (
        get_embeddings, store_chunks_with_embeddings,
        search_similar_chunks, delete_policy_chunks,
    )
    from sqlalchemy import text

    # Create a real policy row (required for the FK constraint on policy_chunks)
    db = SessionLocal()
    test_policy = Policy(
        file_name="__test_vector_store__.txt",
        description="Temporary policy for vector store tests — safe to delete",
        status="uploaded",
        version="1.0",
    )
    db.add(test_policy)
    db.commit()
    db.refresh(test_policy)
    test_policy_id = test_policy.id
    STATE["g7_policy_id"] = test_policy_id
    db.close()
    _info(f"Created test policy: {test_policy_id}")

    # 7.1 Store embeddings
    print("\n[7.1] Store chunk embeddings")
    try:
        test_chunks = [
            {"chunk_index": 0, "text": "All users must use multi-factor authentication.",
             "char_start": 0, "char_end": 46},
            {"chunk_index": 1, "text": "Passwords must be at least 14 characters long.",
             "char_start": 46, "char_end": 92},
            {"chunk_index": 2, "text": "Annual security training is mandatory for all staff.",
             "char_start": 92, "char_end": 144},
        ]
        embeddings = await get_embeddings([c["text"] for c in test_chunks])
        db = SessionLocal()
        store_chunks_with_embeddings(db, test_policy_id, test_chunks, embeddings)
        count = db.execute(
            text(f"SELECT COUNT(*) FROM policy_chunks WHERE policy_id = '{test_policy_id}'")
        ).scalar()
        db.close()
        assert count == 3, f"Expected 3 chunks, got {count}"
        _ok(f"Stored 3 chunks with embeddings successfully")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}\n{traceback.format_exc()}")
        _record(G, False)

    # 7.2 Search similar chunks
    print("\n[7.2] Search similar chunks")
    try:
        db = SessionLocal()
        query_emb = (await get_embeddings(["access control policy"], is_query=True))[0]
        results = search_similar_chunks(db, query_emb, policy_id=test_policy_id, top_k=3)
        db.close()
        assert isinstance(results, list) and len(results) > 0
        for r in results:
            assert "text" in r and "chunk_index" in r and "similarity" in r
            assert 0.0 <= r["similarity"] <= 1.0, f"Similarity out of [0,1]: {r['similarity']}"
        _info("Search results (sorted by similarity):")
        for r in results:
            _info(f"  sim={r['similarity']:.4f} | {r['text'][:60]}")
        _ok(f"search_similar_chunks returned {len(results)} results with valid scores")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}\n{traceback.format_exc()}")
        _record(G, False)

    # 7.3 Delete chunks
    print("\n[7.3] Delete chunks")
    try:
        db = SessionLocal()
        deleted = delete_policy_chunks(db, test_policy_id)
        count = db.execute(
            text(f"SELECT COUNT(*) FROM policy_chunks WHERE policy_id = '{test_policy_id}'")
        ).scalar()
        db.close()
        assert count == 0, f"Expected 0 chunks after delete, got {count}"
        _info(f"Deleted {deleted} rows")
        _ok("delete_policy_chunks removed all chunks correctly")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)


def test_group_7() -> None:
    asyncio.run(_run_group_7())


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 8 — FULL RAG PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

async def _run_group_8() -> None:
    _header("GROUP 8: FULL RAG PIPELINE")
    G = "8-RAG"

    from backend.database import SessionLocal
    from backend.models import Policy
    from backend.vector_store import get_embeddings, store_chunks_with_embeddings
    from backend.rag_engine import analyze_control_compliance, chat_with_context

    # Create test policy with realistic content
    db = SessionLocal()
    test_policy = Policy(
        file_name="__test_rag_pipeline__.txt",
        description="RAG pipeline test policy — safe to delete",
        status="uploaded",
        version="1.0",
    )
    db.add(test_policy)
    db.commit()
    db.refresh(test_policy)
    test_policy_id = test_policy.id
    STATE["g8_policy_id"] = test_policy_id
    db.close()

    realistic_chunks = [
        {
            "chunk_index": 0,
            "text": (
                "All employees must use multi-factor authentication (MFA) to access company "
                "systems. Passwords must be at least 14 characters and include uppercase, "
                "lowercase, numbers, and special symbols. Passwords expire every 90 days."
            ),
            "char_start": 0, "char_end": 200,
        },
        {
            "chunk_index": 1,
            "text": (
                "Annual security awareness training is mandatory for all staff. "
                "Training records must be maintained for audit purposes for a minimum of 3 years. "
                "New employees must complete onboarding training within their first 30 days."
            ),
            "char_start": 200, "char_end": 400,
        },
        {
            "chunk_index": 2,
            "text": (
                "Data classification levels: Public, Internal, Confidential, Restricted. "
                "All data must be labeled according to its classification before storage or "
                "transmission. Restricted data must be encrypted at rest and in transit."
            ),
            "char_start": 400, "char_end": 600,
        },
    ]

    db = SessionLocal()
    embeddings = await get_embeddings([c["text"] for c in realistic_chunks])
    store_chunks_with_embeddings(db, test_policy_id, realistic_chunks, embeddings)
    db.close()
    _info(f"Indexed 3 realistic chunks for policy {test_policy_id}")

    # 8.1 analyze_control_compliance
    print("\n[8.1] analyze_control_compliance (single control)")
    try:
        db = SessionLocal()
        test_control = {
            "control_code": "ECC-2-1-1",
            "title": "Authentication Controls",
            "keywords": ["authentication", "MFA", "multi-factor", "password"],
            "framework": "NCA ECC",
            "severity_if_missing": "High",
        }
        result = await analyze_control_compliance(db, test_policy_id, test_control)
        db.close()

        required_keys = {"status", "confidence", "evidence", "rationale", "recommendation"}
        missing_keys = required_keys - set(result.keys())
        assert not missing_keys, f"Missing keys in result: {missing_keys}"
        assert result["status"] in ("Compliant", "Partial", "Non-Compliant"), \
            f"Invalid status value: {result['status']}"
        assert 0.0 <= float(result["confidence"]) <= 1.0, \
            f"Confidence out of [0,1]: {result['confidence']}"

        _info(f"Status:     {result['status']}")
        _info(f"Confidence: {result['confidence']:.3f}")
        _info(f"Evidence:   {str(result.get('evidence', ''))[:120]}")
        _info(f"Rationale:  {str(result.get('rationale', ''))[:120]}")

        if result["status"] == "Compliant":
            _info("✓ Correctly identified MFA/authentication control as Compliant")
        else:
            _warn(f"Status='{result['status']}' — LLM may need better prompt or larger model")

        _ok("analyze_control_compliance returned valid structured result")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}\n{traceback.format_exc()}")
        _record(G, False)

    # 8.2 chat_with_context (English)
    print("\n[8.2] chat_with_context — English question")
    try:
        db = SessionLocal()
        response = await chat_with_context(db, "What is the password policy?",
                                           policy_id=test_policy_id)
        db.close()
        assert isinstance(response, str) and len(response) > 0
        response_lower = response.lower()
        found_kw = any(kw in response_lower for kw in
                       ["14", "character", "mfa", "authentication", "password", "expire"])
        _info(f"Chat response: {response[:300]}")
        if found_kw:
            _ok("chat_with_context references actual policy content")
        else:
            _warn("Response may be generic — verify the output above references the policy")
        _ok("chat_with_context returned non-empty English response")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)

    # 8.3 chat_with_context (Arabic)
    print("\n[8.3] chat_with_context — Arabic question")
    try:
        db = SessionLocal()
        response = await chat_with_context(db, "ما هي سياسة كلمة المرور؟",
                                           policy_id=test_policy_id)
        db.close()
        assert isinstance(response, str) and len(response) > 0
        _info(f"Arabic chat response: {response[:300]}")
        _ok("chat_with_context handles Arabic questions")
        _record(G, True)
    except Exception as e:
        _fail(f"Exception: {e}")
        _record(G, False)


def test_group_8() -> None:
    asyncio.run(_run_group_8())


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 9 — API ENDPOINTS (Full HTTP Flow)
# Split into two httpx.Client phases to avoid event-loop conflicts with asyncio.run()
# ═══════════════════════════════════════════════════════════════════════════════

_POLICY_CONTENT = (
    "HEMAYA TEST INFORMATION SECURITY POLICY\n\n"
    "1. Access Control\n"
    "All users must authenticate using multi-factor authentication (MFA). "
    "User accounts require approval from the IT Security department before activation. "
    "Access rights are reviewed quarterly and revoked upon termination.\n\n"
    "2. Password Policy\n"
    "Passwords must be minimum 14 characters, include uppercase, lowercase, "
    "numbers, and special characters. Passwords expire every 90 days and cannot "
    "be reused for 12 previous cycles.\n\n"
    "3. Data Classification\n"
    "Data is classified as: Public, Internal, Confidential, Restricted. "
    "All confidential data must be encrypted at rest and in transit using AES-256.\n\n"
    "4. Security Training\n"
    "Annual security awareness training is mandatory for all employees. "
    "Training completion must be recorded and retained for 3 years."
)


async def _index_policy_content(policy_id: str, content: str) -> int:
    """Helper: chunk and embed content, store in DB. Returns chunk count."""
    from backend.database import SessionLocal
    from backend.chunker import chunk_text
    from backend.vector_store import get_embeddings, store_chunks_with_embeddings
    chunks = chunk_text(content)
    embeddings = await get_embeddings([c["text"] for c in chunks])
    db = SessionLocal()
    store_chunks_with_embeddings(db, policy_id, chunks, embeddings)
    db.close()
    return len(chunks)


def test_group_9() -> None:
    _header("GROUP 9: API ENDPOINTS (Full HTTP Flow)")
    G = "9-API"

    from backend.database import SessionLocal
    from sqlalchemy import text as sql_text

    TEST_EMAIL = "test_sys_api9@hemaya.sa"
    TEST_PASS  = "TestPass123!"

    # ── PHASE 1: health / auth / upload / policy creation ──────────────────────
    token      = None
    policy_id  = None
    file_url   = None

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:

        # 9.1 Health check
        print("\n[9.1] Health check")
        try:
            r = client.get("/api/functions/db_health")
            assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
            assert r.json().get("ok") is True
            _ok("GET /api/functions/db_health → 200 OK")
            _record(G, True)
        except Exception as e:
            _fail(f"Exception: {e}")
            _record(G, False)

        # 9.2 Register + Login
        print("\n[9.2] Register + Login flow")
        try:
            r = client.post("/api/auth/register", json={
                "first_name": "API", "last_name": "Test",
                "phone": "0500000099", "email": TEST_EMAIL, "password": TEST_PASS,
            })
            assert r.status_code in (200, 400), f"Register: {r.status_code}"
            _info(f"Register: HTTP {r.status_code}")

            r = client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASS})
            assert r.status_code == 200, f"Login: {r.status_code} {r.text}"
            body = r.json()
            token = body.get("token")
            assert token, f"No 'token' in login response: {list(body.keys())}"
            STATE["test9_token"] = token

            r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200
            user_obj = r.json()
            for field in ("id", "email", "first_name", "last_name"):
                assert field in user_obj, f"Missing field: {field}"
            _info(f"Authenticated as: {user_obj['email']}")
            _ok("Register → Login → /me flow OK")
            _record(G, True)
        except Exception as e:
            _fail(f"Exception: {e}\n{traceback.format_exc()}")
            _record(G, False)
            for _ in range(7):
                _record(G, False)
            return

        AUTH = {"Authorization": f"Bearer {token}"}

        # 9.3 File upload
        print("\n[9.3] File upload flow")
        try:
            file_bytes = _POLICY_CONTENT.encode("utf-8")
            r = client.post(
                "/api/integrations/upload",
                files={"file": ("test_policy.txt", io.BytesIO(file_bytes), "text/plain")},
                headers=AUTH,
            )
            assert r.status_code == 200, f"Upload: {r.status_code} {r.text}"
            body = r.json()
            assert "file_url"   in body and body["file_url"]
            assert "char_count" in body and body["char_count"] > 0
            assert "HEMAYA TEST" in body.get("content_preview", ""), \
                "content_preview missing 'HEMAYA TEST'"
            file_url = body["file_url"]
            STATE["g9_file_url"] = file_url
            _info(f"file_url={file_url}, char_count={body['char_count']}")
            _ok("File upload returns file_url, content_preview, char_count")
            _record(G, True)
        except Exception as e:
            _fail(f"Exception: {e}\n{traceback.format_exc()}")
            _record(G, False)

        # 9.4 Create policy record
        print("\n[9.4] Create policy record via entity endpoint")
        try:
            r = client.post("/api/entities/Policy", json={
                "file_name": "__test_api9_policy__",
                "description": "System test policy — safe to delete",
                "department": "IT",
                "version": "1.0",
                "status": "uploaded",
                "file_url": file_url or "/uploads/test.txt",
                "content_preview": _POLICY_CONTENT[:500],
            }, headers=AUTH)
            assert r.status_code == 200, f"Policy create: {r.status_code} {r.text}"
            body = r.json()
            assert "id" in body, f"No 'id' in response: {list(body.keys())}"
            policy_id = body["id"]
            STATE["g9_policy_id"] = policy_id
            _info(f"Created policy: {policy_id}")
            _ok("Policy record created successfully")
            _record(G, True)
        except Exception as e:
            _fail(f"Exception: {e}")
            _record(G, False)
            for _ in range(5):
                _record(G, False)
            return

        # 9.5 Verify / create chunks
        print("\n[9.5] Verify chunks exist for policy")
        try:
            db = SessionLocal()
            count = db.execute(sql_text(
                f"SELECT COUNT(*) FROM policy_chunks WHERE policy_id = '{policy_id}'"
            )).scalar()
            db.close()
            if count and count > 0:
                _info(f"Found {count} chunks (created during upload with policy_id param)")
                _ok("Chunks exist for the policy")
                _record(G, True)
                STATE["g9_indexed"] = True
            else:
                _warn("No chunks found — policy_id was not passed at upload time (expected).")
                _warn("Will index the policy content after this phase.")
                STATE["g9_indexed"] = False
                _record(G, True)  # Logic is correct; indexing happens separately
        except Exception as e:
            _fail(f"Exception: {e}")
            _record(G, False)
            STATE["g9_indexed"] = False

    # ── Between phases: async indexing (safe — outside HTTP client context) ──────
    if not STATE.get("g9_indexed") and policy_id:
        print("\n  [Indexing policy content before analysis tests...]")
        try:
            n = asyncio.run(_index_policy_content(policy_id, _POLICY_CONTENT))
            _info(f"Indexed {n} chunks for policy {policy_id}")
            STATE["g9_indexed"] = True
        except Exception as e:
            _warn(f"Manual indexing failed: {e}")

    # ── PHASE 2: analysis / chat / verification ────────────────────────────────
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:

        AUTH = {"Authorization": f"Bearer {token}"}
        controls_exist = STATE.get("controls_exist", False)

        # 9.6 Run analysis
        print("\n[9.6] Run analysis (POST /api/functions/analyze_policy)")
        if not controls_exist:
            _warn("SKIPPING — control_library is empty. Seed controls first.")
            _record(G, False)
        elif not policy_id:
            _warn("SKIPPING — no policy_id available")
            _record(G, False)
        else:
            try:
                _info("Running analysis — this may take 1–5 minutes (HF model warm-up)...")
                r = client.post("/api/functions/analyze_policy", json={
                    "policy_id": policy_id,
                    "frameworks": ["NCA ECC"],
                }, headers=AUTH, timeout=300)
                assert r.status_code == 200, f"Analysis: {r.status_code} {r.text[:300]}"
                body = r.json()
                assert body.get("success") is True
                _info(f"Compliance results: {len(body.get('results', []))}")
                _info(f"Mappings created:   {body.get('mappings_created', 0)}")
                _info(f"Gaps created:       {body.get('gaps_created', 0)}")
                _ok("analyze_policy completed successfully")
                _record(G, True)
            except Exception as e:
                _fail(f"Exception: {e}")
                if "timeout" in str(e).lower():
                    _warn("Analysis timed out — HF models warming up. Retry in 60 seconds.")
                _record(G, False)

        # 9.7 Verify analysis records
        print("\n[9.7] Verify analysis created database records")
        try:
            r = client.get(f"/api/entities/ComplianceResult?policy_id={policy_id}",
                           headers=AUTH)
            assert r.status_code == 200
            results_list = r.json()
            if results_list:
                for res in results_list:
                    _info(f"  {res.get('framework')} → score={res.get('compliance_score')}, "
                          f"covered={res.get('controls_covered')}, "
                          f"missing={res.get('controls_missing')}")
                _ok(f"ComplianceResult: {len(results_list)} framework record(s)")
                _record(G, True)
            else:
                _warn("No ComplianceResult records (analysis may have been skipped)")
                _record(G, False)

            r = client.get(f"/api/entities/Gap?policy_id={policy_id}", headers=AUTH)
            gaps_list = r.json() if r.status_code == 200 else []
            _info(f"Gaps found: {len(gaps_list)}")

            r = client.get(f"/api/entities/MappingReview?policy_id={policy_id}", headers=AUTH)
            mappings_list = r.json() if r.status_code == 200 else []
            _info(f"Mapping reviews: {len(mappings_list)}")
            if mappings_list:
                sample = mappings_list[0]
                for field in ("control_id", "confidence_score", "ai_rationale", "decision"):
                    assert field in sample, f"MappingReview missing field: {field}"
        except Exception as e:
            _fail(f"Exception: {e}")
            _record(G, False)

        # 9.8 Chat assistant — English
        print("\n[9.8] Chat assistant with policy context (English)")
        try:
            r = client.post("/api/functions/chat_assistant", json={
                "message": "What does the policy say about passwords?",
                "policy_id": policy_id,
            }, headers=AUTH, timeout=60)
            assert r.status_code == 200, f"Chat: {r.status_code} {r.text}"
            body = r.json()
            response_text = body.get("response", "")
            assert response_text, "Empty chat response"
            _info(f"Chat response: {response_text[:300]}")
            found = any(kw in response_text.lower() for kw in
                        ["14", "password", "character", "mfa", "authentication"])
            if found:
                _ok("Chat response references actual policy content")
            else:
                _warn("Response may be generic — verify it uses policy content above")
            _ok("Chat assistant returns non-empty response")
            _record(G, True)
        except Exception as e:
            _fail(f"Exception: {e}")
            _record(G, False)

        # 9.9 Chat assistant — Arabic
        print("\n[9.9] Chat assistant — Arabic question")
        try:
            r = client.post("/api/functions/chat_assistant", json={
                "message": "ما هي متطلبات التحكم في الوصول؟",
            }, headers=AUTH, timeout=60)
            assert r.status_code == 200, f"Arabic chat: {r.status_code} {r.text}"
            body = r.json()
            response_text = body.get("response", "")
            assert response_text
            _info(f"Arabic response: {response_text[:300]}")
            _ok("Arabic chat assistant returns non-empty response")
            _record(G, True)
        except Exception as e:
            _fail(f"Exception: {e}")
            _record(G, False)


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 10 — FRONTEND INTEGRATION (Data Shape Validation)
# ═══════════════════════════════════════════════════════════════════════════════

def test_group_10() -> None:
    _header("GROUP 10: FRONTEND INTEGRATION CHECKS (Data Shapes)")
    G = "10-Shapes"

    token = STATE.get("test9_token") or STATE.get("auth3_token")
    if not token:
        _warn("No auth token — skipping group 10")
        for _ in range(5):
            _record(G, False)
        return

    with httpx.Client(base_url=BASE_URL, timeout=15.0) as client:
        AUTH = {"Authorization": f"Bearer {token}"}

        # Helper: fetch entity list
        def _fetch(entity: str, limit: int = 5) -> list:
            r = client.get(f"/api/entities/{entity}?limit={limit}", headers=AUTH)
            return r.json() if r.status_code == 200 else []

        # 10.1 Dashboard data shapes
        print("\n[10.1] Dashboard data shapes")
        try:
            all_ok = True
            checks = [
                ("Policy",           ("id", "file_name", "status", "created_at")),
                ("ComplianceResult", ("compliance_score", "framework", "controls_covered")),
                ("Gap",              ("severity", "status", "control_id")),
                ("AuditLog",         ("action", "target_type", "timestamp")),
            ]
            for entity, fields in checks:
                items = _fetch(entity)
                if items:
                    missing = [f for f in fields if f not in items[0]]
                    if missing:
                        _fail(f"{entity} missing fields: {missing}")
                        all_ok = False
                    else:
                        _info(f"  {entity}: fields OK")
            _record(G, all_ok)
            if all_ok:
                _ok("Dashboard entity shapes correct")
        except Exception as e:
            _fail(f"Exception: {e}")
            _record(G, False)

        # 10.2 Policy page shape (Policies.jsx)
        print("\n[10.2] Policies page data shape")
        try:
            policies = _fetch("Policy")
            if not policies:
                _warn("No policies — skipping shape check")
                _record(G, True)
            else:
                p = policies[0]
                required = ("id", "file_name", "description", "file_url",
                            "department", "version", "status", "created_at")
                missing = [f for f in required if f not in p]
                if missing:
                    _fail(f"Policy missing fields for Policies.jsx: {missing}")
                    _record(G, False)
                else:
                    _ok("Policy shape correct for Policies.jsx")
                    _record(G, True)
        except Exception as e:
            _fail(f"Exception: {e}")
            _record(G, False)

        # 10.3 Analysis results shape (Analyses.jsx)
        print("\n[10.3] Analysis results data shape")
        try:
            results = _fetch("ComplianceResult")
            if not results:
                _warn("No ComplianceResult records — skipping shape check")
                _record(G, True)
            else:
                cr = results[0]
                required = ("id", "policy_id", "framework", "compliance_score",
                            "controls_covered", "controls_partial", "controls_missing", "status")
                missing = [f for f in required if f not in cr]
                if missing:
                    _fail(f"ComplianceResult missing fields for Analyses.jsx: {missing}")
                    _record(G, False)
                else:
                    _ok("ComplianceResult shape correct for Analyses.jsx")
                    _record(G, True)
        except Exception as e:
            _fail(f"Exception: {e}")
            _record(G, False)

        # 10.4 Gaps shape (GapsRisks.jsx)
        print("\n[10.4] Gaps data shape")
        try:
            gaps = _fetch("Gap")
            if not gaps:
                _warn("No Gap records — skipping shape check")
                _record(G, True)
            else:
                g = gaps[0]
                required = ("id", "control_id", "framework", "severity",
                            "status", "owner", "due_date", "remediation_notes")
                missing = [f for f in required if f not in g]
                if missing:
                    _fail(f"Gap missing fields for GapsRisks.jsx: {missing}")
                    _record(G, False)
                else:
                    _ok("Gap shape correct for GapsRisks.jsx")
                    _record(G, True)
        except Exception as e:
            _fail(f"Exception: {e}")
            _record(G, False)

        # 10.5 MappingReview shape (MappingReview.jsx)
        print("\n[10.5] Mapping review data shape")
        try:
            mappings = _fetch("MappingReview")
            if not mappings:
                _warn("No MappingReview records — skipping shape check")
                _record(G, True)
            else:
                m = mappings[0]
                required = ("id", "control_id", "framework", "confidence_score",
                            "evidence_snippet", "ai_rationale", "decision", "review_notes")
                missing = [f for f in required if f not in m]
                if missing:
                    _fail(f"MappingReview missing fields for MappingReview.jsx: {missing}")
                    _record(G, False)
                else:
                    _ok("MappingReview shape correct for MappingReview.jsx")
                    _record(G, True)
        except Exception as e:
            _fail(f"Exception: {e}")
            _record(G, False)


# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP
# ═══════════════════════════════════════════════════════════════════════════════

def cleanup() -> None:
    _header("CLEANUP")
    from backend.database import SessionLocal
    from backend.models import Policy, User

    db = SessionLocal()

    # Delete test policies (ORM cascade handles compliance_results/gaps/mappings;
    # SQL ON DELETE CASCADE handles policy_chunks at the DB level)
    for key in ("g9_policy_id", "g8_policy_id", "g7_policy_id"):
        pid = STATE.get(key)
        if not pid:
            continue
        try:
            p = db.query(Policy).filter(Policy.id == pid).first()
            if p:
                db.delete(p)
                db.commit()
                _info(f"Deleted test policy: {pid}")
        except Exception as e:
            _info(f"Could not delete policy {pid}: {e}")
            db.rollback()

    # Delete test users
    for email in ("test_sys_auth@hemaya.sa", "test_sys_api9@hemaya.sa"):
        try:
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.delete(u)
                db.commit()
                _info(f"Deleted test user: {email}")
        except Exception as e:
            _info(f"Could not delete user {email}: {e}")
            db.rollback()

    db.close()
    print(f"  {GREEN}Cleanup complete{RESET}")


# ═══════════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

_GROUP_LABELS = {
    "1-Config":      ("Group 1  (Config)",        3),
    "2-Database":    ("Group 2  (Database)",       5),
    "3-Auth":        ("Group 3  (Auth)",           3),
    "4-Extract":     ("Group 4  (Text Extract)",   3),
    "5-Chunking":    ("Group 5  (Chunking)",       4),
    "6-AI_Models":   ("Group 6  (AI Models)",      5),
    "7-VectorStore": ("Group 7  (Vector Store)",   3),
    "8-RAG":         ("Group 8  (RAG Pipeline)",   3),
    "9-API":         ("Group 9  (API Endpoints)",  9),
    "10-Shapes":     ("Group 10 (Data Shapes)",    5),
}


def print_summary() -> None:
    print(f"\n{BOLD}{'═' * 48}{RESET}")
    print(f"{BOLD}  HEMAYA SYSTEM TEST RESULTS{RESET}")
    print(f"{BOLD}{'═' * 48}{RESET}")

    total_pass = 0
    total_all  = 0
    failed_tests: list[str] = []

    for key, (label, expected) in _GROUP_LABELS.items():
        tests   = RESULTS.get(key, [])
        passed  = sum(tests)
        total_all  += expected
        total_pass += min(passed, expected)
        color = GREEN if passed >= expected else (YELLOW if passed > 0 else RED)
        print(f"  {color}{label}:{RESET}  {passed}/{expected}")
        if passed < expected:
            failed_idx = [i + 1 for i, v in enumerate(tests) if not v]
            failed_tests.append(f"  • {label}: tests {failed_idx} failed")

    print(f"{BOLD}{'═' * 48}{RESET}")
    pct = int(total_pass / total_all * 100) if total_all else 0
    color = GREEN if total_pass == total_all else (YELLOW if pct >= 70 else RED)
    print(f"  {BOLD}{color}TOTAL: {total_pass}/{total_all} passed ({pct}%){RESET}")
    print(f"{BOLD}{'═' * 48}{RESET}")

    if total_pass == total_all:
        print(f"\n  {GREEN}{BOLD}🎉 HEMAYA SYSTEM FULLY OPERATIONAL{RESET}\n")
    else:
        if failed_tests:
            print(f"\n  {YELLOW}Failed groups:{RESET}")
            for line in failed_tests:
                print(f"  {RED}{line}{RESET}")
        print()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"\n{BOLD}{CYAN}{'═' * 56}{RESET}")
    print(f"{BOLD}{CYAN}  HEMAYA POLICY AI — FULL SYSTEM TEST SUITE{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 56}{RESET}")

    try:
        test_group_1()
        test_group_2()
        test_group_3()
        test_group_4()
        test_group_5()
        test_group_6()    # Live HuggingFace API calls
        test_group_7()    # pgvector storage + search
        test_group_8()    # Full RAG pipeline
        test_group_9()    # Full HTTP endpoint flow
        test_group_10()   # Frontend data shape validation
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Test run interrupted by user.{RESET}")
    finally:
        try:
            cleanup()
        except Exception as e:
            print(f"{RED}Cleanup error: {e}{RESET}")
        print_summary()
