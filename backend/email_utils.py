import asyncio
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import partial


# ── Custom error so callers can translate it into a user-facing message ──
class EmailDeliveryError(Exception):
    """Raised when the SMTP send fails. The .public_message attribute is
    safe to surface to end users; the str(exc) is for server logs only."""
    def __init__(self, message: str, public_message: str = None):
        super().__init__(message)
        self.public_message = public_message or (
            "We couldn't send the verification email right now. "
            "Please try again in a moment."
        )


def _read_smtp_config():
    """Read + sanitize SMTP env vars.

    Notable: Gmail App Passwords are *displayed* with spaces in the
    Google UI ("abcd efgh ijkl mnop"). When users paste them verbatim
    into an .env file, smtplib rejects them with 535. Strip aggressively.
    """
    raw_user = os.environ.get("MAIL_USERNAME", "") or ""
    raw_pass = os.environ.get("MAIL_PASSWORD", "") or ""
    raw_host = os.environ.get("MAIL_SERVER", "smtp.gmail.com") or "smtp.gmail.com"
    raw_from = os.environ.get("MAIL_FROM", "") or ""
    raw_port = os.environ.get("MAIL_PORT", "587") or "587"

    # Trim whitespace + zero-width chars on the address fields.
    username = raw_user.strip().strip('"').strip("'")
    host     = raw_host.strip().strip('"').strip("'")
    sender   = (raw_from.strip().strip('"').strip("'")) or username

    # App passwords: strip ALL whitespace inside the value too.
    password = "".join(raw_pass.split())

    try:
        port = int(str(raw_port).strip())
    except (TypeError, ValueError):
        port = 587

    return {
        "username": username,
        "password": password,
        "host": host,
        "port": port,
        "sender": sender,
    }


def _validate_config(cfg):
    """Raise EmailDeliveryError early if config is obviously wrong."""
    if not cfg["username"] or not cfg["password"]:
        raise EmailDeliveryError(
            "MAIL_USERNAME or MAIL_PASSWORD is missing from the environment.",
            public_message=(
                "Email is not configured on the server. "
                "Please contact an administrator."
            ),
        )
    if "@" not in cfg["username"]:
        raise EmailDeliveryError(
            f"MAIL_USERNAME does not look like an email address: {cfg['username']!r}.",
            public_message=(
                "Email service configuration is invalid. "
                "Please contact an administrator."
            ),
        )
    if not cfg["host"]:
        raise EmailDeliveryError(
            "MAIL_SERVER is empty.",
            public_message=(
                "Email service configuration is invalid. "
                "Please contact an administrator."
            ),
        )


def _send_starttls(cfg, msg, to_email):
    """Send via STARTTLS on port 587 (Gmail default)."""
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        server.login(cfg["username"], cfg["password"])
        server.sendmail(cfg["sender"], [to_email], msg.as_string())


def _send_ssl(cfg, msg, to_email):
    """Send via implicit SSL on port 465 (SMTPS)."""
    with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20,
                          context=ssl.create_default_context()) as server:
        server.ehlo()
        server.login(cfg["username"], cfg["password"])
        server.sendmail(cfg["sender"], [to_email], msg.as_string())


def _blocking_send(to_email: str, subject: str, html: str) -> None:
    """Synchronously send an email. Runs in a thread — never call from async."""
    cfg = _read_smtp_config()
    _validate_config(cfg)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = cfg["sender"]
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        if cfg["port"] == 465:
            _send_ssl(cfg, msg, to_email)
        else:
            _send_starttls(cfg, msg, to_email)
    except smtplib.SMTPAuthenticationError as e:
        # 535 from Gmail → almost always App Password issue.
        # Log the precise error server-side; surface a friendly one to the UI.
        is_gmail = "gmail.com" in cfg["host"].lower()
        log_msg = (
            f"SMTP auth failed for {cfg['username']!r} on "
            f"{cfg['host']}:{cfg['port']} → {e.smtp_code} {e.smtp_error!r}"
        )
        print(f"[email] {log_msg}")
        if is_gmail:
            public = (
                "Email service authentication failed. "
                "If this is a Gmail account, the MAIL_PASSWORD must be a "
                "16-character Google App Password (with the spaces removed) "
                "and the account must have 2-Step Verification enabled."
            )
        else:
            public = (
                "Email service authentication failed. "
                "Please contact an administrator."
            )
        raise EmailDeliveryError(log_msg, public_message=public) from e
    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected,
            ConnectionError, OSError) as e:
        log_msg = f"SMTP connection error to {cfg['host']}:{cfg['port']} → {e}"
        print(f"[email] {log_msg}")
        raise EmailDeliveryError(
            log_msg,
            public_message=(
                "Could not reach the email server. "
                "Please try again in a moment."
            ),
        ) from e
    except smtplib.SMTPRecipientsRefused as e:
        log_msg = f"SMTP recipient refused for {to_email}: {e}"
        print(f"[email] {log_msg}")
        raise EmailDeliveryError(
            log_msg,
            public_message="The email address was rejected by the mail server.",
        ) from e
    except Exception as e:
        log_msg = f"SMTP send failed: {type(e).__name__}: {e}"
        print(f"[email] {log_msg}")
        raise EmailDeliveryError(log_msg) from e


async def _send(to_email: str, subject: str, html: str) -> None:
    """Offload the blocking SMTP call to a thread so FastAPI stays non-blocking."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, partial(_blocking_send, to_email, subject, html))


async def send_otp_email(email: str, otp: str) -> None:
    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:sans-serif;padding:32px;background:#f8fafc;">
      <div style="max-width:480px;margin:0 auto;background:white;border-radius:12px;
                  padding:32px;border:1px solid #e2e8f0;">
        <h2 style="color:#059669;margin-top:0;">Verify your Himaya account</h2>
        <p style="color:#475569;">Use the code below to verify your email address:</p>
        <div style="text-align:center;margin:24px 0;">
          <span style="font-size:36px;font-weight:700;letter-spacing:8px;color:#1e293b;">
            {otp}
          </span>
        </div>
        <p style="color:#64748b;font-size:14px;">
          This code expires in <strong>10 minutes</strong>. Do not share it with anyone.
        </p>
        <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">
        <p style="color:#94a3b8;font-size:12px;">
          If you did not create a Himaya account, you can safely ignore this email.
        </p>
      </div>
    </body>
    </html>
    """
    await _send(email, "Your Himaya Verification Code", html)


async def send_password_reset_email(email: str, otp: str) -> None:
    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:sans-serif;padding:32px;background:#f8fafc;">
      <div style="max-width:480px;margin:0 auto;background:white;border-radius:12px;
                  padding:32px;border:1px solid #e2e8f0;">
        <h2 style="color:#0f172a;margin-top:0;">Reset your Himaya password</h2>
        <p style="color:#475569;">
          We received a request to reset your password. Use the code below:
        </p>
        <div style="text-align:center;margin:24px 0;">
          <span style="font-size:36px;font-weight:700;letter-spacing:8px;color:#1e293b;">
            {otp}
          </span>
        </div>
        <p style="color:#64748b;font-size:14px;">
          This code expires in <strong>10 minutes</strong>. Do not share it with anyone.
        </p>
        <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">
        <p style="color:#94a3b8;font-size:12px;">
          If you did not request a password reset, you can safely ignore this email.
          Your password will not change.
        </p>
      </div>
    </body>
    </html>
    """
    await _send(email, "Reset your Himaya password", html)
