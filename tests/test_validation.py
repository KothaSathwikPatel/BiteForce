from datetime import timedelta

from app.validation import validate_report

from .conftest import NOW


def _v(symptoms=("vomiting",), eaten_h_ago=20.0, gap_h=8.0):
    eaten = NOW - timedelta(hours=eaten_h_ago)
    return validate_report(symptoms, eaten, eaten + timedelta(hours=gap_h), NOW)


def test_plausible_report_is_valid():
    assert _v().valid


def test_requires_a_stomach_symptom():
    result = _v(symptoms=("fever",))
    assert not result.valid
    assert "stomach symptom" in result.reasons[0]


def test_incubation_too_short_rejected():
    assert not _v(gap_h=0.5).valid


def test_incubation_too_long_rejected():
    assert not _v(eaten_h_ago=100, gap_h=80).valid


def test_boundaries_are_inclusive():
    assert _v(gap_h=1.0).valid
    assert _v(eaten_h_ago=80, gap_h=72.0).valid


def test_future_meal_rejected():
    result = _v(eaten_h_ago=-2, gap_h=1.5)
    assert not result.valid
    assert any("future" in r for r in result.reasons)


def test_future_onset_rejected():
    assert not _v(eaten_h_ago=2, gap_h=5).valid


def test_old_meal_rejected():
    assert not _v(eaten_h_ago=24 * 8, gap_h=6).valid


def test_multiple_reasons_are_all_reported():
    result = _v(symptoms=("fever",), gap_h=0.2)
    assert len(result.reasons) >= 2
