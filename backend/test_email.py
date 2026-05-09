"""
test_email.py — standalone Resend integration test.

Usage (from the repo root):

    # 1. Make sure resend is installed:
    pip install resend==2.10.0

    # 2. Set the API key (or rely on your .env file):
    export RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

    # 3. Run — replace the address with a real inbox you control:
    python -m backend.test_email your@email.com

    # 4. Optional overrides:
    RESEND_API_KEY=re_xxx RESEND_FROM_EMAIL="Himaya Test <onboarding@resend.dev>" \
        python -m backend.test_email your@email.com

The script exercises both send_otp_email() and send_password_reset_email()
and exits with code 0 on success or 1 on failure.
"""

import asyncio
import logging
import os
import sys

# ── Load .env before importing email_utils so RESEND_API_KEY is available ─────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass   # python-dotenv not installed; rely on shell env

# ── Configure visible logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Import after .env is loaded ───────────────────────────────────────────────
from backend.email_utils import (         # noqa: E402
    EmailDeliveryError,
    send_otp_email,
    send_password_reset_email,
)


async def run_tests(to_email: str) -> bool:
    all_passed = True

    # ── Test 1: OTP email ─────────────────────────────────────────────────────
    test_otp = "847291"
    logger.info("=" * 60)
    logger.info("TEST 1 — send_otp_email  to=%s  otp=%s", to_email, test_otp)
    logger.info("=" * 60)
    try:
        await send_otp_email(to_email, test_otp)
        logger.info("TEST 1 PASSED ✓")
    except EmailDeliveryError as e:
        logger.error("TEST 1 FAILED ✗  %s", e)
        logger.error("          public_message: %s", e.public_message)
        all_passed = False
    except Exception as e:
        logger.error("TEST 1 ERROR  (unexpected %s): %s", type(e).__name__, e)
        all_passed = False

    await asyncio.sleep(1)   # brief pause between calls

    # ── Test 2: Password reset email ─────────────────────────────────────────
    reset_otp = "563018"
    logger.info("=" * 60)
    logger.info("TEST 2 — send_password_reset_email  to=%s  otp=%s", to_email, reset_otp)
    logger.info("=" * 60)
    try:
        await send_password_reset_email(to_email, reset_otp)
        logger.info("TEST 2 PASSED ✓")
    except EmailDeliveryError as e:
        logger.error("TEST 2 FAILED ✗  %s", e)
        logger.error("          public_message: %s", e.public_message)
        all_passed = False
    except Exception as e:
        logger.error("TEST 2 ERROR  (unexpected %s): %s", type(e).__name__, e)
        all_passed = False

    return all_passed


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m backend.test_email <recipient@email.com>")
        sys.exit(1)

    to_email = sys.argv[1].strip()
    logger.info("Himaya email integration test")
    logger.info("  RESEND_API_KEY  : %s", ("set (" + os.getenv("RESEND_API_KEY", "")[:8] + "...)") if os.getenv("RESEND_API_KEY") else "NOT SET ← fix this first")
    logger.info("  RESEND_FROM_EMAIL: %s", os.getenv("RESEND_FROM_EMAIL", "(default) Himaya AI <onboarding@resend.dev>"))
    logger.info("  recipient       : %s", to_email)

    if not os.getenv("RESEND_API_KEY"):
        logger.error("RESEND_API_KEY is not set.  Export it or add it to your .env file.")
        sys.exit(1)

    passed = asyncio.run(run_tests(to_email))
    logger.info("")
    if passed:
        logger.info("All tests PASSED.  Check %s inbox for 2 emails.", to_email)
        sys.exit(0)
    else:
        logger.error("One or more tests FAILED.  See errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
