"""Evidence summary (for the AI reviewer) and the officer-facing report (for email)."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

from .ai_review import ReviewDecision
from .domain import Assessment
from .repository import StallRow
from .timeutil import hours_between

KIND_LABELS = {"street_food": "Street food stall", "restaurant": "Restaurant", "tea_snack": "Tea / snack / juice stall"}
SYMPTOM_LABELS = {
    "vomiting": "Vomiting",
    "diarrhoea": "Diarrhoea",
    "stomach_cramps": "Stomach cramps",
    "nausea": "Nausea",
    "fever": "Fever",
    "blood_in_stool": "Blood in stool",
}


def build_evidence(stall: StallRow, a: Assessment, now: datetime) -> dict[str, Any]:
    """Structured facts only. The stall name and any user text are deliberately excluded."""
    return {
        "venue_ref": stall.id,
        "venue_kind": stall.kind,
        "venue_in_verified_list": stall.is_seed,
        "alert_level": a.level.name,
        "distinct_devices": a.n_devices,
        "weighted_cases": a.effective_cases,
        "coincidence_p_value": a.p_value,
        "meal_time_spread_hours": a.exposure_span_hours,
        "meals_close_in_time": a.coherent,
        "median_incubation_hours": a.median_incubation_hours,
        "symptom_counts": a.symptom_counts,
        "hours_since_first_meal": (
            round(hours_between(a.first_exposure_at, now), 1) if a.first_exposure_at else None
        ),
        "hours_since_last_meal": (
            round(hours_between(a.last_exposure_at, now), 1) if a.last_exposure_at else None
        ),
        "engine_notes": a.reasons,
    }


def complaint_text(stall: StallRow, a: Assessment) -> str:
    """Paste-ready text for the FSSAI Food Safety Connect complaint form."""
    symptoms = ", ".join(SYMPTOM_LABELS.get(s, s) for s in a.symptom_counts) or "gastrointestinal illness"
    return (
        f"{a.n_devices} unrelated people reported {symptoms.lower()} after eating at "
        f"'{stall.name}' ({KIND_LABELS.get(stall.kind, stall.kind).lower()}, "
        f"{stall.lat:.5f}, {stall.lng:.5f}). Symptoms began a median of "
        f"{a.median_incubation_hours} hours after the meal; meals fell within "
        f"{a.exposure_span_hours} hours of each other. Requesting inspection and water/food sampling."
    )


def _fmt(dt: datetime | None) -> str:
    return dt.strftime("%d %b %Y, %H:%M UTC") if dt else "n/a"


def render_report(
    stall: StallRow, a: Assessment, decision: ReviewDecision, *, demo: bool, now: datetime
) -> tuple[str, str, str]:
    """Return (subject, html, text). All dynamic values are HTML-escaped."""
    tag = "[BiteTrace DEMO] " if demo else "[BiteTrace] "
    subject = f"{tag}{a.level.name.title()}: {stall.name}, {a.n_devices} unrelated reports"
    name = escape(stall.name)
    complaint = complaint_text(stall, a)
    map_url = f"https://www.openstreetmap.org/?mlat={stall.lat}&mlon={stall.lng}#map=18/{stall.lat}/{stall.lng}"

    sym_rows = "".join(
        f"<tr><td>{escape(SYMPTOM_LABELS.get(s, s))}</td><td>{n} of {a.n_devices}</td></tr>"
        for s, n in sorted(a.symptom_counts.items(), key=lambda kv: -kv[1])
    )
    meals_from, meals_to = escape(_fmt(a.first_exposure_at)), escape(_fmt(a.last_exposure_at))
    symptom_line = ", ".join(f"{SYMPTOM_LABELS.get(s, s)} {n}/{a.n_devices}" for s, n in a.symptom_counts.items())
    notes = "".join(f"<li>{escape(r)}</li>" for r in a.reasons)
    ai_reasons = "".join(f"<li>{escape(r)}</li>" for r in decision.reasons)
    ai_concerns = "".join(f"<li>{escape(r)}</li>" for r in decision.concerns)
    banner = (
        "<p style='background:#fff3cd;padding:8px 12px;border-radius:8px'>"
        "<b>DEMO:</b> generated from simulated data. Not a real complaint.</p>"
        if demo
        else ""
    )

    font = "-apple-system,Segoe UI,Roboto,sans-serif"
    html = f"""<div style="font-family:{font};max-width:640px;margin:auto;color:#1c1c1e">
<h2 style="margin-bottom:4px">BiteTrace evidence report</h2>
<p style="color:#6e6e73;margin-top:0">Generated {escape(_fmt(now))}</p>
{banner}
<p style="background:#f2f2f7;padding:8px 12px;border-radius:8px"><b>Unverified crowdsourced signal.</b>
This is a request for inspection, not a finding of fault. Only laboratory testing can confirm a source.</p>
<h3>{name}</h3>
<p>{escape(KIND_LABELS.get(stall.kind, stall.kind))} &middot; <a href="{escape(map_url)}">Open location on map</a>
({stall.lat:.5f}, {stall.lng:.5f})</p>
<table cellpadding="6" style="border-collapse:collapse;width:100%">
<tr><td><b>Alert level</b></td><td>{escape(a.level.name)}</td></tr>
<tr><td><b>Unrelated devices reporting</b></td><td>{a.n_devices} (weighted {a.effective_cases})</td></tr>
<tr><td><b>Chance by coincidence</b></td><td>p = {a.p_value:.2g}</td></tr>
<tr><td><b>Meals eaten between</b></td><td>{meals_from} and {meals_to}</td></tr>
<tr><td><b>Median time to symptoms</b></td><td>{a.median_incubation_hours} hours</td></tr>
</table>
<h4>Symptoms</h4><table cellpadding="4">{sym_rows}</table>
<h4>Engine notes</h4><ul>{notes}</ul>
<h4>AI review ({escape(decision.source)}, confidence {decision.confidence:.2f})</h4>
<ul>{ai_reasons}</ul>{"<p><b>Concerns:</b></p><ul>" + ai_concerns + "</ul>" if ai_concerns else ""}
<h4>Suggested action</h4>
<ol><li>Inspect the venue and its water source today.</li>
<li>Collect water and food samples for testing.</li>
<li>Advise the vendor on hygiene and, if needed, pause operations pending results.</li></ol>
<h4>Ready-to-paste complaint text (Food Safety Connect)</h4>
<blockquote style="background:#f2f2f7;padding:10px 14px;border-radius:8px">{escape(complaint)}</blockquote>
<p style="color:#6e6e73;font-size:12px">Sent automatically by BiteTrace. Reporter identities are anonymous;
no names or phone numbers are stored.</p></div>"""

    text = "\n".join(
        [
            f"BiteTrace evidence report{' (DEMO, simulated data)' if demo else ''}",
            "UNVERIFIED crowdsourced signal: a request for inspection, not a finding of fault.",
            "",
            f"Venue: {stall.name} ({KIND_LABELS.get(stall.kind, stall.kind)})",
            f"Location: {stall.lat:.5f}, {stall.lng:.5f}  {map_url}",
            f"Alert level: {a.level.name}",
            f"Unrelated devices: {a.n_devices} (weighted {a.effective_cases}), p = {a.p_value:.2g}",
            f"Meals: {_fmt(a.first_exposure_at)} to {_fmt(a.last_exposure_at)}",
            f"Median time to symptoms: {a.median_incubation_hours} h",
            f"Symptoms: {symptom_line}",
            "",
            f"AI review ({decision.source}, confidence {decision.confidence:.2f}):",
            *[f"- {r}" for r in decision.reasons],
            "",
            "Complaint text:",
            complaint,
        ]
    )
    return subject, html, text
