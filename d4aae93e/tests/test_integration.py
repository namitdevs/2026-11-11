from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from src.config import RAW_DIR


def _sha256_prefix(*paths) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def test_every_place_and_route_lives_on_the_same_graph(engine):
    snapshot = engine.snapshot()
    node_ids = set(engine.graph.nodes)
    assert all(place.node_id in node_ids for place in snapshot.places)
    assert all(cart.node_id in node_ids for cart in snapshot.carts)
    assert set(snapshot.dispatches) == set(snapshot.routes)
    assert set(snapshot.forecasts).issubset(node_ids)
    assert all(hotspot.node_id in node_ids for hotspot in snapshot.hotspots)

    positive_reductions = 0
    for origin, destinations in snapshot.routes.items():
        assert origin in node_ids
        assert len(destinations) == len(snapshot.places)
        for place_id, modes in destinations.items():
            place = next(item for item in snapshot.places if item.id == place_id)
            for result in modes.values():
                assert result.path[0] == origin
                assert result.path[-1] == place.node_id
                total = 0.0
                for u, v in zip(result.path, result.path[1:]):
                    edge = engine.graph.edge_between(u, v)
                    assert edge is not None
                    total += edge["distance_m"]
                assert result.distance_m == pytest.approx(total, abs=0.11)
            assert modes["safest"].risk_index <= modes["fastest"].risk_index
            if modes["safest"].risk_reduction_pct > 0:
                positive_reductions += 1
    assert positive_reductions > 0


def test_refine_accounts_for_every_row(engine):
    telemetry = engine.telemetry_report
    assert telemetry.accepted_rows + telemetry.dropped_rows == telemetry.raw_rows
    incidents = engine.incident_report
    assert incidents.accepted_rows + incidents.dropped_rows == incidents.raw_rows
    assert incidents.incident_reports_merged + incidents.clusters_formed == incidents.accepted_rows
    snapshot = engine.snapshot()
    assert (
        snapshot.refine.incident_reports_merged + snapshot.refine.clusters_formed
        == engine.incident_report.accepted_rows
    )
    raw_incidents = pd.read_csv(RAW_DIR / "incidents.csv")
    evidence = {
        evidence_id
        for cluster in snapshot.triage["queue"]
        for evidence_id in cluster["evidence_ids"]
    }
    assert evidence
    assert evidence.issubset(set(raw_incidents["report_id"]))


def test_snapshot_serialises_without_nan_and_matches_kpis(engine):
    snapshot = engine.snapshot()
    payload = snapshot.model_dump(mode="json")
    serialised = json.dumps(payload, allow_nan=False)
    assert len(serialised) > 100_000
    assert snapshot.kpis["csi_score"] == snapshot.csi.score
    assert snapshot.kpis["reports_collapsed"] == snapshot.refine.incident_reports_merged
    assert snapshot.kpis["quality_score"] == snapshot.refine.quality_score
    assert snapshot.kpis["waste_saved_kg"] == pytest.approx(
        sum(max(plan.waste_saved_kg, 0) for plan in snapshot.mess), abs=0.11
    )
    assert snapshot.kpis["carts_available"] == sum(
        1 for cart in snapshot.carts if cart.status == "available"
    )
    for bundle in snapshot.forecasts.values():
        assert len(bundle["history"]) == 12
        assert len(bundle["points"]) == 3


def test_benchmark_receipt_matches_the_raw_data(engine):
    benchmark = engine.snapshot().benchmark
    assert benchmark["seed"] == 42
    assert benchmark["dataset_sha256_16"] == _sha256_prefix(
        RAW_DIR / "telemetry.csv", RAW_DIR / "incidents.csv", RAW_DIR / "mess.csv"
    )
    assert benchmark["environment"]["embedder_backend"] == engine.embedder.backend
    assert benchmark["forecast"]["model"]["mae_occupancy_ratio"] < 0.05
    assert benchmark["triage"]["model"]["macro_f1"] > 0.7
    assert benchmark["dedupe"]["semantic_gate"]["pair_f1"] > 0.9
    assert benchmark["routing"]["mean_risk_reduction_pct"] > 0
