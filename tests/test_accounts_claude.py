"""Google sign-in, Claude reviewer, and the extra anti-bot checks."""

import json
from datetime import timedelta

import httpx

from app.ai_review import ClaudeReviewer, GeminiReviewer, RuleBasedReviewer, build_reviewer
from app.auth import AuthError, GoogleIdentity, TokenInfoVerifier, issue_token, read_token

from .conftest import NOW, build_env, make_settings

EVIDENCE = {"alert_level": "OUTBREAK", "meals_close_in_time": True}
SALT = "s" * 40


# ---- Claude reviewer -----------------------------------------------------
def claude_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_claude_happy_path_and_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers.get("x-api-key")
        seen["version"] = request.headers.get("anthropic-version")
        seen["body"] = json.loads(request.content)
        verdict = {"send": True, "confidence": 0.9, "reasons": ["Clear cluster"], "concerns": []}
        return httpx.Response(200, json={"content": [{"type": "text", "text": f"Here you go: {json.dumps(verdict)}"}]})

    decision = ClaudeReviewer("k", "claude-test", client=claude_client(handler)).review(EVIDENCE)
    assert decision.send and decision.source == "claude"
    assert seen["key"] == "k" and seen["version"] == "2023-06-01"
    assert seen["body"]["model"] == "claude-test" and "system" in seen["body"]
    assert "stall" not in json.dumps(seen["body"]["messages"]).lower()


def test_claude_failure_falls_back_to_rules():
    decision = ClaudeReviewer("k", "m", client=claude_client(lambda r: httpx.Response(500))).review(EVIDENCE)
    assert decision.source == "rules-fallback"
    assert decision.send == RuleBasedReviewer().review(EVIDENCE).send


def test_claude_bad_json_falls_back():
    handler = lambda r: httpx.Response(200, json={"content": [{"text": "not json"}]})  # noqa: E731
    assert ClaudeReviewer("k", "m", client=claude_client(handler)).review(EVIDENCE).source == "rules-fallback"


def test_build_reviewer_prefers_claude_then_gemini_then_rules():
    assert isinstance(build_reviewer(make_settings(ANTHROPIC_API_KEY="a", GEMINI_API_KEY="g")), ClaudeReviewer)
    assert isinstance(build_reviewer(make_settings(GEMINI_API_KEY="g")), GeminiReviewer)
    assert isinstance(build_reviewer(make_settings()), RuleBasedReviewer)


# ---- Google verification ---------------------------------------------------
def verifier(payload: dict, status: int = 200) -> TokenInfoVerifier:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=payload)))
    return TokenInfoVerifier("client-123", client=client)


GOOD = {"aud": "client-123", "iss": "accounts.google.com", "email_verified": "true", "sub": "42", "given_name": "Asha"}


def test_verifier_accepts_valid_token():
    assert verifier(GOOD).verify("x" * 30) == GoogleIdentity("42", "Asha")


def test_verifier_rejects_wrong_audience_issuer_unverified_and_http_errors():
    for bad in (
        {**GOOD, "aud": "other"},
        {**GOOD, "iss": "evil.example"},
        {**GOOD, "email_verified": "false"},
        {**GOOD, "sub": ""},
    ):
        try:
            verifier(bad).verify("x" * 30)
        except AuthError:
            continue
        raise AssertionError(f"accepted {bad}")
    for status in (400, 500):
        try:
            verifier(GOOD, status).verify("x" * 30)
        except AuthError:
            continue
        raise AssertionError("accepted an error response")
    try:
        verifier(GOOD).verify("")
    except AuthError:
        pass
    else:
        raise AssertionError("accepted an empty credential")


def test_session_token_roundtrip_expiry_and_tampering():
    token = issue_token(SALT, "userkey", "Asha", NOW)
    assert read_token(SALT, token, NOW) == ("userkey", "Asha")
    assert read_token(SALT, token, NOW + timedelta(days=31)) is None
    assert read_token("other-salt", token, NOW) is None
    body, sig = token.split(".")
    assert read_token(SALT, f"{body}x.{sig}", NOW) is None
    for junk in (None, "", "abc", "a.b.c"):
        assert read_token(SALT, junk, NOW) is None


# ---- API: sign-in, history, account voting ---------------------------------------
class FakeVerifier:
    def verify(self, credential: str) -> GoogleIdentity:
        if credential.startswith("bad"):
            raise AuthError("Google rejected this sign-in.")
        return GoogleIdentity(sub=credential[:6], name="Asha")


def account_env():
    from fastapi.testclient import TestClient

    from app.main import create_app

    base = build_env()
    app = create_app(
        base.settings, reviewer=base.reviewer, emailer=base.emailer, clock=base.clock, verifier=FakeVerifier()
    )
    base.client = TestClient(app)
    base.repo = app.state.service.repo
    return base


def body(stall_id: int, **extra) -> dict:
    return {
        "stall_id": stall_id,
        "symptoms": ["vomiting"],
        "eaten_at": (NOW - timedelta(hours=20)).isoformat(),
        "onset_at": (NOW - timedelta(hours=10)).isoformat(),
        **extra,
    }


def sign_in(env, credential="user01-" + "x" * 30) -> dict:
    res = env.client.post("/api/auth/google", json={"credential": credential})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['token']}"}


def test_sign_in_failure_and_unconfigured():
    env = account_env()
    res = env.client.post("/api/auth/google", json={"credential": "bad-" + "x" * 30})
    assert res.status_code == 401 and res.json()["error"] == "auth_failed"
    assert build_env().client.post("/api/auth/google", json={"credential": "x" * 30}).status_code == 401


def test_my_reports_requires_sign_in_and_lists_history():
    env = account_env()
    assert env.client.get("/api/me/reports").status_code == 401
    headers = {"X-Device-Id": "a" * 20, **sign_in(env)}
    assert env.client.post("/api/reports", json=body(3), headers=headers).status_code == 201
    data = env.client.get("/api/me/reports", headers=headers).json()
    assert data["name"] == "Asha" and len(data["reports"]) == 1
    assert data["reports"][0]["stall_id"] == 3


def test_history_follows_the_account_across_devices_and_is_private():
    env = account_env()
    auth = sign_in(env)
    assert env.client.post("/api/reports", json=body(3), headers={"X-Device-Id": "a" * 20, **auth}).status_code == 201
    other = env.client.get("/api/me/reports", headers={"X-Device-Id": "b" * 20, **auth}).json()
    assert len(other["reports"]) == 1
    stranger = sign_in(env, "user02-" + "y" * 30)
    assert env.client.get("/api/me/reports", headers=stranger).json()["reports"] == []


def test_one_account_cannot_vote_twice_by_switching_devices():
    env = account_env()
    auth = sign_in(env)
    assert env.client.post("/api/reports", json=body(3), headers={"X-Device-Id": "a" * 20, **auth}).status_code == 201
    again = env.client.post("/api/reports", json=body(3), headers={"X-Device-Id": "b" * 20, **auth})
    assert again.status_code == 409


def test_tampered_token_is_treated_as_anonymous():
    env = account_env()
    headers = {"X-Device-Id": "a" * 20, "Authorization": "Bearer forged.token"}
    assert env.client.get("/api/me/reports", headers=headers).status_code == 401
    assert env.client.post("/api/reports", json=body(3), headers=headers).status_code == 201


# ---- extra anti-bot checks -------------------------------------------------
def test_honeypot_filled_is_rejected():
    env = build_env()
    res = env.client.post("/api/reports", json=body(3, hp="http://spam.example"), headers={"X-Device-Id": "a" * 20})
    assert res.status_code == 400


def test_form_filled_too_fast_is_rejected_but_human_speed_passes():
    env = build_env()
    headers = {"X-Device-Id": "a" * 20}
    assert env.client.post("/api/reports", json=body(3, form_ms=800), headers=headers).status_code == 429
    assert env.client.post("/api/reports", json=body(3, form_ms=15000), headers=headers).status_code == 201


def test_config_exposes_ai_mode_and_google_client_id():
    cfg = build_env(ANTHROPIC_API_KEY="k", GOOGLE_CLIENT_ID="cid").client.get("/api/config").json()
    assert cfg["ai_mode"] == "claude" and cfg["google_client_id"] == "cid"
