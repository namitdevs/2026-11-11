from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_root_and_health(client):
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["name"] == "CampusPulse"
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["nodes"] == 20
    assert body["embedder"] in {"hashing", "minilm"}
    assert "q10" in body["models"]


def test_graph_and_snapshot_contracts(client):
    graph = client.get("/api/v1/graph")
    assert graph.status_code == 200
    assert len(graph.json()["nodes"]) == 20
    snapshot = client.get("/api/v1/snapshot")
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert {"csi", "routes", "forecasts", "triage", "mess", "benchmark"} <= set(body)
    assert body["csi"]["score"] > 0
    assert body["refine"]["raw_rows"] > 0


def test_forecast_and_hotspots(client):
    response = client.get("/api/v1/forecast/library", params={"horizons": "15,30"})
    assert response.status_code == 200
    assert len(response.json()["points"]) == 2
    missing = client.get("/api/v1/forecast/moon_base")
    assert missing.status_code == 404
    invalid = client.get("/api/v1/forecast/library", params={"horizons": "abc"})
    assert invalid.status_code == 422
    hotspots = client.get("/api/v1/hotspots")
    assert hotspots.status_code == 200
    assert hotspots.json()[0]["pressure"] >= hotspots.json()[-1]["pressure"]


def test_places_search(client):
    response = client.get("/api/v1/places", params={"q": "cold coffee", "limit": 3})
    assert response.status_code == 200
    hits = response.json()
    assert hits[0]["id"] == "food-court"
    assert hits[0]["verification"] == "map"
    assert hits[0]["score"] > 0
    assert client.get("/api/v1/places", params={"q": "", "limit": 4}).json().__len__() == 4
    assert client.get("/api/v1/places", params={"q": "x", "limit": 0}).status_code == 422


def test_find_departments_and_services(client):
    found = client.get("/api/v1/find", params={"q": "professor of electronics"})
    assert found.status_code == 200
    body = found.json()
    assert body["intent"] == "faculty"
    assert any("Electronics" in dept["name"] for dept in body["departments"])
    assert body["note"]
    services = client.get("/api/v1/services")
    assert services.status_code == 200
    statuses = {item["id"]: item["status"] for item in services.json()}
    assert statuses["library-seats"] == "not_connected"
    departments = client.get("/api/v1/departments")
    assert departments.status_code == 200
    assert len(departments.json()) >= 10


def test_route_and_validation(client):
    response = client.post(
        "/api/v1/route",
        json={"origin": "gate_main", "destination": "library", "night_mode": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recommended"] == "safest"
    assert body["safest"]["risk_reduction_pct"] > 0
    assert body["safest"]["path"][0] == "gate_main"
    missing = client.post("/api/v1/route", json={"origin": "gate_main", "destination": "moon_base"})
    assert missing.status_code == 404
    bad_mode = client.post(
        "/api/v1/route",
        json={"origin": "gate_main", "destination": "library", "night_mode": "sometimes"},
    )
    assert bad_mode.status_code == 422


def test_incident_creation_and_queue(client):
    payload = {
        "node_id": "hostel_b1",
        "category": "wifi",
        "description": "No internet in the hostel B1 wing, eduroam drops every minute",
        "reported_at": "2026-02-06T19:57:00",
    }
    created = client.post("/api/v1/incidents", json=payload)
    assert created.status_code == 200
    body = created.json()
    assert body["priority"] in {"P0", "P1", "P2", "P3"}
    assert body["evidence_ids"]
    assert body["embedding_backend"] in {"hashing", "minilm"}
    short = client.post("/api/v1/incidents", json={**payload, "description": "short"})
    assert short.status_code == 422
    bad_category = client.post("/api/v1/incidents", json={**payload, "category": "teleport"})
    assert bad_category.status_code == 422
    queue = client.get("/api/v1/incidents/queue", params={"limit": 5})
    assert queue.status_code == 200
    assert 1 <= len(queue.json()) <= 5


def test_mess_carts_dispatch_and_stress(client):
    plans = client.get("/api/v1/mess/plan")
    assert plans.status_code == 200
    assert all(plan["waste_saved_kg"] >= 0 for plan in plans.json())
    carts = client.get("/api/v1/carts")
    assert carts.status_code == 200
    assert len(carts.json()) >= 4
    dispatch = client.post(
        "/api/v1/carts/dispatch", json={"pickup_node": "gate_main", "destination_node": "hostel_g1"}
    )
    assert dispatch.status_code == 200
    assert dispatch.json()["eta_min"] > 0
    assert client.post("/api/v1/carts/dispatch", json={"pickup_node": "moon_base"}).status_code == 404
    assert client.post(
        "/api/v1/carts/dispatch", json={"pickup_node": "gate_main", "passengers": 5}
    ).status_code == 422
    stress = client.get("/api/v1/stress")
    assert stress.status_code == 200
    assert len(stress.json()["components"]) == 5


def test_benchmarks_insights_and_cascade_demo(client):
    benchmark = client.get("/api/v1/benchmarks")
    assert benchmark.status_code == 200
    body = benchmark.json()
    assert body["seed"] == 42
    assert body["forecast"]["model"]["r2_occupancy_ratio"] > 0.8
    insights = client.get("/api/v1/insights")
    assert insights.status_code == 200
    assert len(insights.json()["insights"]) >= 4
    demo = client.get("/api/v1/demo-scenario")
    assert demo.status_code == 200
    payload = demo.json()
    assert payload["triage"]["node_id"] == "hostel_b1"
    assert payload["routing"]["risk_reduction_pct"] > 0
    assert payload["refine"]["quality_score"] > 0
    assert payload["mess"] and payload["stress"]["score"] > 0
