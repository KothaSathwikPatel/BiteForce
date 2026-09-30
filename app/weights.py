"""Anti-abuse weighting: how much each case counts towards an outbreak signal.

A case never counts for more than 1.0. Suspicious patterns *reduce* weight instead of
hard-blocking, so genuine clusters (e.g. friends in one hostel) are damped, not silenced.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from .domain import Case
from .timeutil import hours_between

NEW_DEVICE_AGE_H = 24.0
NEW_DEVICE_WEIGHT = 0.8  # brand-new devices count a little less than established ones
BURST_WINDOW_S = 120.0  # 3+ reports from one network within 2 minutes look scripted
BURST_MIN_REPORTS = 3
BURST_WEIGHT = 0.5
NETWORK_FULL_WEIGHT_CAP = 3  # one network can fully count for at most 3 devices
OVER_CAP_WEIGHT = 0.3


def compute_weights(cases: list[Case], now: datetime) -> list[float]:
    """Return one weight in (0, 1] per case, in the same order as the input."""
    weights = [1.0] * len(cases)

    for i, case in enumerate(cases):
        if hours_between(case.device_first_seen, now) < NEW_DEVICE_AGE_H:
            weights[i] *= NEW_DEVICE_WEIGHT

    by_network: dict[str, list[int]] = defaultdict(list)
    for i, case in enumerate(cases):
        by_network[case.network_hash].append(i)

    for indexes in by_network.values():
        ordered = sorted(indexes, key=lambda i: cases[i].created_at)
        for position, i in enumerate(ordered):
            if position >= NETWORK_FULL_WEIGHT_CAP:
                weights[i] *= OVER_CAP_WEIGHT
            near = sum(
                1
                for j in indexes
                if abs((cases[j].created_at - cases[i].created_at).total_seconds())
                <= BURST_WINDOW_S
            )
            if near >= BURST_MIN_REPORTS:
                weights[i] *= BURST_WEIGHT

    return weights
