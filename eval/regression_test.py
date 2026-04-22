"""
regression_test.py — Regression gate for checkpoint analysis accuracy.

Runs the full eval harness and checks each policy score against
minimum thresholds. Exits 1 on any regression, 0 if all pass.

Usage:
  python eval/regression_test.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval.eval_runner import run_eval, TEST_POLICIES


# Minimum accuracy thresholds (score %).
# If any policy drops below its threshold, the test fails.
THRESHOLDS = {
    "Desert_Trading_IT_Security_Guidelines.docx":      5.0,
    "Gulf_Medical_Center_Cybersecurity_Policy.docx":   40.0,
    "SDS_Information_Security_Policy_NCA_ECC.docx":    60.0,
    "National_Shield_Full_Compliance_Policy.docx":     75.0,
    "AlphaSecure_Cybersecurity_Policy_NCA_ECC.docx":   75.0,
}


async def main():
    print("\n" + "=" * 70)
    print("REGRESSION TEST")
    print("=" * 70)

    results = await run_eval()

    if not results:
        print("\nFAIL: No results returned from eval harness.")
        return 1

    print("\n" + "=" * 70)
    print("REGRESSION GATE")
    print("=" * 70)
    print(f"{'Policy':<55} {'Score':>7} {'Min':>7} {'Result':>8}")
    print("-" * 79)

    failed = []

    for policy_name, threshold in THRESHOLDS.items():
        if policy_name not in results:
            # Policy not in TEST_POLICIES or was skipped
            if policy_name in TEST_POLICIES:
                print(f"{policy_name:<55} {'SKIP':>7} {threshold:>6.1f}% {'--':>8}")
            continue

        score = results[policy_name]["score"]
        passed = score >= threshold
        status = "PASS" if passed else "REGRESSION"

        print(f"{policy_name:<55} {score:>6.1f}% {threshold:>6.1f}% {status:>10}")

        if not passed:
            failed.append({
                "policy": policy_name,
                "score": score,
                "threshold": threshold,
                "gap": round(threshold - score, 1),
            })

    print("-" * 79)

    if failed:
        print(f"\nFAIL: {len(failed)} regression(s) detected:\n")
        for f in failed:
            print(f"  {f['policy']}")
            print(f"    Score: {f['score']}% (min: {f['threshold']}%, "
                  f"below by {f['gap']}%)\n")
        return 1

    print("\nAll regression tests passed.")
    return 0


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
