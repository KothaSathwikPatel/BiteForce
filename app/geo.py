"""Geospatial helpers: distance, snapping a dropped pin to a known stall, area check."""

from __future__ import annotations

from collections.abc import Iterable
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_M = 6_371_000.0
SNAP_RADIUS_M = 50.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = radians(lat1), radians(lat2)
    dphi = p2 - p1
    dlmb = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def snap_to_stall(
    lat: float,
    lng: float,
    stalls: Iterable[tuple[int, float, float]],
    radius_m: float = SNAP_RADIUS_M,
) -> int | None:
    """Return the id of the nearest stall within radius_m of the point, else None."""
    best_id: int | None = None
    best_d = radius_m
    for stall_id, s_lat, s_lng in stalls:
        d = haversine_m(lat, lng, s_lat, s_lng)
        if d <= best_d:
            best_id, best_d = stall_id, d
    return best_id


def within_area(lat: float, lng: float, center: tuple[float, float], radius_km: float) -> bool:
    return haversine_m(lat, lng, center[0], center[1]) <= radius_km * 1000.0
