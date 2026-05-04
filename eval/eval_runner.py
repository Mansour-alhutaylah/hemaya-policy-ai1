"""
eval_runner.py — Evaluation harness for checkpoint analysis accuracy.

Runs checkpoint analysis on 4 test policies and reports:
  - Per-policy compliance score
  - Per-control breakdown (Compliant/Partial/Non-Compliant)
  - Comparison with baseline scores
  - Accuracy delta

Usage:
  python eval/eval_runner.py
"""
import asyncio
import json
import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
load_dotenv()

# Use a dedicated engine with pool_size=1 so it doesn't compete
# with the running backend server for Supabase connections
_eval_engine = create_engine(
    os.getenv("DATABASE_URL"),
    pool_size=1, max_overflow=0, pool_pre_ping=True,
    connect_args={"connect_timeout": 10},
)
SessionLocal = sessionmaker(bind=_eval_engine, autocommit=False, autoflush=False)


# -- Baseline scores (pre-BM25, from last analysis run) ----------------------
BASELINE = {
    "AlphaSecure_Cybersecurity_Policy_NCA_ECC.docx":  88.3,
    "SDS_Information_Security_Policy_NCA_ECC.docx":   71.0,
    "National_Shield_Full_Compliance_Policy.docx":    80.6,
    "Gulf_Medical_Center_Cybersecurity_Policy.docx":  48.4,
}

# Test policy IDs (one per unique policy, with most chunks)
TEST_POLICIES = {
    "AlphaSecure_Cybersecurity_Policy_NCA_ECC.docx":  "440c5489",
    "SDS_Information_Security_Policy_NCA_ECC.docx":   "2e767948",
    "National_Shield_Full_Compliance_Policy.docx":    "8e1a5e31",
    "Gulf_Medical_Center_Cybersecurity_Policy.docx":  "f8579d3c",
}


def get_full_policy_id(db, prefix):
    """Resolve short ID prefix to full policy ID."""
    row = db.execute(text(
        "SELECT id FROM policies WHERE id LIKE :prefix"
    ), {"prefix": f"{prefix}%"}).fetchone()
    return row[0] if row else None


async def run_eval():
    from backend.checkpoint_analyzer import run_checkpoint_analysis

    db = SessionLocal()
    results = {}

    print("\n" + "=" * 70)
    print("EVALUATION HARNESS — BM25 Hybrid Retrieval (Iteration 3)")
    print("=" * 70)

    for policy_name, id_prefix in TEST_POLICIES.items():
        policy_id = get_full_policy_id(db, id_prefix)
        if not policy_id:
            print(f"\n  SKIP: {policy_name} — policy ID not found")
            continue

        # Check chunks exist
        chunks = db.execute(text(
            "SELECT COUNT(*) FROM policy_chunks "
            "WHERE policy_id=:pid AND embedding IS NOT NULL"
        ), {"pid": policy_id}).fetchone()[0]

        if chunks == 0:
            print(f"\n  SKIP: {policy_name} — no embedded chunks")
            continue

        # Clear previous analysis data for this policy
        db.execute(text("DELETE FROM ai_insights WHERE policy_id=:pid"), {"pid": policy_id})
        db.execute(text("DELETE FROM gaps WHERE policy_id=:pid"), {"pid": policy_id})
        db.execute(text("DELETE FROM mapping_reviews WHERE policy_id=:pid"), {"pid": policy_id})
        db.execute(text("DELETE FROM compliance_results WHERE policy_id=:pid"), {"pid": policy_id})
        db.commit()

        print(f"\n{'-' * 70}")
        print(f"  Analyzing: {policy_name} ({chunks} chunks)")
        print(f"{'-' * 70}")

        t0 = time.time()
        result = await run_checkpoint_analysis(db, policy_id, ["NCA ECC"])
        elapsed = round(time.time() - t0, 1)

        if "error" in result:
            print(f"  ERROR: {result['error']}")
            continue

        fw_result = result.get("NCA ECC", {})
        score = fw_result.get("score", 0)
        comp = fw_result.get("compliant", 0)
        part = fw_result.get("partial", 0)
        miss = fw_result.get("non_compliant", 0)

        results[policy_name] = {
            "score": score,
            "compliant": comp,
            "partial": part,
            "non_compliant": miss,
            "elapsed": elapsed,
        }

    db.close()

    # -- Report -----------------------------------------------------------
    print("\n\n" + "=" * 70)
    print("EVALUATION REPORT")
    print("=" * 70)
    print(f"{'Policy':<55} {'Baseline':>8} {'New':>8} {'Delta':>8}")
    print("-" * 81)

    any_improvement = False
    any_regression = False

    for policy_name in TEST_POLICIES:
        baseline = BASELINE.get(policy_name, 0)
        if policy_name not in results:
            print(f"{policy_name:<55} {baseline:>7.1f}% {'SKIP':>8}")
            continue

        r = results[policy_name]
        delta = r["score"] - baseline
        marker = ""
        if delta > 0:
            marker = " UP"
            any_improvement = True
        elif delta < 0:
            marker = " DN"
            any_regression = True

        print(f"{policy_name:<55} {baseline:>7.1f}% {r['score']:>7.1f}% {delta:>+7.1f}%{marker}")
        print(f"  {'':>55} C={r['compliant']} P={r['partial']} M={r['non_compliant']} ({r['elapsed']}s)")

    print("-" * 81)

    # Summary
    if results:
        avg_baseline = sum(BASELINE.get(k, 0) for k in results) / len(results)
        avg_new = sum(r["score"] for r in results.values()) / len(results)
        avg_delta = avg_new - avg_baseline
        print(f"{'AVERAGE':<55} {avg_baseline:>7.1f}% {avg_new:>7.1f}% {avg_delta:>+7.1f}%")

    print()
    if any_improvement and not any_regression:
        print("PASS: Accuracy improved with no regressions.")
    elif any_improvement and any_regression:
        print("MIXED: Some improvements, some regressions. Review needed.")
    elif any_regression:
        print("FAIL: Regression detected. Retrieval change may not help.")
    else:
        print("NEUTRAL: No change detected.")

    print()
    print("Retrieval config: BM25 hybrid (0.5 keyword + 0.5 BM25), top 8 chunks")
    print("=" * 70)

    return results


if __name__ == "__main__":
    results = asyncio.run(run_eval())


import uuid as _uuid_iter_g
from sqlalchemy import text as _sql_iter_g

async def run_eval_for_text(text: str, framework: str = "NCA ECC") -> float:
    """Create a temp policy, analyze it, return score, clean up.
    Used by adversarial and consistency tests."""
    from backend.database import SessionLocal
    from backend.chunker import chunk_text
    from backend.vector_store import get_embeddings, store_chunks_with_embeddings
    from backend.checkpoint_analyzer import run_checkpoint_analysis

    if not text or len(text.strip()) < 5:
        text = "Empty document."

    db = SessionLocal()
    pid = str(_uuid_iter_g.uuid4())
    score = 0.0

    try:
        db.execute(_sql_iter_g("""
            INSERT INTO policies
            (id, file_name, description, status, content_preview, uploaded_at, created_at)
            VALUES (:id, 'iter_g_test.txt', 'temp adversarial/consistency test',
                    'processing', :c, NOW(), NOW())
        """), {"id": pid, "c": text[:500]})
        db.commit()

        chunks = chunk_text(text)
        if not chunks:
            return 0.0
        embs = await get_embeddings([c["text"] for c in chunks])
        store_chunks_with_embeddings(db, pid, chunks, embs)

        await run_checkpoint_analysis(db, pid, [framework])

        row = db.execute(_sql_iter_g(
            "SELECT compliance_score FROM compliance_results "
            "WHERE policy_id = :pid ORDER BY analyzed_at DESC LIMIT 1"
        ), {"pid": pid}).fetchone()
        if row:
            score = float(row[0])
    except Exception as e:
        print(f"  ERROR in run_eval_for_text: {e}")
        score = -1.0
    finally:
        try:
            for tbl in ("mapping_reviews", "gaps", "compliance_results",
                        "ai_insights", "policy_chunks"):
                db.execute(_sql_iter_g(f"DELETE FROM {tbl} WHERE policy_id = :p"),
                           {"p": pid})
            db.execute(_sql_iter_g(
                "DELETE FROM audit_logs WHERE target_id = :p"
            ), {"p": pid})
            db.execute(_sql_iter_g(
                "DELETE FROM policies WHERE id = :p"
            ), {"p": pid})
            db.commit()
        except Exception:
            db.rollback()
        db.close()

    return score
