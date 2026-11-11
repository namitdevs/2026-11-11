from __future__ import annotations

import pytest

from src.schemas import RouteRequest, Snapshot


def test_forecast_is_monotone_and_bounded(engine):
    response = engine.forecast("library", (15, 30, 60))
    assert len(response.points) == 3
    assert response.capacity > 0
    assert 0.0 <= response.current_occupancy_ratio <= 1.1
    for point in response.points:
        assert 0.0 <= point.p10 <= point.p50 <= point.p90 <= 1.1
    with pytest.raises(KeyError):
        engine.forecast("moon_base")


def test_forecast_and_dispatch_are_deterministic(engine):
    first = engine.forecast("foodcourt").model_dump(exclude={"generated_at"})
    second = engine.forecast("foodcourt").model_dump(exclude={"generated_at"})
    assert first == second
    assert engine.dispatch("gate_main", "hostel_g1").model_dump() == engine.dispatch(
        "gate_main", "hostel_g1"
    ).model_dump()


def test_hotspots_are_ranked_by_pressure(engine):
    hotspots = engine.hotspots()
    assert len(hotspots) >= 10
    pressures = [item.pressure for item in hotspots]
    assert pressures == sorted(pressures, reverse=True)
    assert all(0.0 <= item.occupancy_ratio <= 1.1 for item in hotspots)


def test_night_route_trades_distance_for_lower_risk(engine):
    response = engine.route(
        RouteRequest(origin="gate_main", destination="library", night_mode=True)
    )
    assert response.recommended == "safest"
    assert response.safest.risk_index <= response.fastest.risk_index
    assert response.safest.distance_m >= response.fastest.distance_m
    assert response.safest.risk_reduction_pct == pytest.approx(
        round((response.fastest.risk_index - response.safest.risk_index) / response.fastest.risk_index * 100, 1),
        abs=0.11,
    )
    assert response.safest.risk_reduction_pct > 0
    assert response.destination_label == "Central Library"
    assert response.landmark
    with pytest.raises(KeyError):
        engine.route(RouteRequest(origin="gate_main", destination="moon_base"))


def test_place_search_handles_aliases_and_natural_language(engine):
    assert engine.search_places("cold coffee")[0].id == "food-court"
    assert engine.search_places("vending machine")[0].id == "tan-block"
    assert engine.search_places("central library")[0].node_id == "library"
    assert engine.search_places("cs block")[0].node_id == "block_a"
    assert {hit.id for hit in engine.search_places("hostels")} == {
        "prithvi-hall", "vyom-hall", "vahni-hall"
    }
    assert engine.search_places("prithvi")[0].id == "prithvi-hall"
    assert all(hit.node_id in engine.graph.nodes for hit in engine.search_places("coffee"))
    assert len(engine.search_places("", limit=5)) == 5
    print_docs = engine.search_places("place to print documents", limit=5)
    assert print_docs and print_docs[0].name == "Stationery & ATM"
    assert all(hit.verification in {"map", "demo"} for hit in engine.search_places("canteen"))


def test_find_surfaces_directory_and_honest_service_state(engine):
    popular = engine.find("")
    assert popular.intent == "place"
    assert {hit.id for hit in popular.hits} >= {"central-library", "canteen", "aahar"}

    faculty = engine.find("professor of computer science")
    assert faculty.intent == "faculty"
    assert any(dept.name.startswith("Computer Science") for dept in faculty.departments)
    assert "not individual faculty cabins" in faculty.note
    assert all(hit.score >= 60 for hit in faculty.hits)

    seats = engine.find("library free seats")
    assert seats.intent == "service"
    assert any(service.id == "library-seats" for service in seats.services)
    assert all(service.status != "connected" for service in engine.find("live shuttle gps").services)

    missing = engine.find("moon base")
    assert missing.note

    statuses = {service.id: service.status for service in engine.service_status()}
    assert statuses["place-search"] == "connected"
    assert statuses["cart-dispatch"] == "demo"
    assert statuses["library-seats"] == "not_connected"


def test_cart_dispatch_beats_walking_and_reports_fleet(engine):
    carts = engine.carts()
    assert len(carts) >= 4
    assert all(cart.node_id in engine.graph.nodes for cart in carts)
    dispatch = engine.dispatch("gate_main", "hostel_g1")
    assert dispatch.cart_id and dispatch.cart_label
    assert dispatch.eta_min < dispatch.walk_min
    assert dispatch.pickup_node == "gate_main"
    assert len(dispatch.alternatives) == 3
    assert dispatch.cart_id not in dispatch.alternatives


def test_live_incident_is_triaged_with_evidence(engine):
    cluster = engine.triage_report(
        {
            "node_id": "hostel_b1",
            "category": "wifi",
            "description": "No internet in hostel B1, eduroam keeps dropping every minute",
            "reported_at": "2026-02-06T19:57:00",
        }
    )
    assert cluster.priority in {"P0", "P1", "P2", "P3"}
    assert 0.0 <= cluster.priority_confidence <= 1.0
    assert cluster.sla_minutes >= 10
    assert cluster.evidence_ids
    assert set(cluster.evidence_ids).issubset(set(engine.incidents["report_id"]))
    assert cluster.evidence_snippets
    assert any("eduroam" in snippet for snippet in cluster.evidence_snippets)
    assert all(len(snippet) <= 140 for snippet in cluster.evidence_snippets)
    assert cluster.playbook and cluster.summary
    assert cluster.node_label == "Prithvi Hall"


def test_mess_plan_reduces_waste_without_negative_savings(engine):
    plans = engine.mess_plan()
    assert len(plans) >= 4
    for plan in plans:
        assert plan.p90_headcount >= plan.predicted_headcount
        assert plan.prep_kg > 0
        assert plan.expected_waste_kg >= 0
        assert plan.baseline_waste_kg >= plan.expected_waste_kg
        assert plan.waste_saved_kg >= 0
        assert 0.0 <= plan.confidence <= 1.0
    assert sum(plan.waste_saved_kg for plan in plans) > 0


def test_stress_index_components_are_consistent(engine):
    stress = engine.stress_index()
    assert 0.0 <= stress.score <= 100.0
    assert stress.label in {"Calm", "Steady", "Elevated", "Strained", "Critical"}
    assert sum(component.weight for component in stress.components) == pytest.approx(1.0)
    weighted = sum(component.value * component.weight for component in stress.components)
    assert stress.score == pytest.approx(round(weighted, 1), abs=0.11)
    assert {component.key for component in stress.components} == {
        "crowd", "incidents", "mess", "mobility", "carts"
    }


def test_snapshot_is_valid_and_cached(engine):
    snapshot = engine.snapshot()
    assert isinstance(snapshot, Snapshot)
    assert snapshot.mode == "replay"
    assert snapshot.generated_at.year >= 2026
    assert set(snapshot.routes) == {"gate_main", "gate_north", "hostel_g1"}
    assert snapshot.csi.score == pytest.approx(engine.stress_index().score, abs=0.11)
    assert snapshot.triage["queue"]
    assert snapshot.triage["stats"]["reports_last_24h"] >= snapshot.triage["stats"]["clusters_last_24h"]
    assert snapshot.forecasts and snapshot.hotspots and snapshot.mess
    assert snapshot.benchmark["seed"] == 42
    assert snapshot.kpis["reports_collapsed"] > 0
    assert engine.snapshot() is snapshot
    parsed = Snapshot.model_validate_json(snapshot.model_dump_json())
    assert parsed.csi.label == snapshot.csi.label
