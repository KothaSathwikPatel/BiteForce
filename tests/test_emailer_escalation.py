import json
from datetime import timedelta

import httpx
import pytest

from app.ai_review import ReviewDecision
from app.domain import Level
from app.emailer import DisabledEmailer, EmailError, ResendEmailer, build_emailer
from app.escalation import build_evidence, complaint_text, render_report
from app.outbreak import assess_stall
from app.repository import StallRow

from .conftest import NOW, make_case, make_settings

STALL = StallRow(7, "Momo <b>Wagon</b>", "street_food", 17.2608, 78.3942, True)
DECISION = ReviewDecision(True, 0.91, ["Strong cluster <script>"], ["None"], "fake")


def outbreak():
    cases = [make_case(i, eaten_h_ago=20 - i * 0.2) for i in range(5)]
    a = assess_stall(cases, NOW)
    assert a.level == Level.OUTBREAK
    return a


# ---- Resend ---------------------------------------------------------------------
def emailer(handler) -> ResendEmailer:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return ResendEmailer("re_secret", "BiteTrace <onboarding@resend.dev>", "officer@example.com", client)


def test_resend_request_shape_and_returned_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["idem"] = request.headers["idempotency-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "abc-123"})

    email_id = emailer(handler).send(subject="S", html="<p>h</p>", text="t", idempotency_key="k1")
    assert email_id == "abc-123"
    assert seen["url"] == "https://api.resend.com/emails" and seen["auth"] == "Bearer re_secret"
    assert seen["idem"] == "k1"
    assert seen["body"]["to"] == ["officer@example.com"]
    assert seen["body"]["from"] == "BiteTrace <onboarding@resend.dev>"


def test_resend_error_does_not_leak_the_key():
    with pytest.raises(EmailError) as info:
        emailer(lambda r: httpx.Response(403, json={"message": "nope"})).send(
            subject="S", html="h", text="t", idempotency_key="k"
        )
    assert "403" in str(info.value) and "re_secret" not in str(info.value)


def test_resend_network_failure_is_wrapped():
    def handler(request):
        raise httpx.ConnectError("down")

    with pytest.raises(EmailError):
        emailer(handler).send(subject="S", html="h", text="t", idempotency_key="k")


def test_disabled_emailer_and_factory():
    assert not DisabledEmailer.configured
    with pytest.raises(EmailError):
        DisabledEmailer().send(subject="", html="", text="", idempotency_key="")
    assert isinstance(build_emailer(make_settings()), DisabledEmailer)
    assert isinstance(build_emailer(make_settings(RESEND_API_KEY="k")), DisabledEmailer)  # no recipient
    configured = build_emailer(make_settings(RESEND_API_KEY="k", REPORT_TO_EMAIL="a@b.co"))
    assert isinstance(configured, ResendEmailer)


# ---- Evidence & report -------------------------------------------------------------
def test_evidence_contains_no_names_or_free_text():
    evidence = build_evidence(STALL, outbreak(), NOW)
    assert "Momo" not in json.dumps(evidence)
    assert evidence["alert_level"] == "OUTBREAK" and evidence["distinct_devices"] == 5
    assert evidence["meals_close_in_time"] is True and evidence["hours_since_last_meal"] > 0


def test_report_escapes_html_everywhere():
    subject, html, text = render_report(STALL, outbreak(), DECISION, demo=True, now=NOW)
    assert "<b>Wagon" not in html and "&lt;b&gt;Wagon" in html
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert subject.startswith("[BiteTrace DEMO] Outbreak:")
    assert "not a finding of fault" in html and "DEMO" in html
    assert "UNVERIFIED" in text and "5 unrelated" in text


def test_production_report_has_no_demo_banner():
    subject, html, _ = render_report(STALL, outbreak(), DECISION, demo=False, now=NOW)
    assert subject.startswith("[BiteTrace] ") and "simulated data" not in html


def test_complaint_text_is_paste_ready():
    text = complaint_text(STALL, outbreak())
    assert text.startswith("5 unrelated people reported") and "Requesting inspection" in text


def test_evidence_time_fields_are_relative_not_absolute():
    evidence = build_evidence(STALL, outbreak(), NOW + timedelta(hours=1))
    assert evidence["hours_since_last_meal"] == pytest.approx(20.2, abs=0.05)
