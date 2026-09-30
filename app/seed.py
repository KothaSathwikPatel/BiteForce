"""Demo data: fictional venues around Shamshabad plus a little background activity."""

from __future__ import annotations

import json
import random
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .repository import Repository
from .security import hash_value

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "seed.json"
PLACES_PATH = SEED_PATH.with_name("places_osm.json")  # optional: real places from OpenStreetMap
MANUAL_PATH = SEED_PATH.with_name("places_manual.json")  # optional: hand-collected local stalls

SYMPTOM_SETS = [
    ("vomiting", "diarrhoea"),
    ("diarrhoea", "stomach_cramps"),
    ("vomiting", "nausea", "stomach_cramps"),
    ("diarrhoea", "fever", "nausea"),
    ("vomiting", "diarrhoea", "fever"),
]


def load_seed_data(path: Path = SEED_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_places(
       seed_path: Path | None = None, places_path: Path | None = None, manual_path: Path | None = None
   ) -> list[dict[str, Any]]:
    """Venues to put on the map: real OpenStreetMap places if downloaded, else the fictional set.

    The few fictional demo venues that carry the pre-seeded Watch/Alert stay on the map either
    way, so a real business never shows a fake warning.
    """
    seed_path = seed_path or SEED_PATH
    places_path = places_path or PLACES_PATH  # resolved at call time so tests can point elsewhere
    manual_path = manual_path or MANUAL_PATH
    seed = load_seed_data(seed_path)
    real: list[dict[str, Any]] = []
    for path in (manual_path, places_path):  # hand-collected places first: their coordinates win
        if path.is_file():
            real += json.loads(path.read_text(encoding="utf-8")).get("places", [])
    if not real:
        return seed["stalls"]
    demo_names = {spec["stall"] for spec in seed["background"]}
    demo = [s for s in seed["stalls"] if s["name"] in demo_names]
    taken = {s["name"].lower() for s in demo}
    return demo + [p for p in real if p["name"].lower() not in taken]


def insert_simulated_cases(
    repo: Repository,
    salt: str,
    stall_id: int,
    n: int,
    now: datetime,
    *,
    meal_hours_ago: float = 22.0,
    rng: random.Random | None = None,
) -> None:
    """Create n plausible, mutually unrelated illness reports for one venue.

    Meals fall within ~90 minutes, symptoms start 6-14 h later, and the last two cases share
    a network (like one hostel Wi-Fi) so the anti-abuse weighting is exercised realistically.
    """
    rng = rng or random.Random()
    run = secrets.token_hex(4)
    for i in range(n):
        device = hash_value(salt, f"sim-{run}-{i}")
        net_index = n - 2 if (n >= 4 and i == n - 1) else i
        network = hash_value(salt, f"simnet-{run}-{net_index}")
        established = now - timedelta(days=rng.randint(2, 30))
        newcomer = now - timedelta(hours=rng.randint(2, 12))
        first_seen = established if i % 3 else newcomer
        repo.touch_device(device, first_seen)
        eaten = now - timedelta(hours=meal_hours_ago) + timedelta(minutes=rng.randint(0, 90))
        onset = eaten + timedelta(hours=rng.uniform(6, 14))
        created = min(now, onset + timedelta(minutes=rng.randint(10, 240)))
        repo.add_report(
            stall_id=stall_id,
            device_hash=device,
            network_hash=network,
            symptoms=list(SYMPTOM_SETS[i % len(SYMPTOM_SETS)]),
            eaten_at=eaten,
            onset_at=onset,
            created_at=created,
            is_simulated=True,
        )


def seed_background(repo: Repository, salt: str, now: datetime) -> None:
    """A pre-existing Watch and Alert so the map is not empty on first load."""
    by_name = {s.name: s.id for s in repo.list_stalls()}
    rng = random.Random(42)
    for spec in load_seed_data()["background"]:
        stall_id = by_name.get(spec["stall"])
        if stall_id:
            insert_simulated_cases(
                repo, salt, stall_id, spec["cases"], now, meal_hours_ago=spec["meal_hours_ago"], rng=rng
            )


def sync_places(repo: Repository, now: datetime) -> int:
    """Add places that are in the data files but not yet in the database (safe to run on every start).

    This is what lets you add a stall to places_manual.json and simply redeploy.
    """
    known = {s.name.lower() for s in repo.list_stalls()}
    added = 0
    for place in load_places():
        if place["name"].lower() not in known:
            repo.add_stall(place["name"], place["kind"], place["lat"], place["lng"], now, is_seed=True)
            known.add(place["name"].lower())
            added += 1
    return added


def seed_database(repo: Repository, salt: str, now: datetime) -> bool:
    """Populate an empty database. Returns True if anything was seeded."""
    if repo.count_stalls() > 0:
        return False
    for stall in load_places():
        repo.add_stall(stall["name"], stall["kind"], stall["lat"], stall["lng"], now, is_seed=True)
    seed_background(repo, salt, now)
    return True
