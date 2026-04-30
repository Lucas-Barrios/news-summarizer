"""Email delivery providers for daily digests."""
import smtplib
from email.message import EmailMessage

import requests

from config import Config


class EmailDeliveryError(Exception):
    """Raised when email delivery fails."""


class SMTPEmailSender:
    """Send email through SMTP."""

    provider_name = "smtp"

    def send(self, to_email, subject, html_body, text_body):
        """Send an email through SMTP."""
        if not Config.DIGEST_FROM_EMAIL:
            raise EmailDeliveryError("DIGEST_FROM_EMAIL is required")
        if not Config.SMTP_HOST:
            raise EmailDeliveryError("SMTP_HOST is required")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = Config.DIGEST_FROM_EMAIL
        message["To"] = to_email
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")

        try:
            with smtplib.SMTP(
                Config.SMTP_HOST,
                Config.SMTP_PORT,
                timeout=Config.REQUEST_TIMEOUT,
            ) as smtp:
                if Config.SMTP_USE_TLS:
                    smtp.starttls()
                if Config.SMTP_USERNAME and Config.SMTP_PASSWORD:
                    smtp.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
                smtp.send_message(message)
        except Exception as e:
            raise EmailDeliveryError(str(e)) from e


class SendGridEmailSender:
    """Send email through SendGrid's HTTP API."""

    provider_name = "sendgrid"

    def send(self, to_email, subject, html_body, text_body):
        """Send an email through SendGrid API."""
        if not Config.SENDGRID_API_KEY:
            raise EmailDeliveryError("SENDGRID_API_KEY is required")
        if not Config.DIGEST_FROM_EMAIL:
            raise EmailDeliveryError("DIGEST_FROM_EMAIL is required")

        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": Config.DIGEST_FROM_EMAIL},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text_body},
                {"type": "text/html", "value": html_body},
            ],
        }

        try:
            response = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {Config.SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=Config.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except Exception as e:
            raise EmailDeliveryError(str(e)) from e


def get_email_sender(provider=None):
    """Return the configured email sender."""
    provider = (provider or Config.EMAIL_PROVIDER).lower()

    if provider == "sendgrid":
        return SendGridEmailSender()
    if provider == "smtp":
        return SMTPEmailSender()

    raise EmailDeliveryError(f"Unsupported email provider: {provider}")
