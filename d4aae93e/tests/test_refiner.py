from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.embeddings import HashingEmbedder
from src.graph import default_graph
from src.refiner import refine_incidents, refine_telemetry


def _telemetry(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_telemetry_refiner_drops_dedupes_and_winsorises():
    rows = [
        {"ts": "2026-01-05 09:00", "node_id": "library", "occupancy": 100, "capacity": 100, "queue_len": 4, "wait_min": 3.0},
        {"ts": "2026-01-05 09:00", "node_id": "library", "occupancy": 110, "capacity": 100, "queue_len": 4, "wait_min": 3.0},
        {"ts": "2026-01-05 09:15", "node_id": "library", "occupancy": -4, "capacity": 100, "queue_len": 1, "wait_min": 1.0},
        {"ts": "2026-01-05 09:30", "node_id": "library", "occupancy": 500, "capacity": 100, "queue_len": 8, "wait_min": 7.0},
        {"ts": "2026-01-05 09:45", "node_id": "library", "occupancy": 50, "capacity": 0, "queue_len": 1, "wait_min": 1.0},
        {"ts": None, "node_id": "library", "occupancy": 50, "capacity": 100, "queue_len": 1, "wait_min": 1.0},
        {"ts": "2026-01-05 10:00", "node_id": "block_a", "occupancy": 50, "capacity": 100, "queue_len": 2, "wait_min": 2.0},
    ]
    clean, report = refine_telemetry(_telemetry(rows))
    assert report.raw_rows == 7
    assert report.accepted_rows == len(clean) == 3
    assert report.dropped_rows == 4
    assert report.duplicate_rows_removed == 1
    clipped = clean[(clean["node_id"] == "library") & (clean["ts"] == pd.Timestamp("2026-01-05 09:30"))]
    assert int(clipped["occupancy"].iloc[0]) == 105
    assert (clean["occupancy"] >= 0).all()
    assert 0.0 < report.quality_score <= 1.0
    assert any("winsorised" in issue for issue in report.issues)


def test_incident_dedupe_gates_on_category_node_and_window():
    description = "wifi is down throughout hostel b1 and eduroam will not connect"
    rows = [
        {"report_id": "r-a", "node_id": "hostel_b1", "category": "wifi", "description": description, "reported_at": "2026-02-06 19:40"},
        {"report_id": "r-b", "node_id": "hostel_b1", "category": "wifi", "description": description, "reported_at": "2026-02-06 19:45"},
        {"report_id": "r-c", "node_id": "hostel_b1", "category": "wifi", "description": description, "reported_at": "2026-02-06 20:01"},
        {"report_id": "r-d", "node_id": "hostel_b1", "category": "electrical", "description": description, "reported_at": "2026-02-06 19:42"},
        {"report_id": "r-e", "node_id": "block_a", "category": "wifi", "description": description, "reported_at": "2026-02-06 19:43"},
    ]
    graph = default_graph()
    assignments, clusters, report = refine_incidents(
        pd.DataFrame(rows), graph, HashingEmbedder(), threshold=0.25
    )
    assert report.raw_rows == 5
    assert report.accepted_rows == 5
    assert len(clusters) == 4
    assert report.incident_reports_merged == 1
    assert report.clusters_formed == 4
    by_id = assignments.set_index("report_id")["pred_cluster_id"]
    assert by_id["r-a"] == by_id["r-b"]
    assert len({by_id["r-a"], by_id["r-c"], by_id["r-d"], by_id["r-e"]}) == 4
    assert clusters["canonical_description"].str.len().min() >= 8


def test_incident_refiner_rejects_invalid_rows():
    rows = [
        {"report_id": "r-1", "node_id": "moon_base", "category": "wifi", "description": "wifi down at the moon base", "reported_at": "2026-02-06 19:40"},
        {"report_id": "r-2", "node_id": "hostel_b1", "category": "teleport", "description": "teleporter is offline again", "reported_at": "2026-02-06 19:41"},
        {"report_id": "r-3", "node_id": "hostel_b1", "category": "wifi", "description": "short", "reported_at": "2026-02-06 19:42"},
    ]
    assignments, clusters, report = refine_incidents(
        pd.DataFrame(rows), default_graph(), HashingEmbedder(), threshold=0.25
    )
    assert assignments.empty
    assert clusters.empty
    assert report.dropped_rows == 3
    assert report.quality_score == 0.0


def test_embedding_similarity_threshold_rejects_unrelated_text():
    embedder = HashingEmbedder()
    related = embedder.encode(["wifi is down in hostel b1", "hostel b1 wifi is down"])
    unrelated = embedder.encode(["wifi is down in hostel b1", "the pasta was cold in the mess"])
    assert float(np.dot(related[0], related[1])) > 0.25
    assert float(np.dot(unrelated[0], unrelated[1])) < 0.25
    assert embedder.encode(["wifi"]).shape == (1, 384)
    assert np.linalg.norm(embedder.encode(["wifi"])[0]) == pytest.approx(1.0, abs=1e-5)
