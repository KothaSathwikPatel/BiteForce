from app.weights import compute_weights

from .conftest import NOW, make_case


def test_established_independent_devices_get_full_weight():
    cases = [make_case(i) for i in range(4)]
    assert compute_weights(cases, NOW) == [1.0] * 4


def test_new_device_is_slightly_down_weighted():
    weights = compute_weights([make_case(0, device_age_h=2)], NOW)
    assert weights == [0.8]


def test_burst_from_one_network_is_halved():
    cases = [make_case(i, network="wifi", reported_min_ago=10 + i * 0.2) for i in range(3)]
    assert compute_weights(cases, NOW) == [0.5, 0.5, 0.5]


def test_same_network_spread_over_time_is_not_a_burst():
    cases = [make_case(i, network="wifi", reported_min_ago=10 + i * 30) for i in range(3)]
    assert compute_weights(cases, NOW) == [1.0, 1.0, 1.0]


def test_network_cap_damps_the_fourth_and_later_devices():
    cases = [make_case(i, network="hostel", reported_min_ago=150 - i * 30) for i in range(5)]  # i=0 reported first
    assert compute_weights(cases, NOW) == [1.0, 1.0, 1.0, 0.3, 0.3]


def test_weights_never_exceed_one_or_drop_to_zero():
    cases = [make_case(i, network="n", device_age_h=1, reported_min_ago=5) for i in range(8)]
    for w in compute_weights(cases, NOW):
        assert 0 < w <= 1


def test_empty_input():
    assert compute_weights([], NOW) == []
