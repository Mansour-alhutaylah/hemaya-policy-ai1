"""Adversarial tests — system should reject nonsense inputs."""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval.eval_runner import run_eval_for_text

CASES = [
    {
        "name": "near_empty",
        "text": "Security policy.",
        "max_score": 15.0,
        "reason": "Near-empty document must score very low",
    },
    {
        "name": "vague_repetition",
        "text": ("We take security seriously. We protect our data. "
                 "We care about compliance. ") * 30,
        "max_score": 30.0,
        "reason": "Vague repetition is not real compliance",
    },
    {
        "name": "framework_as_policy",
        "text": ("ECC-1-1-1: Cybersecurity governance. "
                 "ECC-2-2-3: MFA required. "
                 "ECC-3-1-1: Security event logging. "
                 "ECC-2-4-1: Encryption standards. ") * 5,
        "max_score": 40.0,
        "reason": "Listing control codes is not implementing them",
    },
    {
        "name": "negated_mandatories",
        "text": ("MFA shall NOT be required. "
                 "Encryption is NOT enforced. "
                 "Logging is NOT performed. "
                 "Backups are NOT defined. "
                 "Vulnerability scanning is NOT conducted. ") * 5,
        "max_score": 25.0,
        "reason": "Negated requirements should not be marked compliant",
    },
]


async def main():
    print("=" * 70)
    print("ADVERSARIAL TESTS")
    print("=" * 70)

    failed = []
    for case in CASES:
        print(f"\n  Testing: {case['name']}")
        score = await run_eval_for_text(case["text"])
        if score < 0:
            print(f"    ERROR running test")
            failed.append(case["name"])
            continue
        print(f"    Score: {score:.1f}%  (max allowed: {case['max_score']:.0f}%)")
        if score > case["max_score"]:
            print(f"    FAIL: {case['reason']}")
            failed.append(case["name"])
        else:
            print(f"    PASS")

    print("\n" + "=" * 70)
    if failed:
        print(f"FAILED ({len(failed)}): {', '.join(failed)}")
        return 1
    print("ALL ADVERSARIAL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
