"""Outbound email: one small interface, two providers, HTML from Jinja2 templates.

Routes never build HTML or talk HTTP. They queue one of the ``send_*``
coroutines below with FastAPI ``BackgroundTasks``.

Failures are loud on purpose. A provider error is logged with its traceback,
the email is stored in ``failed_emails`` for an admin to retry or discard, and
the error is re-raised. The only quiet path is "no provider configured":
the console adapter is used and says so.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.config import settings
from app.database import SessionLocal
from app.models.failed_email import FailedEmail

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
BREVO_TIMEOUT_SECONDS = 10
CONSOLE_PREVIEW_CHARS = 300

# autoescape: names, titles and messages come from users and must never become markup.
# StrictUndefined: a template variable we forgot to pass raises instead of rendering blank.
_templates = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent.parent / "templates" / "email"),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
)


@dataclass(frozen=True)
class EmailMessage:
    to_email: str
    to_name: str | None
    subject: str
    html: str
    reply_to_email: str | None = None
    reply_to_name: str | None = None


class EmailDeliveryError(Exception):
    """The provider refused the email or could not be reached.

    The text never contains the recipient or the message, so it is safe to log and store.
    """


class EmailAdapter(ABC):
    @abstractmethod
    async def send(self, message: EmailMessage) -> None:
        """Deliver the message or raise."""


class ConsoleEmailAdapter(EmailAdapter):
    """Writes the email to the log. For local development and for before an account exists."""

    async def send(self, message: EmailMessage) -> None:
        logger.info(
            "EMAIL (console) to=%s subject=%r body=%s",
            message.to_email,
            message.subject,
            message.html[:CONSOLE_PREVIEW_CHARS],
        )


class BrevoEmailAdapter(EmailAdapter):
    """Sends through Brevo's HTTPS API (port 443), so it works on Cloud Run with no SMTP."""

    def __init__(self, api_key: str, sender_email: str, sender_name: str):
        self._api_key = api_key
        self._sender = {"email": sender_email, "name": sender_name}

    async def send(self, message: EmailMessage) -> None:
        recipient = {"email": message.to_email}
        if message.to_name:
            recipient["name"] = message.to_name

        payload = {
            "sender": self._sender,
            "to": [recipient],
            "subject": message.subject,
            "htmlContent": message.html,
        }

        if message.reply_to_email:
            payload["replyTo"] = {"email": message.reply_to_email}
            if message.reply_to_name:
                payload["replyTo"]["name"] = message.reply_to_name

        try:
            async with httpx.AsyncClient(timeout=BREVO_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    BREVO_API_URL,
                    json=payload,
                    headers={"api-key": self._api_key, "accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise EmailDeliveryError(
                f"Could not reach Brevo ({type(exc).__name__})"
            ) from exc

        if response.is_error:
            try:
                code = response.json().get("code")
            except ValueError:
                code = None
            raise EmailDeliveryError(
                f"Brevo rejected the email (HTTP {response.status_code}, code={code})"
            )


def get_adapter() -> EmailAdapter:
    if settings.email_provider == "brevo":
        if settings.email_api_key and settings.sender_email:
            return BrevoEmailAdapter(
                settings.email_api_key,
                settings.sender_email,
                settings.app_name,
            )

        logger.warning(
            "EMAIL_PROVIDER=brevo but EMAIL_API_KEY or SENDER_EMAIL is not set; "
            "emails are only being printed to the log."
        )

    return ConsoleEmailAdapter()


def _store_failure(message: EmailMessage, error: str) -> None:
    db = SessionLocal()

    try:
        now = datetime.utcnow()
        db.add(
            FailedEmail(
                to_email=message.to_email,
                to_name=message.to_name,
                subject=message.subject[:200],
                html=message.html,
                reply_to_email=message.reply_to_email,
                reply_to_name=message.reply_to_name,
                error=error[:300],
                attempts=1,
                created_at=now,
                last_attempt_at=now,
            )
        )
        db.commit()
    finally:
        db.close()


async def deliver(message: EmailMessage) -> None:
    try:
        await get_adapter().send(message)
    except Exception as exc:
        logger.exception("Email delivery failed; stored for an admin to retry or discard.")
        await asyncio.to_thread(
            _store_failure,
            message,
            f"{type(exc).__name__}: {exc}",
        )
        raise


async def send_welcome(name: str, email: str) -> None:
    await deliver(
        EmailMessage(
            to_email=email,
            to_name=name,
            subject="Welcome to InfyExchange",
            html=_templates.get_template("welcome.html").render(name=name),
        )
    )


async def send_enquiry_alert(
    *,
    listing_title: str,
    owner_name: str,
    sender_name: str,
    sender_email: str,
    message: str | None,
) -> None:
    if not settings.admin_email:
        logger.warning("Enquiry alert not sent: ADMIN_EMAIL is not set.")
        return

    await deliver(
        EmailMessage(
            to_email=settings.admin_email,
            to_name=None,
            subject=f"New enquiry: {listing_title}"[:200],
            html=_templates.get_template("enquiry_admin.html").render(
                listing_title=listing_title,
                owner_name=owner_name,
                sender_name=sender_name,
                sender_email=sender_email,
                message=message,
            ),
            # Replying to the alert reaches the person who enquired.
            reply_to_email=sender_email,
            reply_to_name=sender_name,
        )
    )
