"""Email delivery through Resend's HTTP API (no SDK, just httpx)."""

from __future__ import annotations

from typing import Protocol

import httpx

from .config import Settings

RESEND_URL = "https://api.resend.com/emails"


class EmailError(RuntimeError):
    """Raised when the provider rejects or cannot deliver a message."""


class Emailer(Protocol):
    configured: bool

    def send(self, *, subject: str, html: str, text: str, idempotency_key: str) -> str: ...


class DisabledEmailer:
    configured = False

    def send(self, *, subject: str, html: str, text: str, idempotency_key: str) -> str:
        raise EmailError("Email is not configured (set RESEND_API_KEY and REPORT_TO_EMAIL).")


class ResendEmailer:
    configured = True

    def __init__(
        self,
        api_key: str,
        sender: str,
        recipient: str,
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._sender = sender
        self._recipient = recipient
        self._client = client
        self._timeout = timeout

    def send(self, *, subject: str, html: str, text: str, idempotency_key: str) -> str:
        payload = {
            "from": self._sender,
            "to": [self._recipient],
            "subject": subject,
            "html": html,
            "text": text,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Idempotency-Key": idempotency_key[:250],
        }
        try:
            if self._client is not None:
                response = self._client.post(
                    RESEND_URL, json=payload, headers=headers, timeout=self._timeout
                )
            else:
                with httpx.Client() as client:
                    response = client.post(
                        RESEND_URL, json=payload, headers=headers, timeout=self._timeout
                    )
        except httpx.HTTPError as exc:
            raise EmailError(f"Could not reach Resend ({type(exc).__name__}).") from exc
        if response.status_code >= 300:
            raise EmailError(f"Resend rejected the message (HTTP {response.status_code}).")
        return str(response.json().get("id", ""))


def build_emailer(settings: Settings) -> Emailer:
    if settings.resend_api_key and settings.report_to_email:
        return ResendEmailer(
            settings.resend_api_key, settings.report_from_email, settings.report_to_email
        )
    return DisabledEmailer()
