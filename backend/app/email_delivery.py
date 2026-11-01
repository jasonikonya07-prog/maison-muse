import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Literal

import httpx


logger = logging.getLogger(__name__)
EmailDeliveryStatus = Literal["SENT", "NOT_CONFIGURED", "FAILED"]


def send_email(recipient: str, subject: str, text: str) -> EmailDeliveryStatus:
    resend_api_key = os.getenv("RESEND_API_KEY", "").strip()
    if resend_api_key:
        sender = os.getenv("RESEND_FROM_EMAIL", "").strip()
        if not sender:
            logger.warning("Resend email delivery requires RESEND_FROM_EMAIL.")
            return "NOT_CONFIGURED"
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": sender,
                    "to": [recipient],
                    "subject": subject,
                    "text": text,
                },
                timeout=10.0,
            )
        except httpx.RequestError:
            logger.exception("Could not reach the Resend email API.")
            return "FAILED"
        if response.status_code >= 400:
            logger.error(
                "Resend rejected an email request with HTTP status %s.",
                response.status_code,
            )
            return "FAILED"
        return "SENT"

    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", os.getenv("SMTP_USERNAME", "")).strip()
    if not host or not sender:
        logger.warning("Email delivery is not configured.")
        return "NOT_CONFIGURED"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(text)
    try:
        with smtplib.SMTP(
            host, int(os.getenv("SMTP_PORT", "587")), timeout=10
        ) as client:
            if os.getenv("SMTP_STARTTLS", "true").strip().casefold() == "true":
                client.starttls()
            username = os.getenv("SMTP_USERNAME", "").strip()
            if username:
                client.login(username, os.getenv("SMTP_PASSWORD", ""))
            if client.send_message(message):
                logger.error("SMTP refused the email recipient.")
                return "FAILED"
    except (OSError, smtplib.SMTPException, ValueError):
        logger.exception("Could not send email using the configured SMTP provider.")
        return "FAILED"
    return "SENT"
