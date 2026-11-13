"""Outgoing e-mail (password reset). Optional: without SMTP settings nothing is sent and the caller is told."""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core import config

log = logging.getLogger("mail")


def configured() -> bool:
    return bool(config.SMTP_HOST and config.MAIL_FROM)


def _send(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = config.MAIL_FROM, to, subject
    msg.set_content(body)
    context = ssl.create_default_context()
    if config.SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=20, context=context)
    else:
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20)
    with server:
        if config.SMTP_PORT != 465 and config.SMTP_STARTTLS:
            server.starttls(context=context)
        if config.SMTP_USER:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)


async def send(to: str, subject: str, body: str) -> bool:
    """True when the message was handed to the mail server. Failures are logged without the recipient or body."""
    if not configured():
        return False
    try:
        await asyncio.to_thread(_send, to, subject, body)
        return True
    except Exception as e:   # noqa: BLE001 - mail must never break a request
        log.warning("could not send e-mail (%s)", type(e).__name__)
        return False
