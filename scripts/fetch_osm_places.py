"""Download REAL food places around Shamshabad from OpenStreetMap into data/places_osm.json.

Run once on your own computer (it needs internet):

    python scripts/fetch_osm_places.py            # 4 km around Shamshabad town centre
    python scripts/fetch_osm_places.py --radius 6000

Then delete bitetrace.db and restart the server so the new places are loaded.
Data (c) OpenStreetMap contributors, ODbL. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CENTER = (17.2603, 78.3969)
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
OUT = Path(__file__).resolve().parent.parent / "data" / "places_osm.json"
NAME_RE = re.compile(r"^[\w .,'&()/\-]{2,60}$", re.UNICODE)
KIND = {
    "restaurant": "restaurant",
    "food_court": "restaurant",
    "fast_food": "street_food",
    "cafe": "tea_snack",
    "ice_cream": "tea_snack",
}


def query(lat: float, lng: float, radius: int) -> str:
    kinds = "|".join(KIND)
    return f'[out:json][timeout:60];nwr["amenity"~"^({kinds})$"](around:{radius},{lat},{lng});out center 600;'


def fetch(q: str) -> dict:
    data = urllib.parse.urlencode({"data": q}).encode()
    last: Exception | None = None
    for url in MIRRORS:
        try:
            req = urllib.request.Request(  # noqa: S310 - fixed https URLs
                url, data=data, headers={"User-Agent": "BiteTrace-hackathon/1.0"}
            )
            with urllib.request.urlopen(req, timeout=90) as res:  # noqa: S310 - fixed https URLs
                return json.load(res)
        except Exception as exc:  # try the next mirror
            last = exc
            print(f"  {url} failed: {exc}", file=sys.stderr)
    raise SystemExit(f"All Overpass mirrors failed ({last}). Try again in a minute.")


def clean_name(raw: str) -> str | None:
    name = re.sub(r"\s+", " ", raw).strip()
    name = re.sub(r"[^\w .,'&()/\-]", "", name, flags=re.UNICODE).strip()
    return name if NAME_RE.match(name) else None


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    dlat, dlng = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    x = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlng / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(x))


def build(elements: list[dict], limit: int) -> list[dict]:
    seen: set[tuple[str, int, int]] = set()
    places: list[dict] = []
    for el in elements:
        tags = el.get("tags", {})
        name = clean_name(tags.get("name:en") or tags.get("name") or "")
        centre = el if "lat" in el else el.get("center") or {}
        try:
            lat, lng = float(centre["lat"]), float(centre["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        kind = KIND.get(tags.get("amenity", ""))
        key = (name or "", round(lat * 2000), round(lng * 2000))
        if not name or not kind or key in seen:
            continue
        seen.add(key)
        places.append({"name": name, "kind": kind, "lat": round(lat, 6), "lng": round(lng, 6)})
    places.sort(key=lambda p: distance_m(CENTER, (p["lat"], p["lng"])))
    return places[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--radius", type=int, default=4000, help="metres around Shamshabad centre")
    parser.add_argument("--limit", type=int, default=250)
    args = parser.parse_args()

    print(f"Asking OpenStreetMap for food places within {args.radius} m ...")
    places = build(fetch(query(*CENTER, args.radius)).get("elements", []), args.limit)
    if not places:
        raise SystemExit("No named places found. Try a bigger --radius.")
    OUT.write_text(
        json.dumps({"_note": "(c) OpenStreetMap contributors, ODbL", "places": places}, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    counts = {k: sum(p["kind"] == k for p in places) for k in set(KIND.values())}
    print(f"Saved {len(places)} places to {OUT} {counts}")
    print("Now delete bitetrace.db and restart the server.")


if __name__ == "__main__":
    main()
