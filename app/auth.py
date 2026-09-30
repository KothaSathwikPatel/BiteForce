"""Optional Google sign-in. Signed-in reporters get a stronger identity than an anonymous device.

Flow: the browser gets a Google ID token, we verify it with Google, then issue our own short
signed session token. Only a salted hash of Google's stable user id is stored, never the email.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

import httpx

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
SESSION_TTL = timedelta(days=30)


class AuthError(Exception):
    """The credential or session token is missing, expired or invalid."""


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    name: str


class GoogleVerifier(Protocol):
    def verify(self, credential: str) -> GoogleIdentity: ...


class TokenInfoVerifier:
    """Verifies a Google ID token through Google's own tokeninfo endpoint."""

    def __init__(self, client_id: str, client: httpx.Client | None = None, timeout: float = 6.0) -> None:
        self._client_id = client_id
        self._client = client
        self._timeout = timeout

    def _get(self, credential: str) -> httpx.Response:
        params = {"id_token": credential}
        if self._client is not None:
            return self._client.get(TOKENINFO_URL, params=params, timeout=self._timeout)
        with httpx.Client() as client:
            return client.get(TOKENINFO_URL, params=params, timeout=self._timeout)

    def verify(self, credential: str) -> GoogleIdentity:
        if not credential or len(credential) > 4096:
            raise AuthError("Missing Google credential.")
        try:
            response = self._get(credential)
        except httpx.HTTPError as exc:
            raise AuthError("Could not reach Google to verify the sign-in.") from exc
        if response.status_code != 200:
            raise AuthError("Google rejected this sign-in.")
        data = response.json()
        if data.get("aud") != self._client_id or data.get("iss") not in GOOGLE_ISSUERS:
            raise AuthError("This sign-in was not issued for BiteTrace.")
        if str(data.get("email_verified")).lower() != "true" or not data.get("sub"):
            raise AuthError("Google account is not verified.")
        name = (data.get("given_name") or data.get("name") or "Reporter")[:40]
        return GoogleIdentity(sub=str(data["sub"]), name=name)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(salt: str, payload: str) -> str:
    return _b64(hmac.new(f"session:{salt}".encode(), payload.encode(), hashlib.sha256).digest())


def issue_token(salt: str, user_key: str, name: str, now: datetime) -> str:
    payload = {"u": user_key, "n": name, "e": int((now + SESSION_TTL).timestamp())}
    body = _b64(json.dumps(payload).encode())
    return f"{body}.{_sign(salt, body)}"


def read_token(salt: str, token: str | None, now: datetime) -> tuple[str, str] | None:
    """Return (user_key, display_name) for a valid, unexpired token, else None."""
    if not token or token.count(".") != 1:
        return None
    body, signature = token.split(".")
    if not hmac.compare_digest(signature, _sign(salt, body)):
        return None
    try:
        data = json.loads(_unb64(body))
        if int(data["e"]) < now.timestamp():
            return None
        return str(data["u"]), str(data["n"])
    except (ValueError, KeyError, TypeError):
        return None
