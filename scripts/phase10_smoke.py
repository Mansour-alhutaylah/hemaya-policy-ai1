"""Phase 10 grounding smoke - v1 vs v2 side-by-side on real policy text.

Runs OFFLINE (no DB, no GPT, no network). Compares the v1 character-aligned
1.3x-claim-length sliding-window grounding against the v2 sentence-bounded +
adjacent-pair grounding on a battery of representative claims drawn from the
tracked MID policy fixtures.

Pass criteria (the safety properties of the algorithm change):
  1. v2 accepted set is a SUBSET of v1 accepted set.
     (Sentence-window must be strictly tighter or equal; never grounds a claim
     v1 rejected.)
  2. Every verbatim policy quote still grounds in v2 at sim=1.0 (Stage 1
     substring fast path is preserved).
  3. Cross-sentence verbatim quotes still ground in v2 (adjacent-pair fallback
     works).

Run: python scripts/phase10_smoke.py
"""
from __future__ import annotations

import os
import sys
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from backend.checkpoint_analyzer import (  # noqa: E402
    _find_grounded_evidence as v2_grounded,
    _normalize_text,
)


# ---- Vendored v1 grounding (pre-Phase-10) -------------------------------
def v1_grounded(claimed_evidence, policy_text):
    """Exact copy of pre-Phase-10 algorithm: char-aligned sliding window
    of size max(50, int(len(claim) * 1.3)) over the full normalized policy.
    """
    if not claimed_evidence or not policy_text:
        return False, "", 0.0
    norm_evidence = _normalize_text(claimed_evidence)
    norm_policy = _normalize_text(policy_text)
    if len(norm_evidence) < 10:
        return False, claimed_evidence, 0.0
    if norm_evidence in norm_policy:
        return True, claimed_evidence, 1.0
    win_size = max(50, int(len(norm_evidence) * 1.3))
    best_ratio = 0.0
    best_window = ""
    step = max(20, win_size // 4)
    for i in range(0, max(1, len(norm_policy) - win_size), step):
        window = norm_policy[i:i + win_size]
        ratio = SequenceMatcher(None, norm_evidence, window).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_window = window
    if best_ratio >= 0.75:
        return True, best_window, best_ratio
    return False, claimed_evidence, best_ratio


# ---- Claim batteries ----------------------------------------------------
# Categories:
#   verbatim         : exact policy substring; expect ground in both at sim=1
#   cross_verbatim   : verbatim quote spanning two sentences; v2 needs pair
#   paraphrase       : same idea, different wording; report only
#   lottery          : crafted to fish v1 long-window leniency; v2 should reject
#   hallucinated     : unrelated claim; expect reject in both
def ecc2_battery():
    return [
        ("verbatim_1", "verbatim",
         "Multi-factor authentication (MFA) is required for all remote access"),
        ("verbatim_2", "verbatim",
         "All security policies are reviewed at least annually"),
        ("verbatim_3", "verbatim",
         "The Chief Information Security Officer (CISO) is responsible for overseeing the information security program"),
        ("cross_verbatim_1", "cross_verbatim",
         "User accounts are created through the IT helpdesk following a formal request process. "
         "All users must authenticate using a username and password."),
        ("paraphrase_1", "paraphrase",
         "MFA must be enforced for remote access and for privileged administrators"),
        ("paraphrase_2", "paraphrase",
         "Security policies are subject to annual review and updates on regulatory or technology changes"),
        ("lottery_1", "lottery",
         "The CISO is responsible for the cafeteria opening hours and visitor parking allocation policy"),
        ("lottery_2", "lottery",
         "Quarterly password rotation enforces multi-factor authentication on visitor parking access cards"),
        ("hallucinated_1", "hallucinated",
         "Volcanic eruptions in Iceland are monitored by seismographs in the data center"),
        ("hallucinated_2", "hallucinated",
         "The board of directors approved a $50 million budget for fiber-optic submarine cables"),
    ]


def sacs002_battery():
    return [
        ("verbatim_1", "verbatim",
         "Third Party must establish, maintain, and communicate a Cybersecurity Acceptable Use"),
        ("verbatim_2", "verbatim",
         "Privileged accounts are strictly controlled"),
        ("verbatim_3", "verbatim",
         "Access requests must be approved by the asset owner and the Cybersecurity Officer"),
        ("cross_verbatim_1", "cross_verbatim",
         "A formal request and approval process is required for all privileged access. "
         "Privileged access sessions are logged and monitored."),
        ("paraphrase_1", "paraphrase",
         "Annual cybersecurity awareness training is mandatory for all third-party staff within thirty days of hire"),
        ("lottery_1", "lottery",
         "The Cybersecurity Officer approves vendor parking allocation and quarterly cafeteria budgets"),
        ("hallucinated_1", "hallucinated",
         "The third party shall maintain a fleet of submarines for fiber-optic monitoring"),
    ]


# ---- Runner -------------------------------------------------------------
def run_battery(name, policy, battery):
    print(f"\n== {name} ==")
    print(f"policy: {len(policy)} chars\n")
    print(f"{'label':<22} {'category':<16} {'sim_v1':>7} {'g_v1':>5} {'sim_v2':>7} {'g_v2':>5}")

    rows = []
    accepted_v1 = accepted_v2 = 0
    for label, category, claim in battery:
        g1, _, sim1 = v1_grounded(claim, policy)
        g2, _, sim2 = v2_grounded(claim, policy)
        accepted_v1 += int(g1)
        accepted_v2 += int(g2)
        rows.append((label, category, claim, sim1, g1, sim2, g2))
        print(f"{label:<22} {category:<16} {sim1:>7.3f} {str(g1):>5} {sim2:>7.3f} {str(g2):>5}")

    print(f"\nv1 accepted: {accepted_v1}/{len(battery)}")
    print(f"v2 accepted: {accepted_v2}/{len(battery)}")

    # Safety property checks
    failures = []

    # SP1: every verbatim must ground in v2 at sim=1.0
    for label, category, claim, sim1, g1, sim2, g2 in rows:
        if category == "verbatim" and (not g2 or sim2 < 1.0):
            failures.append(f"verbatim {label} did not pass Stage 1: g2={g2} sim2={sim2:.3f}")

    # SP2: cross-sentence verbatim must ground in v2 (pair fallback works)
    for label, category, claim, sim1, g1, sim2, g2 in rows:
        if category == "cross_verbatim" and not g2:
            failures.append(f"cross_verbatim {label} not grounded by v2: sim2={sim2:.3f}")

    # SP3: v2 accepted set is subset of v1 accepted set
    for label, category, claim, sim1, g1, sim2, g2 in rows:
        if g2 and not g1:
            failures.append(f"{label}: v2 grounded a claim v1 rejected (sim1={sim1:.3f}, sim2={sim2:.3f}) - v2 must be tighter or equal")

    # Reporting: v1 accepted but v2 rejected (the goal of Phase 10 - lottery catch)
    flips_g1_to_r2 = [
        r for r in rows if r[4] and not r[6]  # g1 True, g2 False
    ]
    flips_r1_to_g2 = [
        r for r in rows if not r[4] and r[6]  # g1 False, g2 True
    ]

    print(f"v1->v2 flips (grounded -> rejected, lottery catch): {len(flips_g1_to_r2)}")
    for label, category, claim, sim1, g1, sim2, g2 in flips_g1_to_r2:
        print(f"  {label} [{category}]: sim {sim1:.3f}->{sim2:.3f}")
        print(f"    claim: {claim[:90]!r}")
    print(f"v1->v2 flips (rejected -> grounded, MUST be 0): {len(flips_r1_to_g2)}")
    for label, category, claim, sim1, g1, sim2, g2 in flips_r1_to_g2:
        print(f"  {label} [{category}]: sim {sim1:.3f}->{sim2:.3f}")

    return rows, failures


def main():
    ecc2 = open("data/test_policies/medium_policy.txt", encoding="utf-8").read()
    sacs = open("data/test_policies/sacs002_medium_policy.txt", encoding="utf-8").read()

    rows1, fails1 = run_battery("ECC-2 / MID", ecc2, ecc2_battery())
    rows2, fails2 = run_battery("SACS-002 / MID", sacs, sacs002_battery())

    print("\n" + "=" * 60)
    print("SUMMARY")
    all_fails = fails1 + fails2
    if all_fails:
        print("FAIL: safety property violations:")
        for f in all_fails:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("PASS: all safety properties hold")
        print("  - every verbatim grounds in v2 at sim=1.0")
        print("  - every cross-sentence verbatim grounds in v2 via pair fallback")
        print("  - v2 accepted set is subset of v1 accepted set (strictly tighter or equal)")


if __name__ == "__main__":
    main()
