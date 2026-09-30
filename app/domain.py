"""Plain domain types shared by the engine, service and API (no I/O here)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum


class Level(IntEnum):
    NONE = 0
    WATCH = 1
    ALERT = 2
    OUTBREAK = 3


@dataclass(frozen=True)
class Case:
    """One validated illness report, reduced to what the engine needs."""

    device_hash: str
    network_hash: str
    eaten_at: datetime
    onset_at: datetime
    created_at: datetime
    symptoms: tuple[str, ...]
    device_first_seen: datetime


@dataclass(frozen=True)
class Thresholds:
    """Tunable engine parameters. Defaults are documented in the README."""

    window_hours: float = 72.0  # cases must share a 72 h exposure window
    decay_days: float = 14.0  # alerts fade once the newest case is this old
    baseline: float = 0.2  # expected reports per stall per window with no outbreak
    watch_p: float = 0.05
    alert_p: float = 0.01
    outbreak_p: float = 0.001
    alert_min_devices: int = 3
    outbreak_min_devices: int = 5
    max_exposure_span_h: float = 12.0  # real cases ate at roughly the same time


@dataclass(frozen=True)
class Assessment:
    level: Level
    active: bool  # newest case within the 72 h window
    n_devices: int
    effective_cases: float
    p_value: float | None
    exposure_span_hours: float
    coherent: bool
    median_incubation_hours: float | None
    symptom_counts: dict[str, int]
    first_exposure_at: datetime | None
    last_exposure_at: datetime | None
    reasons: list[str] = field(default_factory=list)

    @property
    def message(self) -> str:
        return LEVEL_MESSAGES[self.level]


LEVEL_MESSAGES: dict[Level, str] = {
    Level.NONE: "No recent illness reports. This does not mean the place is safe.",
    Level.WATCH: "A couple of reports. Being monitored, not enough to call it a signal.",
    Level.ALERT: "Several unrelated people got sick after eating here. Possible issue.",
    Level.OUTBREAK: "Possible outbreak: many unrelated people fell ill after eating here.",
}
