"""One feature store shared by forecasting, triage, mess and mobility.

All temporal features are causal: every lag/rolling window ends at or before
the prediction timestamp, which is asserted in the test suite.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CATEGORIES, FREQ_MIN, HORIZONS
from .graph import CampusGraph
from .places import search_document

META_COLUMNS = {
    "ts", "node_id", "occupancy", "capacity", "source", "y_occ", "y_wait",
    "horizon_min", "reported_at", "description", "reporter_hash", "category",
    "severity", "resolve_minutes", "cluster_id", "pred_cluster_id", "cluster_size",
    "report_id", "canonical_description", "mean_similarity", "report_ids",
    "date", "mess_id", "meal", "headcount", "prepared_kg", "waste_kg",
    "lag7_headcount", "lag1_headcount", "menu_score", "day_index",
}

CATEGORY_SYNONYMS = {
    "wifi": ("wifi", "internet", "eduroam", "signal", "network"),
    "electrical": ("power", "electric", "spark", "breaker", "switch", "light"),
    "plumbing": ("water", "leak", "drain", "pipe", "tap", "washroom"),
    "food": ("food", "rice", "milk", "curry", "stale", "hygiene"),
    "safety": ("dark", "dog", "suspicious", "slippery", "harass", "exit"),
    "cleanliness": ("garbage", "dirty", "litter", "dustbin", "soap"),
    "infrastructure": ("broken", "cracked", "lift", "door", "ceiling", "nail"),
}


def engineer_telemetry(df: pd.DataFrame, graph: CampusGraph) -> pd.DataFrame:
    work = df.sort_values(["node_id", "ts"]).copy()
    work["occ_ratio"] = (work["occupancy"] / work["capacity"]).clip(0, 1.1)
    grouped = work.groupby("node_id", group_keys=False)
    work["lag1"] = grouped["occ_ratio"].shift(1)
    work["lag2"] = grouped["occ_ratio"].shift(2)
    work["lag4"] = grouped["occ_ratio"].shift(4)
    work["roll3_mean"] = grouped["occ_ratio"].transform(lambda s: s.rolling(3, min_periods=1).mean())
    work["roll3_std"] = grouped["occ_ratio"].transform(lambda s: s.rolling(3, min_periods=1).std())
    work["roll6_mean"] = grouped["occ_ratio"].transform(lambda s: s.rolling(6, min_periods=1).mean())
    work["momentum"] = work["occ_ratio"] - work["lag1"]
    work["queue_per_cap"] = work["queue_len"] / work["capacity"]
    work["node_capacity"] = work["capacity"]
    work["node_footfall"] = work["node_id"].map({k: v["footfall"] for k, v in graph.nodes.items()})
    work["edge_lit_ratio"] = work["node_id"].map({n: graph.edge_lit_ratio(n) for n in graph.nodes})

    pivot = work.pivot_table(index="ts", columns="node_id", values="occ_ratio", aggfunc="mean")
    work["neighbor_mean_occ"] = work["occ_ratio"]
    for node_id in graph.sensor_nodes():
        neighbors = [n for n, _ in graph.neighbors(node_id) if n in pivot.columns]
        if not neighbors:
            continue
        series = pivot[neighbors].mean(axis=1)
        mask = work["node_id"] == node_id
        work.loc[mask, "neighbor_mean_occ"] = work.loc[mask, "ts"].map(series).fillna(work.loc[mask, "occ_ratio"])

    minutes = work["ts"].dt.hour * 60 + work["ts"].dt.minute
    work["minute_sin"] = np.sin(2 * np.pi * minutes / 1440)
    work["minute_cos"] = np.cos(2 * np.pi * minutes / 1440)
    work["dow_sin"] = np.sin(2 * np.pi * work["ts"].dt.day_of_week / 7)
    work["dow_cos"] = np.cos(2 * np.pi * work["ts"].dt.day_of_week / 7)
    for col in ("lag1", "lag2", "lag4", "roll3_std", "momentum"):
        work[col] = work[col].fillna(0.0)
    dummies = pd.get_dummies(work["node_id"], prefix="node")
    work = pd.concat([work.reset_index(drop=True), dummies.reset_index(drop=True)], axis=1)
    return work.reset_index(drop=True)


def make_supervised(base: pd.DataFrame, horizons: tuple[int, ...] = HORIZONS) -> pd.DataFrame:
    frames = []
    for horizon in horizons:
        steps = horizon // FREQ_MIN
        frame = base.copy()
        frame["horizon_min"] = horizon
        grouped = base.groupby("node_id", group_keys=False)
        frame["y_occ"] = grouped["occ_ratio"].shift(-steps)
        frame["y_wait"] = grouped["wait_min"].shift(-steps)
        frame = frame.dropna(subset=["y_occ", "y_wait"])
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def telemetry_feature_columns(df: pd.DataFrame, graph: CampusGraph) -> list[str]:
    node_columns = sorted(
        c for c in df.columns
        if c.startswith("node_") and c not in ("node_id", "node_capacity", "node_footfall")
    )
    return [
        "occ_ratio", "queue_len", "queue_per_cap", "lag1", "lag2", "lag4",
        "roll3_mean", "roll3_std", "roll6_mean", "momentum", "neighbor_mean_occ",
        "edge_lit_ratio", "node_capacity", "node_footfall",
        "minute_sin", "minute_cos", "dow_sin", "dow_cos",
        "is_weekend", "is_exam", "is_holiday", "temp_c", "rain", "horizon_min",
        *node_columns,
    ]


def inference_frame(engineered: pd.DataFrame, feature_columns: list[str], node_id: str,
                    horizon: int) -> pd.DataFrame:
    latest = engineered[engineered["node_id"] == node_id].sort_values("ts").tail(1).copy()
    if latest.empty:
        raise ValueError(f"no telemetry for node {node_id}")
    latest["horizon_min"] = horizon
    for column in feature_columns:
        if column not in latest.columns:
            latest[column] = 0
    return latest[feature_columns].fillna(0)


def build_incident_features(df: pd.DataFrame, graph: CampusGraph, embedder,
                            feature_columns: list[str] | None = None,
                            include_embeddings: bool = True,
                            ) -> tuple[pd.DataFrame, list[str]]:
    frame = pd.DataFrame(index=df.index)
    for category in CATEGORIES:
        frame[f"cat_{category}"] = (df["category"] == category).astype(int)
    hours = df["reported_at"].dt.hour
    frame["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * hours / 24)
    frame["dow_sin"] = np.sin(2 * np.pi * df["reported_at"].dt.day_of_week / 7)
    frame["dow_cos"] = np.cos(2 * np.pi * df["reported_at"].dt.day_of_week / 7)
    frame["is_night"] = ((hours >= 20) | (hours <= 6)).astype(int)
    frame["node_footfall"] = df["node_id"].map({k: v["footfall"] for k, v in graph.nodes.items()}).fillna(0.4)
    frame["node_capacity"] = df["node_id"].map({k: v["capacity"] for k, v in graph.nodes.items()}).fillna(0)
    frame["cluster_size"] = (
        df["cluster_size"] if "cluster_size" in df.columns else 1
    )
    frame["cluster_size"] = pd.to_numeric(frame["cluster_size"], errors="coerce").fillna(1)
    description = df["description"].astype(str)
    frame["desc_len"] = description.str.len()
    frame["desc_words"] = description.str.split().str.len()
    lowered = description.str.lower()
    for category, keywords in CATEGORY_SYNONYMS.items():
        pattern = "|".join(keywords)
        frame[f"kw_{category}"] = lowered.str.contains(pattern, regex=True).astype(int)
    if include_embeddings:
        embeddings = embedder.encode(description.tolist())
        embedding_frame = pd.DataFrame(
            embeddings, index=df.index, columns=[f"emb_{i}" for i in range(embeddings.shape[1])]
        )
        frame = pd.concat([frame, embedding_frame], axis=1)
    return frame, feature_columns or list(frame.columns)


def build_mess_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    work = df.copy()
    frame = pd.DataFrame(index=work.index)
    frame["day_index"] = work["day_index"]
    frame["dow_sin"] = np.sin(2 * np.pi * work["date"].dt.day_of_week / 7)
    frame["dow_cos"] = np.cos(2 * np.pi * work["date"].dt.day_of_week / 7)
    frame["is_weekend"] = work["is_weekend"]
    frame["is_exam"] = work["is_exam"]
    frame["is_holiday"] = work["is_holiday"]
    frame["rain"] = work["rain"]
    frame["temp_c"] = work["temp_c"]
    frame["menu_score"] = work["menu_score"]
    frame["lag7_headcount"] = work["lag7_headcount"]
    frame["lag1_headcount"] = work["lag1_headcount"]
    for meal in ("breakfast", "lunch", "snack", "dinner"):
        frame[f"meal_{meal}"] = (work["meal"] == meal).astype(int)
    frame["mess_main"] = (work["mess_id"] == "mess_main").astype(int)
    return frame, list(frame.columns)


def place_search_frame(places: list[dict], embedder) -> np.ndarray:
    return embedder.encode([search_document(place) for place in places])
