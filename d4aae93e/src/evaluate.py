"""Benchmark harness: baselines, ablations, latency and a signed results file.

Run: python -m src.evaluate
Writes results/benchmark_metrics.json + results/benchmark_table.md
"""
from __future__ import annotations

import hashlib
import json
import platform
import random
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import sklearn
import xgboost as xgb
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    r2_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .config import MODELS_DIR, RAW_DIR, RESULTS_DIR, SEED, SNAPSHOT_TS
from .engine import CampusPulseEngine
from .features import (
    build_incident_features,
    build_mess_features,
    engineer_telemetry,
    make_supervised,
    telemetry_feature_columns,
)
from .graph import default_graph
from .refiner import refine_incidents, refine_telemetry
from .simulator import simulate_carts
from .train import temporal_split, triage_split

SEVERITY_TO_PRIORITY = {0: "P3", 1: "P2", 2: "P1", 3: "P0"}
warnings.filterwarnings("ignore", category=ConvergenceWarning)


def _sha256(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _mape(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = y_true != 0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def _pair_sets(frame: pd.DataFrame, column: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for _, group in frame.groupby(column):
        ids = list(group["report_id"])
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pairs.add(tuple(sorted((ids[i], ids[j]))))
    return pairs


def _pair_prf(predicted: pd.DataFrame) -> dict:
    pred = _pair_sets(predicted, "pred_cluster_id")
    true = _pair_sets(predicted, "cluster_id")
    tp = len(pred & true)
    precision = tp / max(len(pred), 1)
    recall = tp / max(len(true), 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    return {
        "pair_precision": round(precision, 4),
        "pair_recall": round(recall, 4),
        "pair_f1": round(f1, 4),
        "predicted_pairs": len(pred),
        "true_pairs": len(true),
    }


def evaluate_forecast(bundle: dict) -> dict:
    raw = pd.read_csv(RAW_DIR / "telemetry.csv", parse_dates=["ts"])
    clean, report = refine_telemetry(raw)
    graph = default_graph()
    base = engineer_telemetry(clean, graph)
    base["lag96"] = base.groupby("node_id")["occ_ratio"].shift(96)
    supervised = make_supervised(base)
    columns = bundle["forecast_features"]
    train, _, test = temporal_split(supervised, "ts")
    X_train, y_train = train[columns], train["y_occ"]
    X_test, y_test = test[columns], test["y_occ"]

    models = bundle["forecast_models"]
    p50 = 0.7 * models["q50"].predict(X_test) + 0.3 * models["xgb"].predict(X_test)
    p50 = np.clip(p50, 0, 1.1)
    p10 = np.clip(models["q10"].predict(X_test), 0, 1.1)
    p90 = np.clip(models["q90"].predict(X_test), 0, 1.1)
    coverage = float(np.mean((y_test >= p10) & (y_test <= p90)))

    ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    ridge.fit(X_train, y_train)
    ridge_pred = np.clip(ridge.predict(X_test), 0, 1.1)
    persistence = np.clip(test["occ_ratio"], 0, 1.1)
    seasonal = np.clip(test["lag96"].fillna(test["occ_ratio"]), 0, 1.1)

    per_horizon = []
    for horizon, group in test.groupby("horizon_min"):
        index = group.index
        y = group["y_occ"]
        model_pred = pd.Series(p50, index=test.index).loc[index]
        persistence_pred = pd.Series(persistence.values, index=test.index).loc[index]
        per_horizon.append(
            {
                "horizon_min": int(horizon),
                "rows": int(len(group)),
                "model_mae": round(float(mean_absolute_error(y, model_pred)), 4),
                "persistence_mae": round(float(mean_absolute_error(y, persistence_pred)), 4),
                "model_r2": round(float(r2_score(y, model_pred)), 4),
            }
        )

    wait_pred = models["wait"].predict(X_test)
    return {
        "split": "chronological 70/15/15",
        "rows": int(len(supervised)),
        "refined_rows": int(len(clean)),
        "dropped_faulty_rows": int(len(raw) - len(clean)),
        "model": {
            "mae_occupancy_ratio": round(float(mean_absolute_error(y_test, p50)), 4),
            "rmse_occupancy_ratio": round(float(np.sqrt(np.mean((y_test - p50) ** 2))), 4),
            "r2_occupancy_ratio": round(float(r2_score(y_test, p50)), 4),
            "mae_wait_min": round(float(mean_absolute_error(test["y_wait"], wait_pred)), 3),
            "quantile_coverage_p10_p90": round(coverage, 4),
        },
        "baselines": {
            "persistence": {
                "mae": round(float(mean_absolute_error(y_test, persistence)), 4),
                "r2": round(float(r2_score(y_test, persistence)), 4),
            },
            "seasonal_naive_24h": {
                "mae": round(float(mean_absolute_error(y_test, seasonal)), 4),
                "r2": round(float(r2_score(y_test, seasonal)), 4),
            },
            "ridge": {
                "mae": round(float(mean_absolute_error(y_test, ridge_pred)), 4),
                "r2": round(float(r2_score(y_test, ridge_pred)), 4),
            },
        },
        "improvement_vs_seasonal_pct": round(
            (1 - mean_absolute_error(y_test, p50) / max(mean_absolute_error(y_test, seasonal), 1e-9)) * 100,
            2,
        ),
        "per_horizon": per_horizon,
        "refine_quality": report.quality_score,
    }


def evaluate_ablations(bundle: dict) -> dict:
    raw = pd.read_csv(RAW_DIR / "telemetry.csv", parse_dates=["ts"])
    clean, _ = refine_telemetry(raw)
    graph = default_graph()
    base = engineer_telemetry(clean, graph)
    supervised = make_supervised(base)
    columns = bundle["forecast_features"]
    train, _, test = temporal_split(supervised, "ts")
    y_test = test["y_occ"]
    full_mae = float(
        mean_absolute_error(
            y_test,
            np.clip(bundle["forecast_models"]["q50"].predict(test[columns]), 0, 1.1),
        )
    )

    def quick_mae(feature_list: list[str], frame_train, frame_test) -> float:
        model = lgb.LGBMRegressor(
            n_estimators=200, learning_rate=0.06, num_leaves=48,
            random_state=SEED, n_jobs=4, verbosity=-1,
        )
        model.fit(frame_train[feature_list], frame_train["y_occ"])
        pred = np.clip(model.predict(frame_test[feature_list]), 0, 1.1)
        return round(float(mean_absolute_error(frame_test["y_occ"], pred)), 4)

    spatial = {"neighbor_mean_occ", "edge_lit_ratio"}
    temporal = {"lag1", "lag2", "lag4", "roll3_mean", "roll3_std", "roll6_mean", "momentum"}
    no_spatial = quick_mae([c for c in columns if c not in spatial], train, test)
    no_temporal = quick_mae([c for c in columns if c not in temporal], train, test)

    raw_base = engineer_telemetry(raw, graph)
    raw_supervised = make_supervised(raw_base)
    raw_train, _, _ = temporal_split(raw_supervised, "ts")
    refiner_model = lgb.LGBMRegressor(
        n_estimators=200, learning_rate=0.06, num_leaves=48,
        random_state=SEED, n_jobs=4, verbosity=-1,
    )
    refiner_model.fit(raw_train[columns], raw_train["y_occ"])
    no_refiner = round(float(mean_absolute_error(y_test, np.clip(refiner_model.predict(test[columns]), 0, 1.1))), 4)

    return {
        "full_model_mae": round(full_mae, 4),
        "no_spatial_features_mae": no_spatial,
        "no_temporal_features_mae": no_temporal,
        "no_refiner_mae": no_refiner,
        "delta_pct": {
            "spatial": round((no_spatial / full_mae - 1) * 100, 2),
            "temporal": round((no_temporal / full_mae - 1) * 100, 2),
            "refiner": round((no_refiner / full_mae - 1) * 100, 2),
        },
    }


def evaluate_triage(bundle: dict) -> dict:
    raw = pd.read_csv(RAW_DIR / "incidents.csv", parse_dates=["reported_at"])
    graph = default_graph()
    engine_embedder = CampusPulseEngine.load().embedder
    assignments, clusters, report = refine_incidents(raw, graph, engine_embedder)
    features, columns = build_incident_features(
        assignments, graph, engine_embedder, include_embeddings=False
    )
    frame = features.copy()
    frame["target"] = assignments["severity"].astype(int).values
    frame["resolve_minutes"] = assignments["resolve_minutes"].values
    frame["cluster_id"] = assignments["cluster_id"].values
    frame["reported_at"] = assignments["reported_at"].values
    train, test = triage_split(frame)
    X_test = test[columns]
    classifier = bundle["triage_classifier"]
    predictions = classifier.predict(X_test)
    probabilities = classifier.predict_proba(X_test)
    sla_pred = bundle["triage_sla"].predict(X_test)

    baseline = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    baseline.fit(train[columns], train["target"])
    baseline_pred = baseline.predict(test[columns])

    per_class_f1 = f1_score(test["target"], predictions, average=None, labels=[0, 1, 2, 3], zero_division=0)
    matrix = confusion_matrix(test["target"], predictions, labels=[0, 1, 2, 3]).tolist()
    majority = int(test["target"].mode().iloc[0])
    majority_pred = np.full(len(test), majority)

    # Same classifier family, same split; only the 384-d embedding block changes.
    features_emb, columns_emb = build_incident_features(
        assignments, graph, engine_embedder, include_embeddings=True
    )
    frame_emb = features_emb.copy()
    frame_emb["target"] = assignments["severity"].astype(int).values
    frame_emb["cluster_id"] = assignments["cluster_id"].values
    train_emb, test_emb = triage_split(frame_emb)
    embedding_model = xgb.XGBClassifier(
        n_estimators=180, max_depth=3, learning_rate=0.06, subsample=0.85,
        colsample_bytree=0.5, min_child_weight=4, reg_lambda=2.0,
        objective="multi:softprob", num_class=4, tree_method="hist",
        random_state=SEED, n_jobs=4, verbosity=0,
    )
    embedding_model.fit(train_emb[columns_emb], train_emb["target"])
    embedding_pred = embedding_model.predict(test_emb[columns_emb])

    return {
        "split": "group-aware by incident cluster (80/20), no paraphrase leakage",
        "feature_contract": "structured context + text cues; embeddings owned by dedupe/retrieval",
        "reports": int(len(assignments)),
        "clusters": int(len(clusters)),
        "merged_reports": int(report.incident_reports_merged),
        "model": {
            "accuracy": round(float(accuracy_score(test["target"], predictions)), 4),
            "macro_f1": round(float(f1_score(test["target"], predictions, average="macro", zero_division=0)), 4),
            "weighted_f1": round(float(f1_score(test["target"], predictions, average="weighted", zero_division=0)), 4),
            "per_class_f1": {SEVERITY_TO_PRIORITY[i]: round(float(score), 4) for i, score in enumerate(per_class_f1)},
            "mean_confidence": round(float(probabilities.max(axis=1).mean()), 4),
            "confusion_matrix": matrix,
            "sla_mae_min": round(float(mean_absolute_error(test["resolve_minutes"], sla_pred)), 2),
        },
        "baselines": {
            "majority_class": {
                "accuracy": round(float(accuracy_score(test["target"], majority_pred)), 4),
                "macro_f1": round(float(f1_score(test["target"], majority_pred, average="macro", zero_division=0)), 4),
            },
            "logreg_structured": {
                "accuracy": round(float(accuracy_score(test["target"], baseline_pred)), 4),
                "macro_f1": round(float(f1_score(test["target"], baseline_pred, average="macro", zero_division=0)), 4),
            },
        },
        "embedding_features_ablation": {
            "accuracy": round(float(accuracy_score(test_emb["target"], embedding_pred)), 4),
            "macro_f1": round(float(f1_score(test_emb["target"], embedding_pred, average="macro", zero_division=0)), 4),
        },
    }


def evaluate_dedupe() -> dict:
    raw = pd.read_csv(RAW_DIR / "incidents.csv", parse_dates=["reported_at"])
    graph = default_graph()
    engine = CampusPulseEngine.load()
    assignments, clusters, report = refine_incidents(raw, graph, engine.embedder)
    full = _pair_prf(assignments)
    exact = assignments.copy()
    normalised = (
        exact["description"].str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True)
        .str.split().str.join(" ")
    )
    exact["pred_cluster_id"] = exact["node_id"].astype(str) + "|" + normalised
    exact_metrics = _pair_prf(exact)
    return {
        "threshold": engine.embedder.dedupe_threshold,
        "backend": engine.embedder.backend,
        "reports": int(len(assignments)),
        "clusters": int(len(clusters)),
        "merged_reports": int(report.incident_reports_merged),
        "semantic_gate": full,
        "exact_text_match_ablation": exact_metrics,
    }


def evaluate_mess(bundle: dict) -> dict:
    raw = pd.read_csv(RAW_DIR / "mess.csv", parse_dates=["date"])
    features, _ = build_mess_features(raw)
    frame = features.copy()
    frame["date"] = raw["date"].values
    frame["y_head"] = raw["headcount"].values
    frame["y_waste"] = raw["waste_kg"].values
    frame["seasonal"] = raw["lag7_headcount"].values
    train, _, test = temporal_split(frame, "date")
    columns = bundle["mess_features"]
    head_pred = bundle["mess_head"].predict(test[columns])
    waste_pred = bundle["mess_waste"].predict(test[columns])
    seasonal_pred = test["seasonal"].values
    return {
        "split": "chronological by date (70/15/15)",
        "rows": int(len(raw)),
        "model": {
            "headcount_mae": round(float(mean_absolute_error(test["y_head"], head_pred)), 2),
            "headcount_mape_pct": round(_mape(test["y_head"], head_pred), 2),
            "waste_mae_kg": round(float(mean_absolute_error(test["y_waste"], waste_pred)), 2),
            "r2_headcount": round(float(r2_score(test["y_head"], head_pred)), 4),
        },
        "baseline_seasonal": {
            "headcount_mae": round(float(mean_absolute_error(test["y_head"], seasonal_pred)), 2),
            "headcount_mape_pct": round(_mape(test["y_head"], seasonal_pred), 2),
        },
    }


def evaluate_routing(engine: CampusPulseEngine) -> dict:
    graph = engine.graph
    rng = random.Random(SEED)
    nodes = list(graph.nodes.keys())
    crowd = engine.crowd_at(SNAPSHOT_TS)
    incidents = engine.incident_counts(SNAPSHOT_TS)
    risk_reductions, extra_distance, latencies = [], [], []
    for _ in range(80):
        origin, destination = rng.sample(nodes, 2)
        start = time.perf_counter()
        fastest = graph.shortest_path(origin, destination, "fastest", True, crowd, incidents)
        safest = graph.shortest_path(origin, destination, "safest", True, crowd, incidents)
        latencies.append((time.perf_counter() - start) * 1000)
        if fastest["risk_index"] > 0:
            risk_reductions.append(
                (fastest["risk_index"] - safest["risk_index"]) / fastest["risk_index"] * 100
            )
        extra_distance.append(safest["distance_m"] / max(fastest["distance_m"], 1) - 1)
    latencies = np.array(latencies)

    carts = simulate_carts(SNAPSHOT_TS, graph)
    greedy_wait, random_wait = [], []
    for _ in range(120):
        pickup = rng.choice(nodes)
        dispatch = engine.dispatch(pickup, as_of=SNAPSHOT_TS)
        greedy_wait.append(dispatch.eta_min)
        cart = rng.choice(carts)
        distance = graph.distance_m(cart["node_id"], pickup)
        random_wait.append(distance / 280.0 + 1.2 + (0 if cart["status"] == "available" else 4.0))
    return {
        "pairs_evaluated": len(risk_reductions),
        "mean_risk_reduction_pct": round(float(np.mean(risk_reductions)), 2),
        "median_risk_reduction_pct": round(float(np.median(risk_reductions)), 2),
        "mean_extra_distance_pct": round(float(np.mean(extra_distance) * 100), 2),
        "route_latency_ms_p50": round(float(np.percentile(latencies, 50)), 3),
        "route_latency_ms_p95": round(float(np.percentile(latencies, 95)), 3),
        "dispatch": {
            "requests": len(greedy_wait),
            "greedy_mean_eta_min": round(float(np.mean(greedy_wait)), 2),
            "random_mean_eta_min": round(float(np.mean(random_wait)), 2),
            "eta_reduction_pct": round(
                (1 - np.mean(greedy_wait) / max(np.mean(random_wait), 1e-9)) * 100, 2
            ),
        },
    }


def evaluate_latency(engine: CampusPulseEngine) -> dict:
    samples = {"forecast": [], "search": [], "triage": [], "route": []}
    for _ in range(12):
        start = time.perf_counter()
        engine.forecast("library")
        samples["forecast"].append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        engine.search_places("cold coffee")
        samples["search"].append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        engine.triage_report(
            {
                "node_id": "hostel_b1",
                "category": "wifi",
                "description": "Wi-Fi is down in the hostel wing, eduroam will not connect",
            }
        )
        samples["triage"].append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        engine.route({"origin": "gate_main", "destination": "library", "night_mode": True})
        samples["route"].append((time.perf_counter() - start) * 1000)
    return {
        key: {
            "p50_ms": round(float(np.percentile(values, 50)), 2),
            "p95_ms": round(float(np.percentile(values, 95)), 2),
        }
        for key, values in samples.items()
    }


def main() -> dict:
    start = time.perf_counter()
    bundle = joblib.load(MODELS_DIR / "campus_pulse.joblib")
    engine = CampusPulseEngine.load()
    forecast = evaluate_forecast(bundle)
    ablations = evaluate_ablations(bundle)
    triage = evaluate_triage(bundle)
    dedupe = evaluate_dedupe()
    mess = evaluate_mess(bundle)
    routing = evaluate_routing(engine)
    latency = evaluate_latency(engine)

    payload = {
        "benchmark_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "dataset_sha256_16": _sha256(
            [RAW_DIR / "telemetry.csv", RAW_DIR / "incidents.csv", RAW_DIR / "mess.csv"]
        ),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "sklearn": sklearn.__version__,
            "lightgbm": lgb.__version__,
            "xgboost": __import__("xgboost").__version__,
            "embedder_backend": engine.embedder.backend,
        },
        "data_contract": {
            "telemetry_days": 35,
            "incident_days": 60,
            "mess_days": 60,
            "source": "calibrated synthetic digital twin (documented generator)",
        },
        "forecast": forecast,
        "ablations": ablations,
        "triage": triage,
        "dedupe": dedupe,
        "mess": mess,
        "routing": routing,
        "latency": latency,
        "train_metrics": bundle.get("metrics", {}),
        "wall_clock_s": round(time.perf_counter() - start, 2),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "benchmark_metrics.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    table = [
        "# CampusPulse benchmark snapshot",
        "",
        f"Generated: {payload['generated_at']} | seed {SEED} | embeddings: {engine.embedder.backend}",
        "",
        "| Pillar | Metric | Model | Best baseline |",
        "|---|---|---|---|",
        f"| Crowd forecast | MAE (occupancy ratio) | {forecast['model']['mae_occupancy_ratio']:.4f} | "
        f"{min(v['mae'] for v in forecast['baselines'].values()):.4f} |",
        f"| Crowd forecast | R2 | {forecast['model']['r2_occupancy_ratio']:.4f} | "
        f"{max(v['r2'] for v in forecast['baselines'].values()):.4f} |",
        f"| Triage | Macro F1 | {triage['model']['macro_f1']:.4f} | "
        f"{max(v['macro_f1'] for v in triage['baselines'].values()):.4f} |",
        f"| Dedupe | Pair F1 | {dedupe['semantic_gate']['pair_f1']:.4f} | "
        f"{dedupe['exact_text_match_ablation']['pair_f1']:.4f} (exact text only) |",
        f"| Mess | Headcount MAE | {mess['model']['headcount_mae']:.2f} | "
        f"{mess['baseline_seasonal']['headcount_mae']:.2f} |",
        f"| Routing | Night risk reduction | {routing['mean_risk_reduction_pct']:.1f}% | 0% (shortest path) |",
        f"| Cart dispatch | ETA reduction | {routing['dispatch']['eta_reduction_pct']:.1f}% | random assignment |",
        "",
    ]
    (RESULTS_DIR / "benchmark_table.md").write_text("\n".join(table), encoding="utf-8")
    print("\n".join(table))
    print(f"[evaluate] wrote results/benchmark_metrics.json in {payload['wall_clock_s']}s")
    return payload


if __name__ == "__main__":
    main()
