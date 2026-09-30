"""Outbreak engine: turn scattered illness reports for one stall into an alert level.

This is the statistical detection core of the surveillance system: space-time clustering of
sparse, noisy, human-reported cases followed by a significance test against a baseline.

Method (documented in the README):
1. Keep cases whose meal was within the decay period (14 days).
2. Cluster = cases within a 72 h exposure window of the newest meal.
3. One vote per device; each vote is weighted by anti-abuse rules (weights.py).
4. Compare the weighted case count with a baseline using a Poisson upper-tail test.
5. Require the meals to be close in time (exposure coherence) for ALERT/OUTBREAK.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from math import exp, floor, lgamma, log
from statistics import median

from .domain import Assessment, Case, Level, Thresholds
from .timeutil import hours_between
from .weights import compute_weights


def poisson_sf(k: int, lam: float) -> float:
    """P(X >= k) for X ~ Poisson(lam), summed from the tail for numerical stability."""
    if k <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    term = exp(-lam + k * log(lam) - lgamma(k + 1))
    total = 0.0
    i = k
    while True:
        total += term
        i += 1
        term *= lam / i
        if term < total * 1e-15 or i > k + 200:
            break
    return min(1.0, total)


def poisson_tail(k: float, lam: float) -> float:
    """Upper tail for a fractional weighted count, interpolated in log space."""
    lo = floor(k + 1e-9)
    frac = k - lo
    a = max(poisson_sf(lo, lam), 1e-300)
    if frac < 1e-6:
        return a
    b = max(poisson_sf(lo + 1, lam), 1e-300)
    return exp((1 - frac) * log(a) + frac * log(b))


def _empty() -> Assessment:
    return Assessment(
        level=Level.NONE,
        active=False,
        n_devices=0,
        effective_cases=0.0,
        p_value=None,
        exposure_span_hours=0.0,
        coherent=True,
        median_incubation_hours=None,
        symptom_counts={},
        first_exposure_at=None,
        last_exposure_at=None,
    )


def select_cluster(cases: list[Case], now: datetime, params: Thresholds) -> list[Case]:
    """Cases within the decay period AND within one exposure window of the newest meal."""
    recent = [c for c in cases if now - c.eaten_at <= timedelta(days=params.decay_days)]
    if not recent:
        return []
    newest = max(c.eaten_at for c in recent)
    return [c for c in recent if newest - c.eaten_at <= timedelta(hours=params.window_hours)]


def assess_stall(
    cases: list[Case], now: datetime, params: Thresholds | None = None
) -> Assessment:
    params = params or Thresholds()
    cluster = select_cluster(cases, now, params)
    if not cluster:
        return _empty()

    newest = max(c.eaten_at for c in cluster)
    weights = compute_weights(cluster, now)

    best: dict[str, tuple[Case, float]] = {}
    for case, weight in zip(cluster, weights, strict=True):
        if case.device_hash not in best or weight > best[case.device_hash][1]:
            best[case.device_hash] = (case, weight)

    voters = [c for c, _ in best.values()]
    n = len(voters)
    effective = sum(w for _, w in best.values())
    first = min(c.eaten_at for c in voters)
    last = max(c.eaten_at for c in voters)
    span = hours_between(first, last)
    coherent = span <= params.max_exposure_span_h
    p = poisson_tail(effective, params.baseline)

    level = Level.NONE
    if n >= 2 and p < params.watch_p:
        level = Level.WATCH
    if n >= params.alert_min_devices and p < params.alert_p:
        level = Level.ALERT
    if n >= params.outbreak_min_devices and p < params.outbreak_p:
        level = Level.OUTBREAK

    reasons: list[str] = []
    if n >= 2:
        reasons.append(
            f"{n} unrelated devices reported illness after eating here within "
            f"{params.window_hours:.0f} h."
        )
        reasons.append(f"Chance of this many reports by coincidence: p = {p:.2g}.")
    if effective < n - 1e-9:
        reasons.append(
            f"Weighted count is {effective:.1f} of {n}: some reports were down-weighted "
            "(new devices or bursts from one network)."
        )
    if not coherent and level > Level.WATCH:
        level = Level.WATCH
        reasons.append(
            f"Meals were spread over {span:.0f} h (limit {params.max_exposure_span_h:.0f} h), "
            "which does not look like a single source, so the alert was capped."
        )

    symptoms = Counter(s for c in voters for s in c.symptoms)
    incubation = [hours_between(c.eaten_at, c.onset_at) for c in voters]
    return Assessment(
        level=level,
        active=now - newest <= timedelta(hours=params.window_hours),
        n_devices=n,
        effective_cases=round(effective, 2),
        p_value=p,
        exposure_span_hours=round(span, 2),
        coherent=coherent,
        median_incubation_hours=round(median(incubation), 1),
        symptom_counts=dict(symptoms),
        first_exposure_at=first,
        last_exposure_at=last,
        reasons=reasons,
    )
