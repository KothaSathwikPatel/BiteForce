"""Medical-plausibility checks applied to every report before it is stored.

Biomedical rules: incubation window between the meal and symptom onset, and at least one
gastrointestinal symptom, so implausible reports never reach the detection stage."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

GI_SYMPTOMS = frozenset({"vomiting", "diarrhoea", "stomach_cramps", "nausea", "blood_in_stool"})
ALL_SYMPTOMS = GI_SYMPTOMS | {"fever"}

MIN_INCUBATION_H = 1.0  # food poisoning rarely starts sooner than ~1 h after eating
MAX_INCUBATION_H = 72.0  # ...or later than ~72 h for the common bacterial causes
MAX_EXPOSURE_AGE = timedelta(days=7)
CLOCK_SKEW = timedelta(minutes=5)


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reasons: list[str] = field(default_factory=list)


def validate_report(
    symptoms: Iterable[str], eaten_at: datetime, onset_at: datetime, now: datetime
) -> ValidationResult:
    """Return every reason a report is implausible (empty list means valid)."""
    reasons: list[str] = []

    if not set(symptoms) & GI_SYMPTOMS:
        reasons.append("At least one stomach symptom (vomiting, diarrhoea, cramps, nausea) is required.")
    if eaten_at > now + CLOCK_SKEW:
        reasons.append("The meal time is in the future.")
    if onset_at > now + CLOCK_SKEW:
        reasons.append("The symptom start time is in the future.")
    if now - eaten_at > MAX_EXPOSURE_AGE:
        reasons.append("Meals older than 7 days are not counted.")

    gap_h = (onset_at - eaten_at).total_seconds() / 3600.0
    if gap_h < MIN_INCUBATION_H:
        reasons.append("Symptoms must start at least 1 hour after eating.")
    elif gap_h > MAX_INCUBATION_H:
        reasons.append("Symptoms must start within 72 hours of eating to link to that meal.")

    return ValidationResult(valid=not reasons, reasons=reasons)
