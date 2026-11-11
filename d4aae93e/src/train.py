"""Train every model in the unified pipeline and persist one bundle.

Run: python -m src.train
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error
from sklearn.model_selection import GroupShuffleSplit

from .config import MODELS_DIR, PROCESSED_DIR, RAW_DIR, SEED
from .embeddings import get_embedder
from .features import (
    build_incident_features,
    build_mess_features,
    engineer_telemetry,
    make_supervised,
    telemetry_feature_columns,
)
from .graph import default_graph
from .refiner import refine_incidents, refine_telemetry
from .simulator import simulate_all


def temporal_split(frame: pd.DataFrame, column: str, val_frac: float = 0.15,
                   test_frac: float = 0.15):
    unique = np.sort(frame[column].unique())
    val_start = unique[int(len(unique) * (1 - val_frac - test_frac))]
    test_start = unique[int(len(unique) * (1 - test_frac))]
    train = frame[frame[column] < val_start]
    val = frame[(frame[column] >= val_start) & (frame[column] < test_start)]
    test = frame[frame[column] >= test_start]
    return train, val, test


def _lgb(alpha: float | None = None, trees: int = 320) -> lgb.LGBMRegressor:
    kwargs = dict(
        n_estimators=trees,
        learning_rate=0.05,
        num_leaves=48,
        min_child_samples=30,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=SEED,
        n_jobs=4,
        verbosity=-1,
    )
    if alpha is not None:
        kwargs.update(objective="quantile", alpha=alpha)
    return lgb.LGBMRegressor(**kwargs)


def _xgb(trees: int = 300) -> xgb.XGBRegressor:
    return xgb.XGBRegressor(
        n_estimators=trees,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        tree_method="hist",
        random_state=SEED,
        n_jobs=4,
        verbosity=0,
    )


def train_forecaster(verbose: bool = True) -> dict:
    raw = pd.read_csv(RAW_DIR / "telemetry.csv", parse_dates=["ts"])
    clean, report = refine_telemetry(raw)
    graph = default_graph()
    engineered = engineer_telemetry(clean, graph)
    supervised = make_supervised(engineered)
    columns = telemetry_feature_columns(engineered, graph)
    train, val, test = temporal_split(supervised, "ts")
    x_train, y_train = train[columns], train["y_occ"]
    x_val, y_val = val[columns], val["y_occ"]
    x_test, y_test = test[columns], test["y_occ"]

    models: dict[str, object] = {}
    timings = {}
    for alpha in (0.1, 0.5, 0.9):
        start = time.perf_counter()
        model = _lgb(alpha)
        model.fit(x_train, y_train)
        models[f"q{int(alpha * 100)}"] = model
        timings[f"lgb_q{int(alpha * 100)}"] = round(time.perf_counter() - start, 2)
    xgb_model = _xgb()
    start = time.perf_counter()
    xgb_model.fit(x_train, y_train)
    timings["xgb"] = round(time.perf_counter() - start, 2)
    models["xgb"] = xgb_model
    wait_model = _lgb(None, 260)
    wait_model.fit(x_train, train["y_wait"])
    models["wait"] = wait_model

    blended = 0.7 * models["q50"].predict(x_test) + 0.3 * xgb_model.predict(x_test)
    blended = np.clip(blended, 0, 1.1)
    metrics = {
        "test_mae_occupancy_ratio": round(float(mean_absolute_error(y_test, blended)), 4),
        "test_rmse_occupancy_ratio": round(float(np.sqrt(np.mean((y_test - blended) ** 2))), 4),
        "test_mae_wait_min": round(float(mean_absolute_error(test["y_wait"], wait_model.predict(x_test))), 3),
        "rows": int(len(supervised)),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "refined_rows": int(len(clean)),
        "raw_rows": int(len(raw)),
        "quality_score": report.quality_score,
        "timings_s": timings,
    }
    if verbose:
        print(f"[forecast] rows={len(supervised):,} MAE={metrics['test_mae_occupancy_ratio']:.4f} "
              f"RMSE={metrics['test_rmse_occupancy_ratio']:.4f}")
    return {
        "models": models,
        "features": columns,
        "metrics": metrics,
        "refine_report": report.model_dump(),
    }


def triage_split(frame: pd.DataFrame, test_size: float = 0.2, seed: int = SEED):
    """Group-aware split by incident cluster.

    Paraphrased duplicates of the same outage must not straddle train/test,
    otherwise the dedupe/priority metrics are inflated by leakage.
    """
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, test_idx = next(splitter.split(frame, groups=frame["cluster_id"]))
    return frame.iloc[train_idx], frame.iloc[test_idx]


def train_triage(verbose: bool = True) -> dict:
    raw = pd.read_csv(RAW_DIR / "incidents.csv", parse_dates=["reported_at"])
    graph = default_graph()
    embedder = get_embedder()
    assignments, clusters, report = refine_incidents(raw, graph, embedder)
    features, columns = build_incident_features(
        assignments, graph, embedder, include_embeddings=False
    )
    target = assignments["severity"].astype(int).values
    frame = features.copy()
    frame["target"] = target
    frame["reported_at"] = assignments["reported_at"].values
    frame["resolve_minutes"] = assignments["resolve_minutes"].values
    frame["cluster_id"] = assignments["cluster_id"].values
    train, test = triage_split(frame)
    x_train, y_train = train[columns], train["target"]
    x_test, y_test = test[columns], test["target"]

    classifier = xgb.XGBClassifier(
        n_estimators=180,
        max_depth=3,
        learning_rate=0.06,
        subsample=0.85,
        colsample_bytree=0.5,
        min_child_weight=4,
        reg_lambda=2.0,
        objective="multi:softprob",
        num_class=4,
        tree_method="hist",
        random_state=SEED,
        n_jobs=4,
        verbosity=0,
    )
    classifier.fit(x_train, y_train)
    predictions = classifier.predict(x_test)
    accuracy = float(accuracy_score(y_test, predictions))
    macro_f1 = float(f1_score(y_test, predictions, average="macro", zero_division=0))
    sla_model = _lgb(None, 260)
    sla_model.fit(x_train, train["resolve_minutes"])
    sla_mae = float(mean_absolute_error(test["resolve_minutes"], sla_model.predict(x_test)))
    if verbose:
        print(f"[triage] rows={len(assignments):,} clusters={len(clusters):,} "
              f"acc={accuracy:.3f} macroF1={macro_f1:.3f} SLA_MAE={sla_mae:.1f} min")
    return {
        "classifier": classifier,
        "sla": sla_model,
        "features": columns,
        "metrics": {
            "test_accuracy": round(accuracy, 4),
            "test_macro_f1": round(macro_f1, 4),
            "test_sla_mae_min": round(sla_mae, 3),
            "reports": int(len(assignments)),
            "clusters": int(len(clusters)),
            "merged_reports": int(report.incident_reports_merged),
        },
        "refine_report": report.model_dump(),
    }


def train_mess(verbose: bool = True) -> dict:
    raw = pd.read_csv(RAW_DIR / "mess.csv", parse_dates=["date"])
    features, columns = build_mess_features(raw)
    frame = features.copy()
    frame["date"] = raw["date"].values
    frame["y_head"] = raw["headcount"].values
    frame["y_waste"] = raw["waste_kg"].values
    train, val, test = temporal_split(frame, "date", val_frac=0.15, test_frac=0.15)
    head = _lgb(None, 300)
    head.fit(train[columns], train["y_head"])
    head_p90 = _lgb(0.9, 260)
    head_p90.fit(train[columns], train["y_head"])
    waste = _lgb(None, 220)
    waste.fit(train[columns], train["y_waste"])
    head_mae = float(mean_absolute_error(test["y_head"], head.predict(test[columns])))
    waste_mae = float(mean_absolute_error(test["y_waste"], waste.predict(test[columns])))
    mean_head = float(test["y_head"].mean())
    if verbose:
        print(f"[mess] rows={len(raw):,} head_MAE={head_mae:.1f} waste_MAE={waste_mae:.2f} kg")
    return {
        "head": head,
        "head_p90": head_p90,
        "waste": waste,
        "features": columns,
        "metrics": {
            "test_headcount_mae": round(head_mae, 3),
            "test_waste_mae_kg": round(waste_mae, 3),
            "mean_test_headcount": round(mean_head, 1),
        },
    }


def main(force_data: bool = False, verbose: bool = True) -> dict:
    start = time.perf_counter()
    simulate_all(force=force_data)
    forecast = train_forecaster(verbose)
    triage = train_triage(verbose)
    mess = train_mess(verbose)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    bundle = {
        "forecast_models": forecast["models"],
        "forecast_features": forecast["features"],
        "triage_classifier": triage["classifier"],
        "triage_sla": triage["sla"],
        "triage_features": triage["features"],
        "mess_head": mess["head"],
        "mess_head_p90": mess["head_p90"],
        "mess_waste": mess["waste"],
        "mess_features": mess["features"],
        "metrics": {
            "forecast": forecast["metrics"],
            "triage": triage["metrics"],
            "mess": mess["metrics"],
        },
        "refine_reports": {
            "telemetry": forecast["refine_report"],
            "incidents": triage["refine_report"],
        },
        "embedder_backend": get_embedder().backend,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "version": "1.0.0",
    }
    path = MODELS_DIR / "campus_pulse.joblib"
    joblib.dump(bundle, path)
    if verbose:
        print(f"[train] saved {path} in {time.perf_counter() - start:.1f}s")
    return bundle


if __name__ == "__main__":
    main()
