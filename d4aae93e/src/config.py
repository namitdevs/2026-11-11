"""Central configuration for CampusPulse.

Every path, seed and threshold lives here so the whole pipeline is
reproducible from a single source of truth.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = ROOT / "models"
RESULTS_DIR = ROOT / "results"
FRONTEND_DATA_DIR = ROOT / "frontend" / "public" / "data"

SEED = 42
EMBED_DIM = 384
FREQ_MIN = 15
HORIZONS = (15, 30, 60)
SIM_DAYS = 35
INCIDENT_DAYS = 60
MESS_DAYS = 60

ANCHOR = "2026-01-05T00:00:00"
SNAPSHOT_TS = "2026-02-06T20:30:00"
NIGHT_START_HOUR = 20
NIGHT_END_HOUR = 6

DEDUPE_WINDOW_MIN = 15
DEDUPE_RADIUS_M = 150.0
DEDUPE_COSINE_MINILM = 0.80
DEDUPE_COSINE_HASH = 0.25

WALK_SPEED_M_PER_MIN = 75.0
ACCESSIBLE_SPEED_M_PER_MIN = 62.0
NIGHT_SPEED_M_PER_MIN = 72.0
CART_SPEED_M_PER_MIN = 280.0

MEAL_PORTION_KG = {
    "breakfast": 0.30,
    "lunch": 0.44,
    "snack": 0.16,
    "dinner": 0.42,
}
MEAL_CONSUMPTION_RATIO = 0.92
BASELINE_OVER_PREP = 1.12
SMART_SAFETY_MARGIN = 1.04

MEALS = ("breakfast", "lunch", "snack", "dinner")
MESSES = ("mess_main", "mess_north")
CATEGORIES = (
    "wifi",
    "electrical",
    "plumbing",
    "food",
    "safety",
    "cleanliness",
    "infrastructure",
)

PLAYBOOKS = {
    "wifi": "Ping the nearest AP controller, restart the affected switch port, confirm eduroam auth, then follow up with the reporters.",
    "electrical": "Isolate the breaker, dispatch the electrical crew with a multimeter, and verify no exposed wiring before re-energising.",
    "plumbing": "Shut the local valve, inspect the joint/leak source, deploy the plumbing crew, and re-test water pressure.",
    "food": "Quarantine the batch, notify the mess supervisor, sample the serving line, and publish a hygiene notice.",
    "safety": "Alert the security control room, share the live location and nearest safe route, and keep the reporter on a callback loop.",
    "cleanliness": "Route to the sanitation crew with a photo checklist and schedule a supervisor verification.",
    "infrastructure": "Inspect the fixture/structure, raise a works order, and mark the area until it is certified safe.",
}


def ensure_dirs() -> None:
    for path in (DATA_DIR, RAW_DIR, PROCESSED_DIR, MODELS_DIR, RESULTS_DIR, FRONTEND_DATA_DIR):
        path.mkdir(parents=True, exist_ok=True)


ensure_dirs()
