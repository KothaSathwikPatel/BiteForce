import pytest

from app.domain import Level, Thresholds
from app.outbreak import assess_stall, poisson_sf, poisson_tail

from .conftest import NOW, make_case


def _cluster(n, **kw):
    """n independent, established devices who ate around the same time."""
    return [make_case(i, eaten_h_ago=20 - i * 0.2, **kw) for i in range(n)]


# ---- Poisson maths ---------------------------------------------------------
def test_poisson_sf_edge_cases():
    assert poisson_sf(0, 0.2) == 1.0
    assert poisson_sf(-1, 0.2) == 1.0
    assert poisson_sf(3, 0.0) == 0.0


def test_poisson_sf_known_values():
    # P(X>=1) = 1 - e^-0.2
    assert poisson_sf(1, 0.2) == pytest.approx(0.18127, abs=1e-4)
    assert poisson_sf(3, 0.2) == pytest.approx(0.001148, abs=1e-5)
    assert poisson_sf(5, 0.2) == pytest.approx(2.258e-6, rel=0.01)


def test_poisson_sf_is_monotonic_decreasing():
    values = [poisson_sf(k, 0.2) for k in range(0, 9)]
    assert values == sorted(values, reverse=True)


def test_poisson_tail_interpolates_between_integers():
    lo, hi = poisson_sf(2, 0.2), poisson_sf(3, 0.2)
    mid = poisson_tail(2.5, 0.2)
    assert hi < mid < lo
    assert poisson_tail(3.0, 0.2) == pytest.approx(hi)


# ---- Alert levels ----------------------------------------------------------
def test_no_cases_is_none():
    a = assess_stall([], NOW)
    assert a.level == Level.NONE and a.n_devices == 0 and not a.active


def test_single_report_never_triggers_anything():
    a = assess_stall(_cluster(1), NOW)
    assert a.level == Level.NONE


def test_two_reports_is_watch():
    assert assess_stall(_cluster(2), NOW).level == Level.WATCH


def test_three_reports_is_alert():
    assert assess_stall(_cluster(3), NOW).level == Level.ALERT


def test_four_reports_is_still_only_alert():
    assert assess_stall(_cluster(4), NOW).level == Level.ALERT


def test_five_reports_is_outbreak():
    a = assess_stall(_cluster(5), NOW)
    assert a.level == Level.OUTBREAK
    assert a.n_devices == 5 and a.active and a.coherent
    assert a.p_value < 0.001
    assert a.symptom_counts == {"vomiting": 5, "diarrhoea": 5}


def test_meals_spread_over_days_are_capped_at_watch():
    cases = [make_case(i, eaten_h_ago=70 - i * 14) for i in range(5)]  # 56 h spread
    a = assess_stall(cases, NOW)
    assert not a.coherent and a.level == Level.WATCH
    assert any("capped" in r for r in a.reasons)


def test_same_device_reporting_twice_counts_once():
    cases = _cluster(2)
    cases.append(make_case(0, eaten_h_ago=19.5))  # dev0 again
    assert assess_stall(cases, NOW).n_devices == 2


def test_new_devices_lower_confidence_but_still_flag_five_people():
    cases = _cluster(5, device_age_h=1)
    a = assess_stall(cases, NOW)
    assert a.effective_cases == pytest.approx(4.0)
    assert a.level == Level.OUTBREAK


def test_scripted_burst_from_one_network_cannot_reach_outbreak():
    cases = [make_case(i, eaten_h_ago=20, network="fake", reported_min_ago=5 + i * 0.1) for i in range(6)]
    a = assess_stall(cases, NOW)
    assert a.level < Level.OUTBREAK
    assert a.effective_cases < a.n_devices
    assert any("down-weighted" in r for r in a.reasons)


def test_old_cases_beyond_decay_are_ignored():
    cases = [make_case(i, eaten_h_ago=24 * 15) for i in range(5)]
    assert assess_stall(cases, NOW).level == Level.NONE


def test_alert_stays_visible_but_inactive_after_the_window():
    cases = [make_case(i, eaten_h_ago=24 * 6 - i * 0.2) for i in range(5)]
    a = assess_stall(cases, NOW)
    assert a.level == Level.OUTBREAK and not a.active


def test_only_cases_near_the_newest_meal_form_the_cluster():
    old = [make_case(i, eaten_h_ago=24 * 9) for i in range(3)]
    new = [make_case(10 + i, eaten_h_ago=20) for i in range(2)]
    a = assess_stall(old + new, NOW)
    assert a.n_devices == 2 and a.level == Level.WATCH


def test_median_incubation_reported():
    cases = [make_case(0, gap_h=6), make_case(1, gap_h=10), make_case(2, gap_h=8)]
    assert assess_stall(cases, NOW).median_incubation_hours == 8.0


def test_custom_thresholds_are_respected():
    strict = Thresholds(outbreak_min_devices=8)
    assert assess_stall(_cluster(5), NOW, strict).level == Level.ALERT


def test_public_messages_never_claim_safety_or_guilt():
    from app.domain import LEVEL_MESSAGES

    joined = " ".join(LEVEL_MESSAGES.values()).lower()
    assert "guilty" not in joined
    assert "not mean the place is safe" in LEVEL_MESSAGES[Level.NONE].lower()
    assert "safe" not in " ".join(m for lv, m in LEVEL_MESSAGES.items() if lv != Level.NONE).lower()


def test_assessment_message_property():
    assert assess_stall(_cluster(5), NOW).message.startswith("Possible outbreak")
