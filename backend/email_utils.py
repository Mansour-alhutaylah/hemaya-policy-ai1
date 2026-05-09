"""
email_utils.py

Email delivery via the Resend API (https://resend.com).

Replaces Gmail/SMTP which fails on Render:
  [Errno 101] Network is unreachable  (outbound port 587 blocked)

Public API — identical signatures so main.py requires zero changes:
    send_otp_email(email, otp)            → async, raises EmailDeliveryError
    send_password_reset_email(email, otp) → async, raises EmailDeliveryError
    EmailDeliveryError                    → .public_message is user-safe

Root causes fixed in this version
──────────────────────────────────
1. asyncio.get_event_loop() replaced with asyncio.to_thread()
   get_event_loop() is deprecated in Python 3.10+ inside async contexts and
   unreliable in Python 3.12+.  asyncio.to_thread() dispatches to the default
   ThreadPoolExecutor without touching the event loop object directly.

2. 20-second hard timeout via asyncio.wait_for()
   resend.Emails.send() uses httpx internally with no timeout configured by
   default.  Without wait_for(), a slow/unreachable api.resend.com would
   block the executor thread indefinitely and cause the FastAPI handler to
   hang forever → signup stuck on "Creating...", forgot-password never returns.

3. Pre-send + post-send logging
   Log lines before and after the Resend API call make Render logs actionable:
   you can now tell whether the call never started, started and timed out, or
   succeeded.

Environment variables required:
    RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx   ← set in Render dashboard
    RESEND_FROM_EMAIL=Hemaya AI <onboarding@resend.dev>  ← optional override
"""

import asyncio
import logging
import os

import resend

logger = logging.getLogger(__name__)

# ── Sender (read once at startup, after load_dotenv() has run in main.py) ─────
_SENDER = os.getenv("RESEND_FROM_EMAIL", "Hemaya AI <onboarding@resend.dev>")

# Hard timeout for one Resend API call (seconds).
# Generous enough for slow networks; short enough that the handler returns
# before the frontend's own 12-second fetch timeout fires.
_SEND_TIMEOUT_S = 15.0


# ── Public exception — keep identical so callers never change ─────────────────

class EmailDeliveryError(Exception):
    """
    Raised when Resend cannot deliver the email.

    Attributes
    ----------
    public_message : str
        Safe to return in an HTTP response body (no internal detail).
    """
    def __init__(self, message: str, public_message: str = None):
        super().__init__(message)
        self.public_message = public_message or (
            "We couldn't send the verification email right now. "
            "Please try again in a moment."
        )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _resolve_api_key() -> str:
    """Read RESEND_API_KEY from the environment. Raises EmailDeliveryError if absent."""
    key = os.getenv("RESEND_API_KEY", "").strip()
    if not key:
        logger.error("[email] RESEND_API_KEY is not set in the environment")
        raise EmailDeliveryError(
            "RESEND_API_KEY is not configured.",
            public_message=(
                "Email is not configured on the server. "
                "Please contact an administrator."
            ),
        )
    return key


def _classify_resend_error(exc: Exception) -> str:
    """Map a Resend SDK exception to a user-facing message string."""
    low = str(exc).lower()
    if any(k in low for k in ("api_key", "unauthorized", "403", "401", "authentication")):
        return (
            "Email service authentication failed. "
            "Please contact an administrator."
        )
    if any(k in low for k in ("invalid_to", "invalid email", "invalid_from", "invalid address")):
        return "The email address appears to be invalid."
    if any(k in low for k in ("rate", "429", "too many")):
        return (
            "Too many emails have been sent recently. "
            "Please wait a moment and try again."
        )
    if any(k in low for k in ("timeout", "timed out", "network", "connection")):
        return (
            "The email service is temporarily unreachable. "
            "Please try again in a moment."
        )
    return (
        "We couldn't send the verification email right now. "
        "Please try again in a moment."
    )


def _blocking_send(to_email: str, subject: str, html: str) -> None:
    """
    Synchronous Resend API call.  ALWAYS runs inside a thread (never directly
    in the event loop) so it cannot block FastAPI's async handling.
    """
    api_key = _resolve_api_key()
    resend.api_key = api_key

    params: resend.Emails.SendParams = {
        "from":    _SENDER,
        "to":      [to_email],
        "subject": subject,
        "html":    html,
    }

    logger.info("[email] → Calling Resend API  to=%s  subject=%r", to_email, subject)

    try:
        result   = resend.Emails.send(params)
        email_id = (
            result.get("id") if isinstance(result, dict)
            else getattr(result, "id", "unknown")
        )
        logger.info("[email] ✓ Resend accepted  to=%s  id=%s", to_email, email_id)

    except Exception as exc:
        err_type = type(exc).__name__
        log_msg  = f"Resend send failed ({err_type}) to={to_email!r}: {exc}"
        logger.error("[email] ✗ %s", log_msg)
        raise EmailDeliveryError(
            log_msg,
            public_message=_classify_resend_error(exc),
        ) from exc


async def _send(to_email: str, subject: str, html: str) -> None:
    """
    Async wrapper:
      • dispatches _blocking_send to a thread via asyncio.to_thread()
        (fixes the deprecated asyncio.get_event_loop() pattern)
      • enforces a hard timeout so the handler never hangs forever
        (fixes the "signup stuck on Creating..." symptom)
    """
    logger.info("[email] Dispatching email  to=%s", to_email)
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_blocking_send, to_email, subject, html),
            timeout=_SEND_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        msg = (
            f"Resend API did not respond within {_SEND_TIMEOUT_S}s "
            f"(to={to_email!r})"
        )
        logger.error("[email] TIMEOUT: %s", msg)
        raise EmailDeliveryError(
            msg,
            public_message=(
                "The email service is not responding. "
                "Please try again in a moment."
            ),
        )
    # EmailDeliveryError propagates unchanged to the caller.


# ── Public API — signatures frozen; main.py must not be modified ──────────────

async def send_otp_email(email: str, otp: str) -> None:
    """Send a 6-digit OTP verification code to *email*."""
    logger.info("[email] send_otp_email  to=%s  otp=***%s", email, otp[-2:])
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Arial,sans-serif;padding:32px;background:#f8fafc;margin:0;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;
              padding:32px;border:1px solid #e2e8f0;">

    <!-- Brand -->
    <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      <tr>
        <td style="width:40px;height:40px;border-radius:8px;
                   background:linear-gradient(135deg,#34d399,#0d9488);
                   text-align:center;vertical-align:middle;font-size:20px;">
          &#x1F6E1;
        </td>
        <td style="padding-left:10px;vertical-align:middle;">
          <p style="margin:0;font-size:13px;font-weight:600;color:#0f172a;">Himaya</p>
          <p style="margin:0;font-size:10px;letter-spacing:.1em;
                    text-transform:uppercase;color:#94a3b8;">AI Compliance</p>
        </td>
      </tr>
    </table>

    <h2 style="color:#059669;margin:0 0 8px;font-size:22px;">Verify your email</h2>
    <p style="color:#475569;margin:0 0 24px;font-size:15px;">
      Use the code below to verify your Himaya account:
    </p>

    <div style="text-align:center;margin:24px 0;padding:20px;
                background:#f0fdf4;border-radius:10px;border:1px solid #bbf7d0;">
      <span style="font-size:40px;font-weight:700;letter-spacing:10px;
                   color:#065f46;font-family:monospace;">
        {otp}
      </span>
    </div>

    <p style="color:#64748b;font-size:14px;margin:0 0 8px;">
      This code expires in <strong>10 minutes</strong>. Do not share it with anyone.
    </p>

    <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">

    <p style="color:#94a3b8;font-size:12px;margin:0;">
      If you did not create a Himaya account you can safely ignore this email.
    </p>
  </div>
</body>
</html>"""
    await _send(email, "Your Himaya Verification Code", html)


async def send_password_reset_email(email: str, otp: str) -> None:
    """Send a 6-digit password-reset OTP to *email*."""
    logger.info("[email] send_password_reset_email  to=%s  otp=***%s", email, otp[-2:])
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Arial,sans-serif;padding:32px;background:#f8fafc;margin:0;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;
              padding:32px;border:1px solid #e2e8f0;">

    <!-- Brand -->
    <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      <tr>
        <td style="width:40px;height:40px;border-radius:8px;
                   background:linear-gradient(135deg,#34d399,#0d9488);
                   text-align:center;vertical-align:middle;font-size:20px;">
          &#x1F6E1;
        </td>
        <td style="padding-left:10px;vertical-align:middle;">
          <p style="margin:0;font-size:13px;font-weight:600;color:#0f172a;">Himaya</p>
          <p style="margin:0;font-size:10px;letter-spacing:.1em;
                    text-transform:uppercase;color:#94a3b8;">AI Compliance</p>
        </td>
      </tr>
    </table>

    <h2 style="color:#0f172a;margin:0 0 8px;font-size:22px;">Reset your password</h2>
    <p style="color:#475569;margin:0 0 24px;font-size:15px;">
      We received a request to reset your Himaya password. Use the code below:
    </p>

    <div style="text-align:center;margin:24px 0;padding:20px;
                background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;">
      <span style="font-size:40px;font-weight:700;letter-spacing:10px;
                   color:#1e293b;font-family:monospace;">
        {otp}
      </span>
    </div>

    <p style="color:#64748b;font-size:14px;margin:0 0 8px;">
      This code expires in <strong>10 minutes</strong>. Do not share it with anyone.
    </p>

    <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">

    <p style="color:#94a3b8;font-size:12px;margin:0;">
      If you did not request a password reset you can safely ignore this email.
      Your password will not change.
    </p>
  </div>
</body>
</html>"""
    await _send(email, "Reset your Himaya password", html)
