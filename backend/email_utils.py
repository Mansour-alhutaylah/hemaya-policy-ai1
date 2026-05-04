import asyncio
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import partial


def _blocking_send(to_email: str, subject: str, html: str) -> None:
    """Send an email synchronously via STARTTLS (port 587).
    Runs in a thread — do not call directly from async code."""
    username = os.environ.get("MAIL_USERNAME", "")
    password = os.environ.get("MAIL_PASSWORD", "")
    host = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    port = int(os.environ.get("MAIL_PORT", 587))
    sender = os.environ.get("MAIL_FROM") or username

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(host, port, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(username, password)
        server.sendmail(sender, [to_email], msg.as_string())


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
