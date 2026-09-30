import json

import httpx
import pytest

from app.ai_review import (
    AIVerdict,
    GeminiReviewer,
    ReviewDecision,
    RuleBasedReviewer,
    build_reviewer,
    enforce_guardrails,
)

from .conftest import make_settings

EVIDENCE = {"alert_level": "OUTBREAK", "meals_close_in_time": True, "distinct_devices": 5}


def gemini_payload(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def reviewer_with(handler) -> GeminiReviewer:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GeminiReviewer("test-key", "gemini-test", client=client)


def test_gemini_happy_path_and_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        verdict = {"send": True, "confidence": 0.93, "reasons": ["Strong cluster"], "concerns": []}
        return httpx.Response(200, json=gemini_payload(json.dumps(verdict)))

    decision = reviewer_with(handler).review(EVIDENCE)
    assert decision.send and decision.source == "gemini" and decision.confidence == 0.93
    assert "gemini-test:generateContent" in seen["url"] and seen["key"] == "test-key"
    assert "key=" not in seen["url"]  # key travels in a header, never in the URL
    assert json.loads(seen["body"]["contents"][0]["parts"][0]["text"]) == EVIDENCE
    assert seen["body"]["generationConfig"]["temperature"] == 0


def test_gemini_accepts_markdown_fenced_json():
    fenced = '```json\n{"send": false, "confidence": 0.4, "reasons": [], "concerns": ["Too few cases"]}\n```'
    decision = reviewer_with(lambda r: httpx.Response(200, json=gemini_payload(fenced))).review(EVIDENCE)
    assert not decision.send and decision.concerns == ["Too few cases"]


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500, json={}),
        lambda r: httpx.Response(200, json={"unexpected": True}),
        lambda r: httpx.Response(200, json=gemini_payload("not json at all")),
        lambda r: httpx.Response(200, json=gemini_payload('{"send": "maybe", "confidence": 7}')),
    ],
)
def test_bad_answers_fall_back_to_rules(handler):
    decision = reviewer_with(handler).review(EVIDENCE)
    assert decision.source == "rules-fallback"
    assert decision.send  # OUTBREAK + coherent -> rules say send
    assert any("fallback" in c for c in decision.concerns)


def test_network_timeout_falls_back():
    def handler(request):
        raise httpx.ConnectTimeout("slow")

    assert reviewer_with(handler).review(EVIDENCE).source == "rules-fallback"


def test_verdict_trims_long_or_excess_text():
    v = AIVerdict.model_validate({"send": True, "confidence": 0.5, "reasons": ["x" * 500] * 9, "concerns": "oops"})
    assert len(v.reasons) == 5 and len(v.reasons[0]) == 200 and v.concerns == []


def test_rule_based_reviewer():
    r = RuleBasedReviewer()
    assert r.review(EVIDENCE).send
    assert not r.review({**EVIDENCE, "alert_level": "ALERT"}).send
    assert not r.review({**EVIDENCE, "meals_close_in_time": False}).send


def test_guardrail_blocks_ai_from_sending_unflagged_venues():
    pushy = ReviewDecision(True, 0.99, ["trust me"], [], "gemini")
    blocked = enforce_guardrails(pushy, {"alert_level": "WATCH"})
    assert not blocked.send and any("guardrail" in c for c in blocked.concerns)
    assert enforce_guardrails(pushy, {"alert_level": "ALERT"}).send


def test_guardrail_never_upgrades_a_hold():
    hold = ReviewDecision(False, 0.2, [], ["weak"], "gemini")
    assert not enforce_guardrails(hold, {"alert_level": "OUTBREAK"}).send


def test_build_reviewer_selects_by_key():
    assert isinstance(build_reviewer(make_settings()), RuleBasedReviewer)
    assert isinstance(build_reviewer(make_settings(GEMINI_API_KEY="k")), GeminiReviewer)
