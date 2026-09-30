"""Use-case layer: validates, stores, assesses and (if warranted) escalates a report."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from .ai_review import Reviewer, enforce_guardrails
from .auth import AuthError, GoogleVerifier, issue_token
from .config import Settings
from .domain import Assessment, Level, Thresholds
from .emailer import Emailer, EmailError
from .escalation import build_evidence, render_report
from .geo import snap_to_stall, within_area
from .outbreak import assess_stall, select_cluster
from .repository import EventRow, Repository, StallRow
from .schemas import ReportIn
from .security import hash_value
from .seed import insert_simulated_cases, load_seed_data, seed_background
from .timeutil import utcnow
from .validation import validate_report

DEVICE_LIMIT, DEVICE_WINDOW = 3, timedelta(days=7)
NETWORK_LIMIT, NETWORK_WINDOW = 15, timedelta(hours=24)
DUPLICATE_WINDOW = timedelta(hours=24)
THROTTLE_WINDOW = timedelta(hours=24)
MIN_FILL_MS = 4000  # a human needs a few seconds to fill in the form
VERIFIED_ACCOUNT_AGE = timedelta(days=30)

CARE_ADVICE = [
    "Drink oral rehydration solution (ORS) or clean water in small, frequent sips.",
    "Rest, and eat light foods once you can keep fluids down.",
    "See a doctor today if you have blood in stool, cannot keep water down, a high fever, "
    "very little urine, or symptoms lasting more than 2 days.",
    "Tell the doctor where and when you ate. This is not medical advice.",
]


class ReportRejected(Exception):
    status_code = 400
    code = "rejected"

    def __init__(self, message: str, reasons: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.reasons = reasons or [message]


class ValidationFailed(ReportRejected):
    status_code, code = 422, "implausible_report"


class OutOfArea(ReportRejected):
    status_code, code = 403, "out_of_area"


class RateLimited(ReportRejected):
    status_code, code = 429, "rate_limited"


class DuplicateReport(ReportRejected):
    status_code, code = 409, "duplicate_report"


class AuthFailed(ReportRejected):
    status_code, code = 401, "auth_failed"


class StallNotFound(ReportRejected):
    status_code, code = 404, "stall_not_found"


def _round15(dt: datetime) -> datetime:
    """Blur timestamps to 15 minutes in public views."""
    return dt.replace(minute=dt.minute // 15 * 15, second=0, microsecond=0)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class BiteTraceService:
    def __init__(
        self,
        repo: Repository,
        settings: Settings,
        reviewer: Reviewer,
        emailer: Emailer,
        params: Thresholds | None = None,
        clock: Callable[[], datetime] = utcnow,
        verifier: GoogleVerifier | None = None,
    ) -> None:
        self.verifier = verifier
        self.repo = repo
        self.settings = settings
        self.reviewer = reviewer
        self.emailer = emailer
        self.params = params or Thresholds()
        self.clock = clock

    # ---- submitting a report ---------------------------------------------
    def _identity_hash(self, device_id: str, user: tuple[str, str] | None) -> str:
        """Signed-in reporters vote as an account (one vote across all their devices)."""
        salt = self.settings.secret_salt
        return hash_value(salt, f"acct:{user[0]}") if user else hash_value(salt, f"dev:{device_id}")

    def submit_report(
        self, payload: ReportIn, device_id: str, ip: str, user: tuple[str, str] | None = None
    ) -> dict[str, Any]:
        now = self.clock()
        if payload.hp:
            raise ReportRejected("Could not submit this report.")
        if payload.form_ms is not None and payload.form_ms < MIN_FILL_MS:
            raise RateLimited("That was very fast. Please review the details and try again.")
        device_hash = self._identity_hash(device_id, user)
        network_hash = hash_value(self.settings.secret_salt, f"net:{ip}")

        self._check_area(payload)
        result = validate_report(payload.symptoms, payload.eaten_at, payload.onset_at, now)
        if not result.valid:
            raise ValidationFailed("This report does not look medically plausible.", result.reasons)
        if self.repo.count_device_reports(device_hash, now - DEVICE_WINDOW) >= DEVICE_LIMIT:
            raise RateLimited("Report limit reached for this device (3 per week).")
        if self.repo.count_network_reports(network_hash, now - NETWORK_WINDOW) >= NETWORK_LIMIT:
            raise RateLimited("Too many reports from this network today.")

        stall_id = self._resolve_stall(payload, now)
        if self.repo.device_reported_stall_since(device_hash, stall_id, now - DUPLICATE_WINDOW):
            raise DuplicateReport("You already reported this place in the last 24 hours.")

        self.repo.touch_device(device_hash, now - VERIFIED_ACCOUNT_AGE if user else now)
        self.repo.add_report(
            stall_id=stall_id,
            device_hash=device_hash,
            network_hash=network_hash,
            symptoms=[s.value for s in payload.symptoms],
            eaten_at=payload.eaten_at,
            onset_at=payload.onset_at,
            created_at=now,
        )
        stall = self.repo.get_stall(stall_id)
        assessment = self._assess(stall_id, now)
        alert = self._escalate(stall, assessment, now)
        return {
            "accepted": True,
            "stall_id": stall_id,
            "level": assessment.level.name,
            "n_cases": assessment.n_devices,
            "message": assessment.message,
            "alert": alert,
            "care_advice": CARE_ADVICE,
        }

    def _check_area(self, payload: ReportIn) -> None:
        if not self.settings.enforce_area:
            return
        points = []
        if payload.reporter_lat is not None and payload.reporter_lng is not None:
            points.append((payload.reporter_lat, payload.reporter_lng))
        if payload.new_stall is not None:
            points.append((payload.new_stall.lat, payload.new_stall.lng))
        for lat, lng in points:
            if not within_area(lat, lng, self.settings.area_center, self.settings.area_radius_km):
                raise OutOfArea("BiteTrace currently covers the Shamshabad area only.")

    def _resolve_stall(self, payload: ReportIn, now: datetime) -> int:
        if payload.stall_id is not None:
            if self.repo.get_stall(payload.stall_id) is None:
                raise StallNotFound("That place does not exist.")
            return payload.stall_id
        new = payload.new_stall
        snapped = snap_to_stall(new.lat, new.lng, [(s.id, s.lat, s.lng) for s in self.repo.list_stalls()])
        if snapped is not None:
            return snapped
        return self.repo.add_stall(new.name, new.kind.value, new.lat, new.lng, now)

    # ---- assessment ---------------------------------------------------------
    def _assess(self, stall_id: int, now: datetime) -> Assessment:
        since = now - timedelta(days=self.params.decay_days)
        cases = [c for _, c in self.repo.cases_since(since, stall_id)]
        return assess_stall(cases, now, self.params)

    def _escalate(self, stall: StallRow, a: Assessment, now: datetime) -> dict[str, Any]:
        """Decide whether to email officials. Every branch is recorded or explained."""
        if a.level < Level.ALERT:
            return {"action": "none"}
        if not self.settings.auto_send:
            return {"action": "auto_send_off"}

        last_sent = self.repo.last_event(stall.id, now - THROTTLE_WINDOW, ("sent",))
        if last_sent and a.level <= Level[last_sent.level]:
            return {"action": "throttled", "detail": "A report for this venue was already sent in the last 24 hours."}
        settled = ("sent", "held", "skipped_no_email")
        last_any = self.repo.last_event(stall.id, now - THROTTLE_WINDOW, settled)
        if last_any and last_any.level == a.level.name and last_any.n_cases == a.n_devices:
            return {"action": "unchanged", "detail": "No new evidence since the last review."}

        evidence = build_evidence(stall, a, now)
        decision = enforce_guardrails(self.reviewer.review(evidence), evidence)

        email_id: str | None = None
        detail: str | None = None
        if not decision.send:
            action = "held"
        elif not self.emailer.configured:
            action, detail = "skipped_no_email", "Email is not configured."
        else:
            subject, html, text = render_report(stall, a, decision, demo=self.settings.demo_mode, now=now)
            key = f"bitetrace-{stall.id}-{a.level.name}-{a.n_devices}-{now:%Y%m%d%H}"
            try:
                email_id = self.emailer.send(subject=subject, html=html, text=text, idempotency_key=key)
                action = "sent"
            except EmailError as exc:
                action, detail = "error", str(exc)[:290]

        self.repo.add_event(
            stall_id=stall.id,
            level=a.level.name,
            n_cases=a.n_devices,
            p_value=a.p_value,
            action=action,
            created_at=now,
            ai_source=decision.source,
            ai_send=decision.send,
            ai_confidence=decision.confidence,
            ai_reasons=decision.reasons + [f"Concern: {c}" for c in decision.concerns],
            email_id=email_id,
            detail=detail,
        )
        return {
            "action": action,
            "detail": detail,
            "ai_source": decision.source,
            "ai_send": decision.send,
            "ai_confidence": decision.confidence,
            "ai_reasons": decision.reasons,
            "ai_concerns": decision.concerns,
        }

    # ---- reads ------------------------------------------------------------------
    @staticmethod
    def _stall_public(stall: StallRow, a: Assessment) -> dict[str, Any]:
        return {
            "id": stall.id,
            "name": stall.name,
            "kind": stall.kind,
            "lat": stall.lat,
            "lng": stall.lng,
            "verified": stall.is_seed,
            "level": a.level.name,
            "level_value": int(a.level),
            "active": a.active,
            "n_cases": a.n_devices,
            "message": a.message,
            "last_meal_at": _iso(a.last_exposure_at),
        }

    def list_stalls(self) -> list[dict[str, Any]]:
        now = self.clock()
        by_stall: dict[int, list] = defaultdict(list)
        for stall_id, case in self.repo.cases_since(now - timedelta(days=self.params.decay_days)):
            by_stall[stall_id].append(case)
        return [
            self._stall_public(s, assess_stall(by_stall[s.id], now, self.params))
            for s in self.repo.list_stalls()
        ]

    def stall_detail(self, stall_id: int) -> dict[str, Any]:
        stall = self.repo.get_stall(stall_id)
        if stall is None:
            raise StallNotFound("That place does not exist.")
        now = self.clock()
        cases = [c for _, c in self.repo.cases_since(now - timedelta(days=self.params.decay_days), stall_id)]
        a = assess_stall(cases, now, self.params)
        cluster = select_cluster(cases, now, self.params)
        timeline = sorted(
            (
                {"eaten_at": _round15(c.eaten_at).isoformat(), "onset_at": _round15(c.onset_at).isoformat()}
                for c in cluster
            ),
            key=lambda row: row["eaten_at"],
        )
        detail = self._stall_public(stall, a)
        detail.update(
            {
                "effective_cases": a.effective_cases,
                "p_value": a.p_value,
                "coherent": a.coherent,
                "exposure_span_hours": a.exposure_span_hours,
                "median_incubation_hours": a.median_incubation_hours,
                "symptom_counts": a.symptom_counts,
                "reasons": a.reasons,
                "timeline": timeline,
                "events": [self._event_public(e, stall.name) for e in self.repo.recent_events(5, stall_id)],
            }
        )
        return detail

    @staticmethod
    def _event_public(e: EventRow, stall_name: str) -> dict[str, Any]:
        return {
            "id": e.id,
            "stall_id": e.stall_id,
            "stall_name": stall_name,
            "level": e.level,
            "n_cases": e.n_cases,
            "action": e.action,
            "ai_source": e.ai_source,
            "ai_send": e.ai_send,
            "ai_confidence": e.ai_confidence,
            "ai_reasons": e.ai_reasons,
            "created_at": e.created_at.isoformat(),
        }

    def recent_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        names = {s.id: s.name for s in self.repo.list_stalls()}
        return [self._event_public(e, names.get(e.stall_id, "Unknown")) for e in self.repo.recent_events(limit)]

    def public_config(self) -> dict[str, Any]:
        s = self.settings
        return {
            "center": list(s.area_center),
            "radius_km": s.area_radius_km,
            "demo_mode": s.demo_mode,
            "auto_send": s.auto_send,
            "email_configured": self.emailer.configured,
            "ai_mode": "claude" if s.anthropic_api_key else "gemini" if s.gemini_api_key else "rules",
            "google_client_id": s.google_client_id,
            "landmarks": load_seed_data().get("landmarks", []),
        }

    # ---- accounts ---------------------------------------------------------------
    def sign_in(self, credential: str) -> dict[str, Any]:
        if self.verifier is None:
            raise AuthFailed("Google sign-in is not configured.")
        try:
            identity = self.verifier.verify(credential)
        except AuthError as exc:
            raise AuthFailed(str(exc)) from exc
        user_key = hash_value(self.settings.secret_salt, f"g:{identity.sub}")
        token = issue_token(self.settings.secret_salt, user_key, identity.name, self.clock())
        return {"token": token, "name": identity.name}

    def my_reports(self, user: tuple[str, str] | None) -> dict[str, Any]:
        if user is None:
            raise AuthFailed("Please sign in to see your reports.")
        rows = self.repo.reports_by_device(self._identity_hash("", user))
        return {"name": user[1], "reports": rows}

    # ---- demo tools ----------------------------------------------------------------
    def simulate_outbreak(self, stall_id: int, cases: int) -> dict[str, Any]:
        stall = self.repo.get_stall(stall_id)
        if stall is None:
            raise StallNotFound("That place does not exist.")
        now = self.clock()
        insert_simulated_cases(
            self.repo, self.settings.secret_salt, stall_id, cases, now, rng=random.Random()
        )
        assessment = self._assess(stall_id, now)
        alert = self._escalate(stall, assessment, now)
        return {
            "stall": self._stall_public(stall, assessment),
            "alert": alert,
            "simulated_cases": cases,
            "p_value": assessment.p_value,
        }

    def reset_demo(self) -> None:
        self.repo.reset()
        seed_background(self.repo, self.settings.secret_salt, self.clock())
