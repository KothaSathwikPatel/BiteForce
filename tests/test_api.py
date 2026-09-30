import re
from datetime import timedelta

from .conftest import NOW, Env, FakeEmailer, build_env


def dev(i: int) -> dict[str, str]:
    """Distinct device + distinct network per index."""
    return {"X-Device-Id": f"test-device-{i:08d}", "X-Real-IP": f"10.0.0.{i}"}


def body(stall_id: int, eaten_h_ago: float = 20, gap_h: float = 8, **extra) -> dict:
    eaten = NOW - timedelta(hours=eaten_h_ago)
    payload = {
        "stall_id": stall_id,
        "symptoms": ["vomiting", "diarrhoea"],
        "eaten_at": eaten.isoformat(),
        "onset_at": (eaten + timedelta(hours=gap_h)).isoformat(),
    }
    payload.update(extra)
    return payload


def stall_id(env: Env, name: str) -> int:
    return next(s["id"] for s in env.client.get("/api/stalls").json() if s["name"] == name)


# ---- meta / read endpoints ---------------------------------------------------
def test_health(env):
    assert env.client.get("/api/health").json() == {"status": "ok"}


def test_config_exposes_no_secrets(env):
    data = env.client.get("/api/config").json()
    assert data["center"] == [17.2603, 78.3969]
    assert data["demo_mode"] is True and data["ai_mode"] == "rules"
    text = str(data).lower()
    assert "resend" not in text and "@" not in text and "key" not in text


def test_stalls_are_seeded_with_background_levels(env):
    stalls = env.client.get("/api/stalls").json()
    assert len(stalls) == 16
    levels = {s["name"]: s["level"] for s in stalls}
    assert levels["Highway Dhaba Grill"] == "ALERT"
    assert levels["Corner Juice Bar"] == "WATCH"
    assert levels["Bus Stand Bhel Cart"] == "NONE"
    assert all(s["verified"] for s in stalls)


def test_security_headers_and_no_store(env):
    r = env.client.get("/api/stalls")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
    assert "content-security-policy" not in env.client.get("/docs").headers


def test_frontend_is_served(env):
    r = env.client.get("/")
    assert r.status_code == 200 and "BiteTrace" in r.text


def test_stall_detail_and_404(env):
    sid = stall_id(env, "Highway Dhaba Grill")
    detail = env.client.get(f"/api/stalls/{sid}").json()
    assert detail["level"] == "ALERT" and len(detail["timeline"]) == 3
    assert "device_hash" not in str(detail)
    assert not re.search(r"[0-9a-f]{40}", str(detail))  # no hashed identifiers leak
    assert env.client.get("/api/stalls/9999").status_code == 404


# ---- submitting reports ---------------------------------------------------------
def test_device_header_required(env):
    sid = stall_id(env, "Momo Wagon")
    assert env.client.post("/api/reports", json=body(sid)).status_code == 400
    assert env.client.post("/api/reports", json=body(sid), headers={"X-Device-Id": "short"}).status_code == 400


def test_single_report_is_accepted_but_triggers_nothing(env):
    sid = stall_id(env, "Momo Wagon")
    r = env.client.post("/api/reports", json=body(sid), headers=dev(1))
    assert r.status_code == 201
    data = r.json()
    assert data["level"] == "NONE" and data["alert"]["action"] == "none"
    assert any("ORS" in tip for tip in data["care_advice"])
    assert env.emailer.sent == []


def test_implausible_report_rejected_with_reasons(env):
    sid = stall_id(env, "Momo Wagon")
    r = env.client.post("/api/reports", json=body(sid, gap_h=0.2), headers=dev(1))
    assert r.status_code == 422
    assert r.json()["error"] == "implausible_report" and r.json()["reasons"]


def test_invalid_input_shapes_rejected(env):
    sid = stall_id(env, "Momo Wagon")
    h = dev(1)
    assert env.client.post("/api/reports", json={**body(sid), "extra": 1}, headers=h).status_code == 422
    naive = body(sid)
    naive["eaten_at"] = "2026-09-29T16:00:00"
    assert env.client.post("/api/reports", json=naive, headers=h).status_code == 422
    both = body(sid, new_stall={"name": "Test Cart", "lat": 17.26, "lng": 78.39})
    assert env.client.post("/api/reports", json=both, headers=h).status_code == 422
    r = env.client.post("/api/reports", json={**body(sid), "symptoms": []}, headers=h)
    assert r.status_code == 422 and r.json()["error"] == "invalid_input"


def test_reporter_outside_service_area_rejected(env):
    sid = stall_id(env, "Momo Wagon")
    r = env.client.post("/api/reports", json=body(sid, reporter_lat=28.61, reporter_lng=77.21), headers=dev(1))
    assert r.status_code == 403 and r.json()["error"] == "out_of_area"


def test_area_check_can_be_disabled():
    e = build_env(ENFORCE_AREA="false")
    sid = stall_id(e, "Momo Wagon")
    r = e.client.post("/api/reports", json=body(sid, reporter_lat=28.61, reporter_lng=77.21), headers=dev(1))
    assert r.status_code == 201


def test_duplicate_report_same_device_same_place(env):
    sid = stall_id(env, "Momo Wagon")
    assert env.client.post("/api/reports", json=body(sid), headers=dev(1)).status_code == 201
    r = env.client.post("/api/reports", json=body(sid), headers=dev(1))
    assert r.status_code == 409 and r.json()["error"] == "duplicate_report"


def test_device_weekly_limit(env):
    names = ["Momo Wagon", "Morning Dosa Cart", "Golden Pani Puri Cart", "Metro Corner Shawarma"]
    codes = [env.client.post("/api/reports", json=body(stall_id(env, n)), headers=dev(1)).status_code for n in names]
    assert codes == [201, 201, 201, 429]


def test_network_daily_limit(env):
    sid = stall_id(env, "Momo Wagon")
    codes = []
    for i in range(16):
        h = {"X-Device-Id": f"test-device-{i:08d}", "X-Real-IP": "192.168.1.1"}
        codes.append(env.client.post("/api/reports", json=body(sid), headers=h).status_code)
    assert codes[:15] == [201] * 15 and codes[15] == 429


def test_nonexistent_stall(env):
    assert env.client.post("/api/reports", json=body(9999), headers=dev(1)).status_code == 404


# ---- new venues via map pin -----------------------------------------------------------
def test_pin_near_existing_stall_snaps_to_it(env):
    sid = stall_id(env, "Momo Wagon")
    stall = next(s for s in env.client.get("/api/stalls").json() if s["id"] == sid)
    pin = {"name": "Something Else", "lat": stall["lat"] + 0.0002, "lng": stall["lng"]}  # ~22 m
    r = env.client.post("/api/reports", json=body(None, new_stall=pin) | {"stall_id": None}, headers=dev(1))
    assert r.status_code == 201 and r.json()["stall_id"] == sid
    assert len(env.client.get("/api/stalls").json()) == 16


def test_pin_in_empty_spot_creates_unverified_stall(env):
    pin = {"name": "New Cart (near school)", "kind": "street_food", "lat": 17.2700, "lng": 78.4100}
    r = env.client.post("/api/reports", json=body(None, new_stall=pin) | {"stall_id": None}, headers=dev(1))
    assert r.status_code == 201
    stalls = env.client.get("/api/stalls").json()
    assert len(stalls) == 17 and stalls[-1]["verified"] is False


def test_malicious_stall_name_rejected(env):
    pin = {"name": "<script>alert(1)</script>", "lat": 17.27, "lng": 78.41}
    r = env.client.post("/api/reports", json=body(None, new_stall=pin) | {"stall_id": None}, headers=dev(1))
    assert r.status_code == 422


def test_new_stall_far_outside_area_rejected(env):
    pin = {"name": "Far Cart", "lat": 28.61, "lng": 77.21}
    r = env.client.post("/api/reports", json=body(None, new_stall=pin) | {"stall_id": None}, headers=dev(1))
    assert r.status_code == 403


# ---- outbreak flow, end to end ---------------------------------------------------------------
def _five_reports(env: Env, sid: int) -> list[dict]:
    return [env.client.post("/api/reports", json=body(sid), headers=dev(i)).json() for i in range(1, 6)]


def test_five_unrelated_reports_send_one_evidence_email(env):
    sid = stall_id(env, "Momo Wagon")
    results = _five_reports(env, sid)
    assert [r["level"] for r in results] == ["NONE", "WATCH", "ALERT", "ALERT", "OUTBREAK"] or \
        results[-1]["level"] == "OUTBREAK"
    assert len(env.emailer.sent) >= 1
    sent = env.emailer.sent[-1]
    assert "Momo Wagon" in sent["html"] and "DEMO" in sent["subject"]
    alerts = env.client.get("/api/alerts").json()
    assert alerts[0]["action"] == "sent" and alerts[0]["ai_source"] == "fake"
    detail = env.client.get(f"/api/stalls/{sid}").json()
    assert detail["level"] == "OUTBREAK" and detail["events"][0]["action"] == "sent"


def test_no_second_email_within_24h_for_same_level(env):
    sid = stall_id(env, "Momo Wagon")
    _five_reports(env, sid)
    count = len(env.emailer.sent)
    r = env.client.post("/api/reports", json=body(sid), headers=dev(6)).json()
    assert r["alert"]["action"] == "throttled"
    assert len(env.emailer.sent) == count


def test_scripted_burst_from_one_network_does_not_trigger_email():
    e = build_env()
    sid = stall_id(e, "Momo Wagon")
    for i in range(1, 7):
        h = {"X-Device-Id": f"attack-device-{i:08d}", "X-Real-IP": "6.6.6.6"}
        r = e.client.post("/api/reports", json=body(sid), headers=h).json()
    assert r["level"] in ("NONE", "WATCH")
    assert e.emailer.sent == []


def test_ai_can_hold_back_a_candidate():
    e = build_env(reviewer_sends=False)
    sid = stall_id(e, "Momo Wagon")
    _five_reports(e, sid)
    assert e.emailer.sent == []
    assert e.client.get("/api/alerts").json()[0]["action"] == "held"


def test_auto_send_can_be_switched_off():
    e = build_env(AUTO_SEND="false")
    sid = stall_id(e, "Momo Wagon")
    results = _five_reports(e, sid)
    assert results[-1]["alert"]["action"] == "auto_send_off"
    assert e.emailer.sent == [] and e.reviewer.seen == []


def test_email_not_configured_is_recorded():
    e = build_env(emailer=FakeEmailer(configured=False))
    sid = stall_id(e, "Momo Wagon")
    _five_reports(e, sid)
    assert e.client.get("/api/alerts").json()[0]["action"] == "skipped_no_email"


def test_email_failure_is_recorded_and_does_not_break_reporting():
    e = build_env(emailer=FakeEmailer(fail=True))
    sid = stall_id(e, "Momo Wagon")
    results = _five_reports(e, sid)
    assert all(r["accepted"] for r in results)
    assert e.client.get("/api/alerts").json()[0]["action"] == "error"


def test_reviewer_never_sees_stall_names_or_free_text(env):
    sid = stall_id(env, "Momo Wagon")
    _five_reports(env, sid)
    assert env.reviewer.seen
    dump = str(env.reviewer.seen)
    assert "Momo" not in dump and "name" not in dump.lower()


def test_reviewer_not_called_below_alert_level(env):
    sid = stall_id(env, "Momo Wagon")
    env.client.post("/api/reports", json=body(sid), headers=dev(1))
    env.client.post("/api/reports", json=body(sid), headers=dev(2))
    assert env.reviewer.seen == []


# ---- demo tools ----------------------------------------------------------------------------------
def test_simulate_fires_the_full_pipeline(env):
    sid = stall_id(env, "Sugarcane Juice Cart")
    r = env.client.post("/api/demo/simulate", json={"stall_id": sid, "cases": 6})
    assert r.status_code == 200
    data = r.json()
    assert data["stall"]["level"] == "OUTBREAK" and data["alert"]["action"] == "sent"
    assert len(env.emailer.sent) == 1


def test_simulate_unknown_stall_and_bad_input(env):
    assert env.client.post("/api/demo/simulate", json={"stall_id": 999}).status_code == 404
    assert env.client.post("/api/demo/simulate", json={"stall_id": 1, "cases": 99}).status_code == 422


def test_demo_endpoints_disabled_outside_demo_mode():
    e = build_env(DEMO_MODE="false")
    assert e.client.post("/api/demo/simulate", json={"stall_id": 1}).status_code == 404
    assert e.client.post("/api/demo/reset").status_code == 404


def test_reset_clears_events_and_user_stalls(env):
    sid = stall_id(env, "Sugarcane Juice Cart")
    env.client.post("/api/demo/simulate", json={"stall_id": sid, "cases": 6})
    pin = {"name": "Temp Cart", "lat": 17.27, "lng": 78.41}
    env.client.post("/api/reports", json=body(None, new_stall=pin) | {"stall_id": None}, headers=dev(1))
    assert env.client.post("/api/demo/reset").json() == {"status": "reset"}
    assert env.client.get("/api/alerts").json() == []
    stalls = env.client.get("/api/stalls").json()
    assert len(stalls) == 16
    assert {s["name"]: s["level"] for s in stalls}["Sugarcane Juice Cart"] == "NONE"
    assert {s["name"]: s["level"] for s in stalls}["Highway Dhaba Grill"] == "ALERT"


def test_simulate_returns_p_value_for_the_step_by_step_demo(env):
    stall = next(s for s in env.client.get("/api/stalls").json() if s["level"] == "NONE")
    data = env.client.post("/api/demo/simulate", json={"stall_id": stall["id"], "cases": 6}).json()
    assert data["p_value"] is not None and data["p_value"] < 0.001
    assert data["alert"]["action"] == "sent"
