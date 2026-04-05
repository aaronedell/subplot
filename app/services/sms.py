"""SMS delivery: abstract base, Twilio implementation, and console fallback."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SMSService(ABC):
    """Abstract SMS service interface."""

    @abstractmethod
    def send_message(self, to: str, body: str) -> None:
        """Send an SMS message to *to* (E.164 format) with *body* text."""

    @abstractmethod
    def send_verification_code(self, to: str, code: str) -> None:
        """Send a verification code SMS."""


class TwilioSMS(SMSService):
    """Twilio implementation of SMSService."""

    def __init__(self, account_sid: str, auth_token: str, from_number: str) -> None:
        from twilio.rest import Client  # type: ignore[import]
        self._client = Client(account_sid, auth_token)
        self._from = from_number

    def send_message(self, to: str, body: str) -> None:
        msg = self._client.messages.create(body=body, from_=self._from, to=to)
        logger.info("Twilio SMS sent to %s, sid=%s", to, msg.sid)

    def send_verification_code(self, to: str, code: str) -> None:
        body = f"Your Subplot verification code is: {code}"
        self.send_message(to, body)


class ConsoleSMS(SMSService):
    """Development fallback: print SMS to stdout instead of sending."""

    def send_message(self, to: str, body: str) -> None:
        print(f"[SMS to {to}]\n{body}\n{'─' * 40}")

    def send_verification_code(self, to: str, code: str) -> None:
        self.send_message(to, f"Your Subplot verification code is: {code}")


def get_sms_service() -> SMSService:
    """Factory: return Twilio if credentials are configured, else ConsoleSMS."""
    from app.config import settings

    if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_PHONE_NUMBER:
        return TwilioSMS(
            account_sid=settings.TWILIO_ACCOUNT_SID,
            auth_token=settings.TWILIO_AUTH_TOKEN,
            from_number=settings.TWILIO_PHONE_NUMBER,
        )
    logger.info("Twilio not configured — using ConsoleSMS (dev mode)")
    return ConsoleSMS()
