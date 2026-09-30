import pytest

from app.geo import haversine_m, snap_to_stall, within_area
from app.security import client_ip, hash_value, sanitize_stall_name, valid_device_id

SHAMSHABAD = (17.2603, 78.3969)


def test_haversine_zero_distance():
    assert haversine_m(*SHAMSHABAD, *SHAMSHABAD) == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_distance():
    # 0.01 degrees of latitude is about 1.11 km
    d = haversine_m(17.26, 78.39, 17.27, 78.39)
    assert d == pytest.approx(1111, rel=0.01)


def test_snap_picks_nearest_within_radius():
    stalls = [(1, 17.26030, 78.39690), (2, 17.26050, 78.39690)]
    assert snap_to_stall(17.26048, 78.39690, stalls) == 2


def test_snap_returns_none_when_too_far():
    assert snap_to_stall(17.27, 78.39, [(1, 17.2603, 78.3969)]) is None


def test_snap_with_no_stalls():
    assert snap_to_stall(17.26, 78.39, []) is None


def test_within_area():
    assert within_area(17.27, 78.40, SHAMSHABAD, 25)
    assert not within_area(28.61, 77.21, SHAMSHABAD, 25)  # Delhi


def test_hash_is_stable_salted_and_not_reversible_looking():
    a = hash_value("salt1", "device-123456789012")
    assert a == hash_value("salt1", "device-123456789012")
    assert a != hash_value("salt2", "device-123456789012")
    assert "device" not in a and len(a) == 40


@pytest.mark.parametrize("value,ok", [("a" * 16, True), ("abc-123-" * 4, True), ("short", False),
                                       ("has space " * 3, False), (None, False), ("x" * 65, False)])
def test_device_id_format(value, ok):
    assert valid_device_id(value) is ok


def test_client_ip_prefers_real_ip_then_forwarded_then_fallback():
    assert client_ip({"x-real-ip": "1.1.1.1", "x-forwarded-for": "2.2.2.2"}, "3.3.3.3") == "1.1.1.1"
    assert client_ip({"x-forwarded-for": "2.2.2.2, 9.9.9.9"}, "3.3.3.3") == "2.2.2.2"
    assert client_ip({}, "3.3.3.3") == "3.3.3.3"
    assert client_ip({}, None) == "unknown"


def test_sanitize_collapses_whitespace():
    assert sanitize_stall_name("  Pani   Puri  Cart ") == "Pani Puri Cart"


@pytest.mark.parametrize("bad", ["<script>alert(1)</script>", "a", "x" * 61, "Name; DROP TABLE", "😀😀"])
def test_sanitize_rejects_unsafe_names(bad):
    with pytest.raises(ValueError):
        sanitize_stall_name(bad)
