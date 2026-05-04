"""Consistency test — same input, multiple runs, must produce stable scores.
With Iteration E cache, second+ runs should be byte-identical."""
import sys, os, asyncio, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval.eval_runner import run_eval_for_text

SAMPLE_POLICY = """
Information Security Policy

1. Authentication
The organization shall implement multi-factor authentication for all
remote access to critical systems.

2. Encryption
All data at rest shall be encrypted using AES-256 encryption standards.
All data in transit shall use TLS 1.2 or higher.

3. Roles
The Chief Information Security Officer is appointed by the board and
reports to senior management.

4. Logging
Security event logging is enabled on all critical systems and reviewed
weekly by the security team.

5. Incident Response
An incident response plan is documented, approved, and tested annually.

6. Review
This policy shall be reviewed and updated at least annually.
""" * 2

MAX_VARIANCE = 2.0  # percentage points


async def main():
    print("=" * 70)
    print("CONSISTENCY TEST — same input, multiple runs")
    print("=" * 70)

    scores = []
    for i in range(3):
        print(f"\n  Run {i+1}/3...")
        s = await run_eval_for_text(SAMPLE_POLICY)
        if s < 0:
            print(f"    ERROR")
            return 1
        scores.append(s)
        print(f"    Score: {s:.2f}%")

    variance = max(scores) - min(scores)
    stdev = statistics.stdev(scores) if len(scores) > 1 else 0
    print(f"\n  Spread: {variance:.2f} points")
    print(f"  StDev:  {stdev:.2f}")

    print("\n" + "=" * 70)
    if variance > MAX_VARIANCE:
        print(f"FAILED: variance {variance:.1f} > tolerance {MAX_VARIANCE}")
        return 1
    print(f"PASSED: variance {variance:.2f} pt within {MAX_VARIANCE} pt tolerance")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
