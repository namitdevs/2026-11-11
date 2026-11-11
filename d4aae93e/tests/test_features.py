from __future__ import annotations

import numpy as np
import pandas as pd

from src.embeddings import HashingEmbedder
from src.features import (
    build_incident_features,
    build_mess_features,
    engineer_telemetry,
    make_supervised,
    telemetry_feature_columns,
)
from src.graph import default_graph


def _frame(node_id: str = "library", points: int = 30) -> pd.DataFrame:
    ts = pd.date_range("2026-01-05 08:00", periods=points, freq="15min")
    ratio = np.linspace(0.2, 0.9, points)
    return pd.DataFrame(
        {
            "ts": ts,
            "node_id": node_id,
            "occupancy": (ratio * 100).round().astype(int),
            "capacity": 100,
            "queue_len": (ratio * 10).round().astype(int),
            "wait_min": ratio * 5,
            "temp_c": 20.0,
            "rain": 0,
            "is_weekend": 0,
            "is_exam": 0,
            "is_holiday": 0,
        }
    )


def test_features_are_causal_and_do_not_leak_future_values():
    graph = default_graph()
    base = pd.concat([_frame("library"), _frame("block_a")], ignore_index=True)
    before = engineer_telemetry(base, graph)

    changed = base.copy()
    last = changed.index[-1]
    changed.loc[last, "occupancy"] = 100
    after = engineer_telemetry(changed, graph)

    cutoff = base["ts"].max()
    masks = base["ts"] < cutoff
    columns = ["lag1", "lag2", "roll3_mean", "momentum", "neighbor_mean_occ"]
    pd.testing.assert_frame_equal(
        before.loc[masks, ["node_id", *columns]].reset_index(drop=True),
        after.loc[masks, ["node_id", *columns]].reset_index(drop=True),
    )


def test_supervision_target_is_aligned_to_the_horizon():
    graph = default_graph()
    engineered = engineer_telemetry(_frame("library"), graph)
    supervised = make_supervised(engineered, horizons=(15,))
    first = engineered.iloc[0]
    target = supervised.iloc[0]
    assert target["horizon_min"] == 15
    assert target["y_occ"] == engineered.iloc[1]["occ_ratio"]
    assert supervised["y_occ"].notna().all()
    assert first["node_id"] == target["node_id"]


def test_telemetry_feature_columns_are_numeric_and_usable():
    graph = default_graph()
    engineered = engineer_telemetry(_frame("library"), graph)
    supervised = make_supervised(engineered, horizons=(15,))
    columns = telemetry_feature_columns(engineered, graph)
    assert "node_id" not in columns
    assert "node_capacity" in columns and "node_footfall" in columns
    assert any(column.startswith("node_") and column not in ("node_capacity", "node_footfall") for column in columns)
    assert set(columns).issubset(supervised.columns)
    for column in columns:
        assert pd.api.types.is_numeric_dtype(supervised[column]), column
    assert 0.0 <= engineered["occ_ratio"].max() <= 1.1


def test_incident_feature_contract_excludes_embeddings_when_requested():
    embedder = HashingEmbedder()
    graph = default_graph()
    frame = pd.DataFrame(
        [
            {
                "report_id": "r-1",
                "node_id": "hostel_b1",
                "category": "wifi",
                "description": "wifi is down in hostel b1, no signal at all",
                "reported_at": pd.Timestamp("2026-02-06 19:40"),
                "cluster_size": 4,
            }
        ]
    )
    without, columns = build_incident_features(frame, graph, embedder, include_embeddings=False)
    assert not [column for column in columns if column.startswith("emb_")]
    assert {"cat_wifi", "hour_sin", "kw_wifi", "cluster_size"}.issubset(columns)
    assert without.shape[1] == len(columns)

    with_embeddings, rich_columns = build_incident_features(frame, graph, embedder, include_embeddings=True)
    assert len([column for column in rich_columns if column.startswith("emb_")]) == 384
    assert with_embeddings.shape[1] == len(rich_columns)


def test_mess_feature_contract_matches_training_columns():
    frame = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-02-07"),
                "mess_id": "mess_main",
                "meal": "dinner",
                "day_index": 33,
                "is_weekend": 1,
                "is_exam": 0,
                "is_holiday": 0,
                "rain": 0,
                "temp_c": 18.0,
                "menu_score": 1.0,
                "lag7_headcount": 520.0,
                "lag1_headcount": 540.0,
            }
        ]
    )
    features, columns = build_mess_features(frame)
    assert features.shape[1] == len(columns)
    assert {"lag7_headcount", "meal_dinner", "mess_main", "menu_score"}.issubset(columns)
    assert features["meal_dinner"].iloc[0] == 1
    assert features["mess_main"].iloc[0] == 1
