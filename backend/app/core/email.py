"""Minimal SMTP helper (kept for operator notifications; unused by the call path)."""

import smtplib
from email.message import EmailMessage

from app.core.config import get_settings


def smtp_configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host and settings.smtp_username and settings.smtp_password)


def send_email(*, to: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not smtp_configured():
        raise RuntimeError("SMTP is not configured")
    message = EmailMessage()
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email or settings.smtp_username}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=12) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
