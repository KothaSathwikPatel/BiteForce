from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import Case

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
def now() -> datetime:
    return NOW


def make_case(
    i: int = 0,
    *,
    eaten_h_ago: float = 20.0,
    gap_h: float = 8.0,
    network: str | None = None,
    device_age_h: float = 200.0,
    reported_min_ago: float | None = None,
    symptoms: tuple[str, ...] = ("vomiting", "diarrhoea"),
) -> Case:
    """Build a Case; defaults describe an established device on its own network."""
    eaten = NOW - timedelta(hours=eaten_h_ago)
    created = NOW - timedelta(minutes=reported_min_ago if reported_min_ago is not None else 30 + 10 * i)
    return Case(
        device_hash=f"dev{i}",
        network_hash=network or f"net{i}",
        eaten_at=eaten,
        onset_at=eaten + timedelta(hours=gap_h),
        created_at=created,
        symptoms=symptoms,
        device_first_seen=NOW - timedelta(hours=device_age_h),
    )


# ---------------------------------------------------------------------------
# Application-level fixtures
# ---------------------------------------------------------------------------
from dataclasses import dataclass, field  # noqa: E402
from typing import Any  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.ai_review import ReviewDecision  # noqa: E402
from app.config import Settings, load_settings  # noqa: E402
from app.emailer import EmailError  # noqa: E402
from app.main import create_app  # noqa: E402


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeEmailer:
    def __init__(self, configured: bool = True, fail: bool = False) -> None:
        self.configured = configured
        self.fail = fail
        self.sent: list[dict[str, str]] = []

    def send(self, *, subject: str, html: str, text: str, idempotency_key: str) -> str:
        if self.fail:
            raise EmailError("boom")
        self.sent.append({"subject": subject, "html": html, "text": text, "key": idempotency_key})
        return f"email-{len(self.sent)}"


class FakeReviewer:
    def __init__(self, send: bool = True) -> None:
        self.send = send
        self.seen: list[dict[str, Any]] = []

    def review(self, evidence: dict[str, Any]) -> ReviewDecision:
        self.seen.append(evidence)
        return ReviewDecision(
            self.send, 0.9, ["Several unrelated devices, plausible incubation."], [], "fake"
        )


def make_settings(**overrides: str) -> Settings:
    env = {
        "SECRET_SALT": "s" * 40,
        "DATABASE_URL": "sqlite://",
        "DEMO_MODE": "true",
        "AUTO_SEND": "true",
    }
    env.update(overrides)
    return load_settings(env)


@dataclass
class Env:
    client: TestClient
    service: Any
    repo: Any
    emailer: FakeEmailer
    reviewer: FakeReviewer
    clock: Clock
    settings: Settings = field(repr=False, default=None)  # type: ignore[assignment]


def build_env(*, reviewer_sends: bool = True, emailer: FakeEmailer | None = None, **settings) -> Env:
    clock = Clock(NOW)
    emailer = emailer or FakeEmailer()
    reviewer = FakeReviewer(reviewer_sends)
    cfg = make_settings(**settings)
    app = create_app(cfg, reviewer=reviewer, emailer=emailer, clock=clock)
    return Env(TestClient(app), app.state.service, app.state.service.repo, emailer, reviewer, clock, cfg)


@pytest.fixture
def env() -> Env:
    return build_env()
