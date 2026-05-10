"""
test_resend_email.py — standalone Resend integration test.

Runs WITHOUT the backend package installed. Drop it at the repo root and run:

    # Install the two deps if not already present:
    pip install resend python-dotenv

    # Run (replace the address with a real inbox you control):
    python test_resend_email.py your@email.com

    # Optional env overrides:
    RESEND_API_KEY=re_xxx python test_resend_email.py your@email.com

Exits 0 on success, 1 on failure.
"""

import asyncio
import logging
import os
import sys

# ── Load .env before anything else ────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # rely on shell env if python-dotenv is not installed

# ── Visible logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("resend_test")

# ── Validate env before importing resend ──────────────────────────────────────
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
SENDER = os.getenv("RESEND_FROM_EMAIL", "Himaya AI <onboarding@resend.dev>")
TIMEOUT_S = 15.0

if not RESEND_API_KEY:
    log.error("RESEND_API_KEY is not set. Export it or add it to your .env file.")
    sys.exit(1)

try:
    import resend
except ImportError:
    log.error("resend package not installed. Run: pip install resend")
    sys.exit(1)

resend.api_key = RESEND_API_KEY


# ── Blocking send (runs in a thread via asyncio.to_thread) ────────────────────

def _send_blocking(to: str, subject: str, html: str) -> str:
    """Return the Resend email id on success, raise on failure."""
    params: resend.Emails.SendParams = {
        "from":    SENDER,
        "to":      [to],
        "subject": subject,
        "html":    html,
    }
    result = resend.Emails.send(params)
    email_id = (
        result.get("id") if isinstance(result, dict)
        else getattr(result, "id", "unknown")
    )
    return email_id


async def _send(to: str, subject: str, html: str) -> str:
    """Async wrapper with a hard timeout so the test never hangs."""
    return await asyncio.wait_for(
        asyncio.to_thread(_send_blocking, to, subject, html),
        timeout=TIMEOUT_S,
    )


# ── Test cases ─────────────────────────────────────────────────────────────────

OTP_HTML = """<!DOCTYPE html>
<html lang="en">
<body style="font-family:Arial,sans-serif;padding:32px;background:#f8fafc;margin:0;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;
              padding:32px;border:1px solid #e2e8f0;">
    <h2 style="color:#059669;margin:0 0 8px;">Verify your email</h2>
    <p style="color:#475569;margin:0 0 24px;">Your Himaya test OTP:</p>
    <div style="text-align:center;padding:20px;background:#f0fdf4;border-radius:10px;
                border:1px solid #bbf7d0;">
      <span style="font-size:40px;font-weight:700;letter-spacing:10px;
                   color:#065f46;font-family:monospace;">847291</span>
    </div>
    <p style="color:#64748b;font-size:13px;margin-top:20px;">
      This is a test email from test_resend_email.py.
    </p>
  </div>
</body>
</html>"""

RESET_HTML = """<!DOCTYPE html>
<html lang="en">
<body style="font-family:Arial,sans-serif;padding:32px;background:#f8fafc;margin:0;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;
              padding:32px;border:1px solid #e2e8f0;">
    <h2 style="color:#0f172a;margin:0 0 8px;">Reset your password</h2>
    <p style="color:#475569;margin:0 0 24px;">Your Himaya test reset code:</p>
    <div style="text-align:center;padding:20px;background:#f8fafc;border-radius:10px;
                border:1px solid #e2e8f0;">
      <span style="font-size:40px;font-weight:700;letter-spacing:10px;
                   color:#1e293b;font-family:monospace;">563018</span>
    </div>
    <p style="color:#64748b;font-size:13px;margin-top:20px;">
      This is a test email from test_resend_email.py.
    </p>
  </div>
</body>
</html>"""


async def run(to: str) -> bool:
    passed = True

    for label, subject, html in [
        ("OTP email",           "Himaya — Test OTP code",           OTP_HTML),
        ("Password reset email","Himaya — Test password reset code", RESET_HTML),
    ]:
        log.info("=" * 56)
        log.info("TEST: %s  →  %s", label, to)
        log.info("=" * 56)
        try:
            email_id = await _send(to, subject, html)
            log.info("PASSED ✓  resend_id=%s", email_id)
        except asyncio.TimeoutError:
            log.error("FAILED ✗  Resend API did not respond within %.0fs", TIMEOUT_S)
            passed = False
        except Exception as exc:
            log.error("FAILED ✗  %s: %s", type(exc).__name__, exc)
            passed = False

        await asyncio.sleep(1)

    return passed


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python test_resend_email.py <recipient@email.com>")
        sys.exit(1)

    to = sys.argv[1].strip()

    log.info("Himaya Resend integration test")
    log.info("  RESEND_API_KEY   : set (%s...)", RESEND_API_KEY[:8])
    log.info("  RESEND_FROM_EMAIL: %s", SENDER)
    log.info("  recipient        : %s", to)
    log.info("  timeout          : %.0fs per send", TIMEOUT_S)

    ok = asyncio.run(run(to))

    log.info("")
    if ok:
        log.info("All tests PASSED.  Check %s for 2 test emails.", to)
        sys.exit(0)
    else:
        log.error("One or more tests FAILED — see errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
