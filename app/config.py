"""Runtime settings, read from environment variables (see .env.example)."""

from __future__ import annotations

import logging
import os
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("bitetrace.config")

SHAMSHABAD = (17.2603, 78.3969)


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_salt: str
    demo_mode: bool
    auto_send: bool
    enforce_area: bool
    area_center: tuple[float, float]
    area_radius_km: float
    resend_api_key: str | None
    report_from_email: str
    report_to_email: str | None
    gemini_api_key: str | None
    ai_model: str
    anthropic_api_key: str | None = None
    claude_model: str = "claude-haiku-4-5"
    google_client_id: str | None = None


def _flag(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _num(value: str | None, default: float) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except ValueError:
        log.warning("Ignoring invalid numeric setting %r", value)
        return default


def normalise_database_url(url: str) -> str:
    """Neon/Supabase hand out postgres:// URLs; SQLAlchemy wants an explicit driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix) :]
    return url


def load_dotenv(path: Path) -> None:
    """Minimal .env reader so local runs need no extra dependency. Never overrides real env."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = re.sub(r"\s+#.*$", "", value).strip().strip("'\"")
        os.environ.setdefault(key.strip(), value)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        load_dotenv(Path(".env"))
        env = os.environ

    on_vercel = bool(env.get("VERCEL"))
    default_db = "sqlite:////tmp/bitetrace.db" if on_vercel else "sqlite:///./bitetrace.db"
    salt = env.get("SECRET_SALT") or ""
    if not salt:
        salt = secrets.token_hex(32)
        log.warning("SECRET_SALT is not set; using a random per-process salt (dev only).")

    return Settings(
        database_url=normalise_database_url(env.get("DATABASE_URL") or default_db),
        secret_salt=salt,
        demo_mode=_flag(env.get("DEMO_MODE"), True),
        auto_send=_flag(env.get("AUTO_SEND"), True),
        enforce_area=_flag(env.get("ENFORCE_AREA"), True),
        area_center=(
            _num(env.get("AREA_CENTER_LAT"), SHAMSHABAD[0]),
            _num(env.get("AREA_CENTER_LNG"), SHAMSHABAD[1]),
        ),
        area_radius_km=_num(env.get("AREA_RADIUS_KM"), 25.0),
        resend_api_key=env.get("RESEND_API_KEY") or None,
        report_from_email=env.get("REPORT_FROM_EMAIL") or "BiteTrace Alerts <onboarding@resend.dev>",
        report_to_email=env.get("REPORT_TO_EMAIL") or None,
        gemini_api_key=env.get("GEMINI_API_KEY") or None,
        ai_model=env.get("AI_MODEL") or "gemini-2.5-flash",
        anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
        claude_model=env.get("CLAUDE_MODEL") or "claude-haiku-4-5",
        google_client_id=env.get("GOOGLE_CLIENT_ID") or None,
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
