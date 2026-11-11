from __future__ import annotations

from src.directory import department_dicts, service_dicts
from src.graph import default_graph
from src.places import PLACES

VERIFICATION = {"map", "official", "third-party", "unverified", "demo"}
SERVICE_STATES = {"connected", "partial", "demo", "not_connected"}


def test_every_place_points_at_a_real_graph_node():
    graph = default_graph()
    sub_locations = {
        "lp-101-103",
        "lp-110-111",
        "dean-office",
        "cart-stop-main",
        "cart-stop-library",
        "cart-stop-north",
    }
    ids = [place["id"] for place in PLACES]
    assert len(ids) == len(set(ids))
    for place in PLACES:
        assert place["node_id"] in graph.nodes, place["id"]
        if place["id"] not in sub_locations:
            assert place["name"] == graph.label(place["node_id"]), place["id"]


def test_places_are_sourced_and_classified():
    for place in PLACES:
        assert place["verification"] in VERIFICATION
        assert place["description"] and place["landmark"]
        assert place["source"]
        assert place["aliases"]
        assert place["open_hours"] in {"Not published", "Not connected", "Simulated"}
        if place["verification"] == "demo":
            assert "simulat" in place["source"].lower()


def test_aliases_are_unique_and_resolvable():
    seen: dict[str, str] = {}
    for place in PLACES:
        for alias in [place["name"].lower(), *place["aliases"]]:
            assert alias not in seen or seen[alias] == place["id"], (alias, seen.get(alias), place["id"])
            seen[alias] = place["id"]
    assert seen["cold coffee"] == "food-court"
    assert seen["oat"] == "open-air-theatre"


def test_no_place_claims_live_availability():
    words = ("live seats", "seats free", "available now", "queue length now")
    for place in PLACES:
        blob = (place["description"] + place["open_hours"]).lower()
        assert not any(word in blob for word in words)


def test_directory_services_are_honest():
    statuses = {item["id"]: item["status"] for item in service_dicts()}
    assert statuses["place-search"] == "connected"
    assert statuses["wayfinding"] == "connected"
    assert statuses["faculty-directory"] == "partial"
    assert statuses["cart-dispatch"] == "demo"
    assert statuses["library-seats"] == "not_connected"
    assert statuses["classroom-timetable"] == "not_connected"
    for item in service_dicts():
        assert item["status"] in SERVICE_STATES
        assert item["detail"]
    partial = [item for item in department_dicts() if "not individual" in item["name"]]
    assert not partial
    assert len(department_dicts()) >= 10
    assert all(item["verification"] == "official" for item in department_dicts())
