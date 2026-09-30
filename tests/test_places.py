import json

from app.seed import load_places
from scripts.fetch_osm_places import build, clean_name, query

from .conftest import build_env


def test_clean_name_and_query():
    assert clean_name("  Hotel   Ravi <b>Palace</b> ") == "Hotel Ravi bPalace/b"
    assert clean_name("x") is None and clean_name("@@@") is None
    assert "restaurant" in query(17.2, 78.3, 1000) and "around:1000" in query(17.2, 78.3, 1000)


def test_build_filters_dedupes_and_sorts_by_distance():
    elements = [
        {"lat": 17.27, "lon": 78.40, "tags": {"amenity": "restaurant", "name": "Far Place"}},
        {"lat": 17.2604, "lon": 78.3970, "tags": {"amenity": "fast_food", "name": "Near Cart"}},
        {"lat": 17.2604, "lon": 78.3970, "tags": {"amenity": "fast_food", "name": "Near Cart"}},
        {"center": {"lat": 17.261, "lon": 78.398}, "tags": {"amenity": "cafe", "name": "Way Cafe"}},
        {"lat": 17.26, "lon": 78.39, "tags": {"amenity": "restaurant"}},
        {"lat": 17.26, "lon": 78.39, "tags": {"amenity": "bank", "name": "Some Bank"}},
        {"tags": {"amenity": "cafe", "name": "No Coordinates"}},
    ]
    places = build(elements, limit=10)
    assert [p["name"] for p in places] == ["Near Cart", "Way Cafe", "Far Place"]
    assert {p["kind"] for p in places} == {"street_food", "tea_snack", "restaurant"}
    assert len(build(elements, limit=1)) == 1


def test_load_places_uses_real_file_but_keeps_demo_venues(tmp_path):
    from app.seed import SEED_PATH

    file = tmp_path / "p.json"
    file.write_text(json.dumps({"places": [
        {"name": "Real Biryani House", "kind": "restaurant", "lat": 17.26, "lng": 78.39},
        {"name": "Highway Dhaba Grill", "kind": "restaurant", "lat": 17.0, "lng": 78.0},
    ]}))
    names = [s["name"] for s in load_places(SEED_PATH, file)]
    assert "Real Biryani House" in names and names.count("Highway Dhaba Grill") == 1
    assert "Golden Pani Puri Cart" not in names
    assert len(load_places(SEED_PATH, tmp_path / "missing.json")) > 10


def test_app_seeds_from_load_places(monkeypatch):
    import app.seed as seed

    monkeypatch.setattr(seed, "load_places", lambda: [
        {"name": "Real Cafe", "kind": "tea_snack", "lat": 17.26, "lng": 78.39},
        {"name": "Highway Dhaba Grill", "kind": "restaurant", "lat": 17.257, "lng": 78.397},
    ])
    by_name = {s["name"]: s for s in build_env().client.get("/api/stalls").json()}
    assert by_name["Real Cafe"]["level"] == "NONE"
    assert by_name["Highway Dhaba Grill"]["level"] == "ALERT"


def test_manual_places_win_and_are_merged(tmp_path):
    from app.seed import SEED_PATH

    osm = tmp_path / "osm.json"
    osm.write_text(json.dumps({"places": [{"name": "Raju Tiffins", "kind": "restaurant", "lat": 17.2, "lng": 78.3}]}))
    manual = tmp_path / "manual.json"
    row = {"name": "raju tiffins", "kind": "street_food", "lat": 17.26, "lng": 78.39}
    manual.write_text(json.dumps({"places": [row]}))
    places = load_places(SEED_PATH, osm, manual)
    raju = [p for p in places if p["name"].lower() == "raju tiffins"]
    assert len(raju) == 2 and raju[0]["kind"] == "street_food"  # manual listed first


def test_sync_places_adds_only_missing_ones(monkeypatch):
    import app.seed as seed
    from app.seed import sync_places

    env = build_env()
    before = len(env.client.get("/api/stalls").json())
    extra = [{"name": "Brand New Stall", "kind": "street_food", "lat": 17.26, "lng": 78.39}]
    monkeypatch.setattr(seed, "load_places", lambda: extra)
    assert sync_places(env.repo, env.clock()) == 1
    assert sync_places(env.repo, env.clock()) == 0
    names = [s["name"] for s in env.client.get("/api/stalls").json()]
    assert len(names) == before + 1 and "Brand New Stall" in names
