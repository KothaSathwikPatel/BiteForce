"""End-to-end smoke tests for BiteTrace.

These run the real FastAPI application in memory (SQLite, no network, fake e-mail and
AI reviewer) and check the full report -> cluster -> statistics -> alert path.
The detailed unit tests live in ``tests/``; run everything with ``pytest``.
"""

from __future__ import annotations

import pytest

from app import seed
from tests.conftest import Env, build_env


@pytest.fixture(autouse=True)
def _fictional_places_only(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Ignore local data files so the smoke tests always run on the built-in demo venues."""
    monkeypatch.setattr(seed, "PLACES_PATH", tmp_path / "no_osm_places.json")
    monkeypatch.setattr(seed, "MANUAL_PATH", tmp_path / "no_manual_places.json")


def _first_stall(env: Env) -> dict:
    stalls = env.client.get("/api/stalls").json()
    assert stalls, "seed data should provide at least one place"
    return stalls[0]


def test_health_endpoint_reports_ok() -> None:
    env = build_env()
    response = env.client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_config_exposes_public_settings_only() -> None:
    env = build_env()
    body = env.client.get("/api/config").json()
    assert body["radius_km"] > 0
    assert len(body["center"]) == 2
    assert "secret" not in str(body).lower()


def test_stalls_are_listed_with_a_valid_level() -> None:
    env = build_env()
    stall = _first_stall(env)
    assert stall["level"] in {"NONE", "WATCH", "ALERT", "OUTBREAK"}
    assert -90 <= stall["lat"] <= 90 and -180 <= stall["lng"] <= 180


def test_invalid_report_is_rejected_with_reasons() -> None:
    env = build_env()
    stall = _first_stall(env)
    response = env.client.post(
        "/api/reports",
        json={"stall_id": stall["id"], "symptoms": []},
        headers={"X-Device-Id": "d" * 32},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_input"


def test_simulated_outbreak_sends_one_evidence_email() -> None:
    env = build_env()
    stall = _first_stall(env)
    response = env.client.post("/api/demo/simulate", json={"stall_id": stall["id"]})
    assert response.status_code == 200
    assert len(env.emailer.sent) == 1
    assert "DEMO" in env.emailer.sent[0]["subject"]