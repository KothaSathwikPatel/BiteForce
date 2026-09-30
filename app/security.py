"""Privacy and input-safety helpers: salted hashing, IP extraction, name sanitising."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping

DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9-]{16,64}$")
STALL_NAME_RE = re.compile(r"^[\w .,'&()/\-]{2,60}$", re.UNICODE)


def hash_value(salt: str, value: str) -> str:
    """Keyed hash (HMAC-SHA256, truncated). Raw device IDs and IPs are never stored."""
    return hmac.new(salt.encode(), value.encode(), hashlib.sha256).hexdigest()[:40]


def valid_device_id(value: str | None) -> bool:
    return bool(value and DEVICE_ID_RE.match(value))


def client_ip(headers: Mapping[str, str], fallback: str | None) -> str:
    """Best-effort client IP. On Vercel the platform sets these headers itself."""
    real = headers.get("x-real-ip")
    if real:
        return real.strip()
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return fallback or "unknown"


def sanitize_stall_name(name: str) -> str:
    """Collapse whitespace and allow only a conservative character set."""
    cleaned = re.sub(r"\s+", " ", name).strip()
    if not STALL_NAME_RE.match(cleaned):
        raise ValueError("Stall name must be 2-60 characters: letters, digits and . , ' & ( ) / -")
    return cleaned
