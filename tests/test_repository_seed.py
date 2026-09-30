from datetime import timedelta

import pytest

from app.db import make_engine
from app.repository import Repository
from app.seed import insert_simulated_cases, load_seed_data, seed_database
from app.validation import validate_report

from .conftest import NOW

SALT = "s" * 40


@pytest.fixture
def repo() -> Repository:
    r = Repository(make_engine("sqlite://"))
    r.init_schema()
    return r


def test_seed_is_idempotent_and_marks_verified(repo):
    assert seed_database(repo, SALT, NOW) is True
    assert seed_database(repo, SALT, NOW) is False
    stalls = repo.list_stalls()
    assert len(stalls) == len(load_seed_data()["stalls"]) and all(s.is_seed for s in stalls)


def test_seed_data_is_fictional_and_inside_the_service_area():
    from app.config import SHAMSHABAD
    from app.geo import within_area

    data = load_seed_data()
    assert "FICTIONAL" in data["_note"]
    assert all(within_area(s["lat"], s["lng"], SHAMSHABAD, 2) for s in data["stalls"])
    assert len({s["name"] for s in data["stalls"]}) == len(data["stalls"])


def test_touch_device_keeps_the_original_first_seen(repo):
    first = repo.touch_device("dev-a", NOW)
    again = repo.touch_device("dev-a", NOW + timedelta(days=3))
    assert first == NOW and again == NOW


def test_simulated_cases_are_valid_reports_the_engine_accepts(repo):
    seed_database(repo, SALT, NOW)
    stall = repo.list_stalls()[0]
    insert_simulated_cases(repo, SALT, stall.id, 6, NOW)
    cases = [c for _, c in repo.cases_since(NOW - timedelta(days=3), stall.id)]
    assert len(cases) == 6 and len({c.device_hash for c in cases}) == 6
    for c in cases:
        assert validate_report(c.symptoms, c.eaten_at, c.onset_at, NOW).valid
        assert c.created_at <= NOW


def test_counts_and_event_log(repo):
    seed_database(repo, SALT, NOW)
    stall = repo.list_stalls()[0]
    repo.touch_device("d1", NOW)
    repo.add_report(stall_id=stall.id, device_hash="d1", network_hash="n1", symptoms=["vomiting"],
                    eaten_at=NOW - timedelta(hours=20), onset_at=NOW - timedelta(hours=10), created_at=NOW)
    since = NOW - timedelta(hours=1)
    assert repo.count_device_reports("d1", since) == 1 and repo.count_network_reports("n1", since) == 1
    assert repo.count_device_reports("d1", NOW + timedelta(hours=1)) == 0
    assert repo.device_reported_stall_since("d1", stall.id, since)
    assert not repo.device_reported_stall_since("d2", stall.id, since)

    repo.add_event(stall_id=stall.id, level="ALERT", n_cases=3, p_value=0.001, action="held",
                   created_at=NOW, ai_reasons=["r1"])
    repo.add_event(stall_id=stall.id, level="OUTBREAK", n_cases=5, p_value=1e-5, action="sent",
                   created_at=NOW + timedelta(minutes=1), email_id="e1")
    assert repo.last_event(stall.id, since).action == "sent"
    assert repo.last_event(stall.id, since, ("held",)).ai_reasons == ["r1"]
    assert repo.last_event(stall.id, NOW + timedelta(days=1)) is None
    assert [e.action for e in repo.recent_events(10)] == ["sent", "held"]
    assert len(repo.recent_events(10, stall_id=9999)) == 0


def test_get_stall_missing_returns_none(repo):
    assert repo.get_stall(123) is None
