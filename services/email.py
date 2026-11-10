"""Plain SMTP email, configured entirely from the environment:

  SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM,
  SMTP_STARTTLS (true) — or SMTP_SSL=true for port 465.

Unconfigured (no SMTP_HOST) means email is simply off: send_email returns
False and nothing else changes.
"""
from __future__ import annotations

import asyncio
import os
import smtplib
from email.message import EmailMessage

from loguru import logger


def email_enabled() -> bool:
    return bool(os.getenv("SMTP_HOST"))


def _send_sync(to: list[str], subject: str, body: str) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "465" if os.getenv("SMTP_SSL", "").lower() == "true" else "587"))
    sender = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER", "")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = sender  # recipients go in Bcc so admins don't see each other's addresses
    msg["Bcc"] = ", ".join(to)
    msg.set_content(body)
    use_ssl = os.getenv("SMTP_SSL", "").lower() == "true"
    with (smtplib.SMTP_SSL(host, port, timeout=30) if use_ssl else smtplib.SMTP(host, port, timeout=30)) as smtp:
        if not use_ssl and os.getenv("SMTP_STARTTLS", "true").lower() != "false":
            smtp.starttls()
        if os.getenv("SMTP_USER"):
            smtp.login(os.environ["SMTP_USER"], os.getenv("SMTP_PASSWORD", ""))
        smtp.send_message(msg)


async def send_email(to: list[str], subject: str, body: str) -> bool:
    """True if sent. Never raises: a mail failure is logged, not fatal."""
    to = [t for t in to if t]
    if not email_enabled() or not to:
        return False
    try:
        await asyncio.to_thread(_send_sync, to, subject, body)
        return True
    except Exception:
        logger.exception(f"Could not send email {subject!r}")
        return False
