"""CampusPulse unified inference engine.

One graph, one refined event stream, one calibrated model bundle. Public
capabilities (forecast, triage, mess planning, safe routing, search, cart
dispatch, stress index) are thin views over the same state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .config import (
    BASELINE_OVER_PREP,
    CART_SPEED_M_PER_MIN,
    FRONTEND_DATA_DIR,
    MEAL_PORTION_KG,
    MODELS_DIR,
    NIGHT_END_HOUR,
    NIGHT_START_HOUR,
    PLAYBOOKS,
    RESULTS_DIR,
    SEED,
    SNAPSHOT_TS,
    WALK_SPEED_M_PER_MIN,
)
from .embeddings import get_embedder
from .directory import department_dicts, service_dicts
from .features import (
    build_incident_features,
    build_mess_features,
    engineer_telemetry,
    inference_frame,
    place_search_frame,
    telemetry_feature_columns,
)
from .graph import CampusGraph, default_graph
from .llm import synthesize_incident
from .places import place_dicts, search_document
from .refiner import refine_incidents, refine_telemetry
from .schemas import (
    Cart,
    Department,
    DispatchResponse,
    FindResponse,
    ForecastPoint,
    ForecastResponse,
    Hotspot,
    IncidentCluster,
    IncidentReport,
    MessForecast,
    Place,
    PlaceHit,
    RefineReport,
    RouteRequest,
    RouteResponse,
    RouteResult,
    RouteStep,
    ServiceStatus,
    Snapshot,
    StressComponent,
    StressIndex,
)
from .simulator import simulate_carts

PRIORITY_BY_SEVERITY = {0: "P3", 1: "P2", 2: "P1", 3: "P0"}
SEVERITY_BY_PRIORITY = {v: k for k, v in PRIORITY_BY_SEVERITY.items()}
MEAL_HOURS = {"breakfast": 8.0, "lunch": 13.0, "snack": 17.5, "dinner": 20.0}
MEAL_ORDER = ("breakfast", "lunch", "snack", "dinner")
SNAPSHOT_ORIGINS = ("gate_main", "gate_north", "hostel_g1")


def _naive(ts) -> pd.Timestamp:
    stamp = pd.Timestamp(ts)
    return stamp.tz_localize(None) if stamp.tzinfo is not None else stamp


class CampusPulseEngine:
    def __init__(self, graph: CampusGraph | None = None, embedder=None) -> None:
        self.graph = graph or default_graph()
        self.embedder = embedder or get_embedder()
        self.places = place_dicts()
        self.place_embeddings = place_search_frame(self.places, self.embedder)
        self.bundle: dict = {}
        self.engineered: pd.DataFrame = pd.DataFrame()
        self.incidents: pd.DataFrame = pd.DataFrame()
        self.clusters: pd.DataFrame = pd.DataFrame()
        self.mess: pd.DataFrame = pd.DataFrame()
        self.triage_table: pd.DataFrame = pd.DataFrame()
        self.incident_embeddings = np.zeros((0, self.embedder.dim), dtype=np.float32)
        self.telemetry_report = RefineReport()
        self.incident_report = RefineReport()
        self._snapshot_cache: Snapshot | None = None

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls, path: Path | None = None) -> "CampusPulseEngine":
        bundle_path = path or MODELS_DIR / "campus_pulse.joblib"
        if not bundle_path.exists():
            raise FileNotFoundError(
                f"{bundle_path} missing. Run `python -m src.train` or use load_or_bootstrap()."
            )
        engine = cls()
        engine.bundle = joblib.load(bundle_path)
        backend = engine.bundle.get("embedder_backend", "hashing")
        engine.embedder = get_embedder(backend)
        engine.place_embeddings = place_search_frame(engine.places, engine.embedder)
        engine._load_data()
        return engine

    @classmethod
    def load_or_bootstrap(cls) -> "CampusPulseEngine":
        try:
            return cls.load()
        except FileNotFoundError:
            from .train import main as train_main

            train_main()
            return cls.load()

    def _load_data(self) -> None:
        from .config import RAW_DIR

        raw_telemetry = pd.read_csv(RAW_DIR / "telemetry.csv", parse_dates=["ts"])
        self.engineered, self.telemetry_report = refine_telemetry(raw_telemetry)
        raw_incidents = pd.read_csv(RAW_DIR / "incidents.csv", parse_dates=["reported_at"])
        self.incidents, self.clusters, self.incident_report = refine_incidents(
            raw_incidents, self.graph, self.embedder
        )
        self.mess = pd.read_csv(RAW_DIR / "mess.csv", parse_dates=["date"])
        self.incident_embeddings = self.embedder.encode(self.incidents["description"].tolist())
        # Telemetry is refined, then re-engineered; the raw-derived engineered frame
        # is required for one-hot inference parity.
        self.engineered = engineer_telemetry(self.engineered, self.graph)
        self._prepare_triage()

    def _prepare_triage(self) -> None:
        if self.clusters.empty:
            return
        frame = self.clusters.copy()
        frame["description"] = frame["canonical_description"]
        frame["cluster_size"] = frame["merged_reports"]
        frame["report_id"] = frame["cluster_id"]
        features, _ = build_incident_features(frame, self.graph, self.embedder)
        columns = self.bundle.get("triage_features")
        X = features.reindex(columns=columns, fill_value=0) if columns else features
        classifier = self.bundle["triage_classifier"]
        probabilities = classifier.predict_proba(X)
        severity = probabilities.argmax(axis=1)
        confidence = probabilities.max(axis=1)
        sla = np.maximum(10, self.bundle["triage_sla"].predict(X).round().astype(int))
        summaries, evidence = [], []
        for row, sev in zip(frame.itertuples(), severity):
            priority = PRIORITY_BY_SEVERITY[int(sev)]
            retrieved = self._retrieve_similar(row.canonical_description, row.category)
            window = max(1, int(row.merged_reports))
            summary, ids = synthesize_incident(
                self.graph.label(row.node_id),
                row.category,
                int(row.merged_reports),
                window,
                row.canonical_description,
                priority,
                int(sla[len(summaries)]),
                retrieved,
            )
            summaries.append(summary)
            evidence.append(ids)
        self.triage_table = frame.copy()
        self.triage_table["priority"] = [PRIORITY_BY_SEVERITY[int(s)] for s in severity]
        self.triage_table["severity_pred"] = severity
        self.triage_table["confidence"] = confidence
        self.triage_table["sla_minutes"] = sla
        self.triage_table["summary"] = summaries
        self.triage_table["evidence_ids"] = evidence
        self.triage_table["playbook"] = self.triage_table["category"].map(PLAYBOOKS)

    def _evidence_snippets(self, canonical: str, report_ids, limit: int = 3) -> list[str]:
        snippets: list[str] = []

        def add(text) -> None:
            cleaned = " ".join(str(text).split())
            if not cleaned or cleaned in snippets or len(snippets) >= limit:
                return
            snippets.append(cleaned if len(cleaned) <= 140 else cleaned[:137].rstrip() + "...")

        add(canonical)
        if self.incidents.empty or len(snippets) >= limit:
            return snippets
        lookup = self.incidents.drop_duplicates("report_id")
        descriptions = dict(zip(lookup["report_id"], lookup["description"]))
        for report_id in report_ids:
            add(descriptions.get(report_id, ""))
            if len(snippets) >= limit:
                break
        return snippets

    def _retrieve_similar(self, description: str, category: str, k: int = 3) -> list[dict]:
        if self.incidents.empty:
            return []
        mask = (self.incidents["category"] == category).to_numpy()
        if not mask.any():
            mask = np.ones(len(self.incidents), dtype=bool)
        vector = self.embedder.encode([description])[0]
        similarities = self.incident_embeddings[mask] @ vector
        subset = self.incidents[mask]
        order = np.argsort(similarities)[-k:][::-1]
        retrieved = []
        for idx in order:
            row = subset.iloc[int(idx)]
            retrieved.append(
                {
                    "report_id": row.get("report_id", ""),
                    "description": row["description"],
                    "category": row["category"],
                    "severity": int(row["severity"]),
                    "resolve_minutes": float(row["resolve_minutes"]),
                    "similarity": float(similarities[int(idx)]),
                }
            )
        return retrieved

    # --------------------------------------------------------------- helpers
    def _as_of(self, as_of=None) -> pd.Timestamp:
        return _naive(as_of) if as_of is not None else _naive(SNAPSHOT_TS)

    def _latest(self, as_of=None) -> pd.DataFrame:
        ts = self._as_of(as_of)
        window = self.engineered[self.engineered["ts"] <= ts]
        if window.empty:
            window = self.engineered
        return window.sort_values("ts").groupby("node_id", as_index=False).tail(1)

    def crowd_at(self, as_of=None) -> dict[str, float]:
        latest = self._latest(as_of)
        return {row.node_id: float(row.occ_ratio) for row in latest.itertuples()}

    def active_clusters(self, as_of=None, hours: int = 24) -> pd.DataFrame:
        ts = self._as_of(as_of)
        window = self.triage_table
        if window.empty:
            return window
        cutoff = ts - pd.Timedelta(hours=hours)
        return window[(window["reported_at"] <= ts) & (window["reported_at"] >= cutoff)]

    def incident_counts(self, as_of=None) -> dict[str, int]:
        active = self.active_clusters(as_of)
        if active.empty:
            return {}
        return active.groupby("node_id").size().to_dict()

    # ------------------------------------------------------------- forecasts
    def forecast(self, node_id: str, horizons=(15, 30, 60), as_of=None) -> ForecastResponse:
        if node_id not in self.graph.nodes:
            raise KeyError("unknown campus node")
        if self.engineered.empty:
            raise RuntimeError("engine has no telemetry")
        models = self.bundle["forecast_models"]
        columns = self.bundle["forecast_features"]
        ts = self._as_of(as_of)
        window = self.engineered[self.engineered["ts"] <= ts]
        if window.empty:
            window = self.engineered
        current = window[window["node_id"] == node_id].sort_values("ts").tail(1)
        if current.empty:
            raise ValueError(f"no telemetry for {node_id}")
        points = []
        for horizon in horizons:
            X = inference_frame(window, columns, node_id, int(horizon))
            low = float(models["q10"].predict(X)[0])
            mid_lgb = float(models["q50"].predict(X)[0])
            mid_xgb = float(models["xgb"].predict(X)[0])
            high = float(models["q90"].predict(X)[0])
            mid = 0.7 * mid_lgb + 0.3 * mid_xgb
            low, mid, high = sorted([low, mid, high])
            points.append(
                ForecastPoint(
                    horizon_min=int(horizon),
                    p10=round(float(np.clip(low, 0, 1.1)), 4),
                    p50=round(float(np.clip(mid, 0, 1.1)), 4),
                    p90=round(float(np.clip(high, 0, 1.1)), 4),
                )
            )
        node = self.graph.nodes[node_id]
        return ForecastResponse(
            node_id=node_id,
            node_label=node["label"],
            generated_at=datetime.now(timezone.utc),
            model="LightGBM quantile + XGBoost blend (70/30)",
            points=points,
            current_occupancy_ratio=round(float(current["occ_ratio"].iloc[0]), 4),
            capacity=int(node["capacity"]),
        )

    def hotspots(self, as_of=None) -> list[Hotspot]:
        latest = self._latest(as_of)
        results = []
        for row in latest.itertuples():
            try:
                forecast = self.forecast(row.node_id, (30,), as_of=as_of)
                predicted = forecast.points[0].p50
            except Exception:
                predicted = float(row.occ_ratio)
            pressure = 0.55 * predicted + 0.45 * float(row.occ_ratio)
            results.append(
                Hotspot(
                    node_id=row.node_id,
                    label=self.graph.label(row.node_id),
                    occupancy_ratio=round(float(row.occ_ratio), 4),
                    predicted_ratio=round(float(predicted), 4),
                    pressure=round(float(pressure), 4),
                    queue_len=int(row.queue_len),
                    wait_min=round(float(row.wait_min), 1),
                )
            )
        return sorted(results, key=lambda item: item.pressure, reverse=True)

    # ---------------------------------------------------------------- routing
    def route(self, request: RouteRequest | dict, as_of=None) -> RouteResponse:
        req = request if isinstance(request, RouteRequest) else RouteRequest.model_validate(request)
        crowd = self.crowd_at(as_of)
        incidents = self.incident_counts(as_of)
        if req.origin not in self.graph.nodes or req.destination not in self.graph.nodes:
            raise KeyError("unknown campus node")

        def build(mode: str) -> RouteResult:
            raw = self.graph.shortest_path(
                req.origin,
                req.destination,
                mode=mode,
                night=req.night_mode,
                crowd=crowd,
                incidents=incidents,
                accessible=req.accessible,
            )
            path = raw["path"]
            steps = []
            for u, v in zip(path, path[1:]):
                edge = self.graph.edge_between(u, v)
                steps.append(
                    RouteStep(
                        from_node=u,
                        to_node=v,
                        instruction=f"Head to {self.graph.label(v)} along the walkway",
                        distance_m=round(float(edge["distance_m"]) if edge else 0.0, 1),
                    )
                )
            speed = (
                62.0 if req.accessible else (72.0 if req.night_mode else 75.0)
            ) if req.accessible or req.night_mode else WALK_SPEED_M_PER_MIN
            mean_crowd = float(np.mean([crowd.get(node, 0.0) for node in path])) if path else 0.0
            eta = raw["distance_m"] / max(speed, 1.0) * (1 + 0.18 * mean_crowd)
            places_here = [p for p in self.places if p["node_id"] == req.destination]
            landmark = places_here[0]["landmark"] if places_here else ""
            return RouteResult(
                mode=mode,  # type: ignore[arg-type]
                path=path,
                labels=[self.graph.label(node) for node in path],
                steps=steps,
                distance_m=round(float(raw["distance_m"]), 1),
                eta_min=round(float(eta), 1),
                risk_index=round(float(raw["risk_index"]), 2),
                risk_reduction_pct=0.0,
                accessible=req.accessible,
                night_mode=req.night_mode,
            )

        fastest = build("fastest")
        safest = build("safest")
        if fastest.risk_index > 0:
            safest.risk_reduction_pct = round(
                max(0.0, (fastest.risk_index - safest.risk_index) / fastest.risk_index * 100), 1
            )
        recommended = "safest" if req.night_mode else "fastest"
        try:
            dispatch = self.dispatch(req.origin, req.destination, 1, as_of=as_of)
            cart_eta = dispatch.eta_min
        except Exception:
            cart_eta = None
        places_here = [p for p in self.places if p["node_id"] == req.destination]
        return RouteResponse(
            origin=req.origin,
            destination=req.destination,
            destination_label=self.graph.label(req.destination),
            landmark=places_here[0]["landmark"] if places_here else "",
            fastest=fastest,
            safest=safest,
            recommended=recommended,
            cart_eta_min=cart_eta,
        )

    def carts(self, as_of=None) -> list[Cart]:
        raw = simulate_carts(self._as_of(as_of), self.graph)
        return [Cart.model_validate(item) for item in raw]

    def dispatch(self, pickup_node: str, destination_node: str | None = None,
                 passengers: int = 1, as_of=None) -> DispatchResponse:
        if pickup_node not in self.graph.nodes:
            raise KeyError("unknown pickup node")
        carts = simulate_carts(self._as_of(as_of), self.graph)
        candidates = []
        for cart in carts:
            distance = self.graph.distance_m(cart["node_id"], pickup_node)
            penalty = 0.0 if cart["status"] == "available" else (4.0 if cart["status"] == "on_trip" else 9.0)
            eta = distance / CART_SPEED_M_PER_MIN + 1.2 + penalty
            candidates.append((eta, distance, cart))
        candidates.sort(key=lambda item: item[0])
        eta, distance, cart = candidates[0]
        walk_from = self.graph.distance_m(pickup_node, destination_node) if destination_node else 0.0
        walk_min = walk_from / WALK_SPEED_M_PER_MIN if walk_from else 0.0
        reason = (
            f"{cart['label']} is {distance:.0f} m away at {self.graph.label(cart['node_id'])} "
            f"with status '{cart['status']}'."
        )
        return DispatchResponse(
            cart_id=cart["id"],
            cart_label=cart["label"],
            pickup_node=pickup_node,
            eta_min=round(float(eta), 1),
            walk_min=round(float(walk_min), 1),
            reason=reason,
            alternatives=[item[2]["id"] for item in candidates[1:4]],
        )

    # ----------------------------------------------------------------- triage
    def triage_report(self, report: IncidentReport | dict, as_of=None) -> IncidentCluster:
        payload = report if isinstance(report, IncidentReport) else IncidentReport.model_validate(report)
        now = _naive(payload.reported_at) if payload.reported_at else self._as_of(as_of)
        row = pd.DataFrame(
            [
                {
                    "report_id": f"live-{abs(int(now.value)) % 100000}",
                    "node_id": payload.node_id,
                    "category": payload.category,
                    "description": payload.description,
                    "reported_at": now,
                    "cluster_size": 1,
                }
            ]
        )
        features, _ = build_incident_features(row, self.graph, self.embedder)
        columns = self.bundle["triage_features"]
        X = features.reindex(columns=columns, fill_value=0)
        probabilities = self.bundle["triage_classifier"].predict_proba(X)[0]
        severity = int(np.argmax(probabilities))
        priority = PRIORITY_BY_SEVERITY[severity]
        sla = max(10, int(round(float(self.bundle["triage_sla"].predict(X)[0]))))
        retrieved = self._retrieve_similar(payload.description, payload.category)
        summary, evidence = synthesize_incident(
            self.graph.label(payload.node_id),
            payload.category,
            1,
            1,
            payload.description,
            priority,
            sla,
            retrieved,
        )
        return IncidentCluster(
            cluster_id=f"live-{abs(int(now.value)) % 100000}",
            node_id=payload.node_id,
            node_label=self.graph.label(payload.node_id),
            category=payload.category,
            merged_reports=1,
            reported_at=now.to_pydatetime(),
            priority=priority,  # type: ignore[arg-type]
            priority_confidence=round(float(np.max(probabilities)), 4),
            sla_minutes=sla,
            summary=summary,
            playbook=PLAYBOOKS[payload.category],
            evidence_ids=evidence,
            evidence_snippets=self._evidence_snippets(payload.description, evidence),
            mean_similarity=0.0,
            embedding_backend=self.embedder.backend,
        )

    def incident_queue(self, as_of=None, limit: int = 10) -> list[IncidentCluster]:
        active = self.active_clusters(as_of)
        if active.empty:
            return []
        active = active.sort_values(["severity_pred", "reported_at"], ascending=[False, False]).head(limit)
        queue = []
        for row in active.itertuples():
            queue.append(
                IncidentCluster(
                    cluster_id=row.cluster_id,
                    node_id=row.node_id,
                    node_label=self.graph.label(row.node_id),
                    category=row.category,
                    merged_reports=int(row.merged_reports),
                    reported_at=row.reported_at.to_pydatetime(),
                    priority=row.priority,
                    priority_confidence=round(float(row.confidence), 4),
                    sla_minutes=int(row.sla_minutes),
                    summary=row.summary,
                    playbook=row.playbook,
                    evidence_ids=list(row.evidence_ids),
                    evidence_snippets=self._evidence_snippets(
                        getattr(row, "canonical_description", ""), list(row.evidence_ids)
                    ),
                    mean_similarity=round(float(row.mean_similarity), 3),
                    embedding_backend=self.embedder.backend,
                )
            )
        return queue

    # ------------------------------------------------------------------- mess
    def mess_plan(self, as_of=None) -> list[MessForecast]:
        now = self._as_of(as_of)
        slots = []
        for offset in range(0, 3):
            day = now.normalize() + pd.Timedelta(days=offset)
            for meal in MEAL_ORDER:
                slot = day + pd.Timedelta(hours=MEAL_HOURS[meal])
                if slot > now:
                    slots.append((day, meal))
        slots = slots[:4]
        results = []
        last_weather = self._latest(as_of).iloc[0]
        for day, meal in slots:
            for mess_id in ("mess_main", "mess_north"):
                history = self.mess[(self.mess["mess_id"] == mess_id) & (self.mess["meal"] == meal)
                                    & (self.mess["date"] < day)].sort_values("date")
                previous = history.tail(1)
                lag7_rows = history[history["date"] == day - pd.Timedelta(days=7)]
                lag7 = float(lag7_rows["headcount"].iloc[-1]) if not lag7_rows.empty else float(previous["headcount"].iloc[-1])
                lag1 = float(previous["headcount"].iloc[-1])
                row = pd.DataFrame(
                    [
                        {
                            "date": day,
                            "mess_id": mess_id,
                            "meal": meal,
                            "day_index": int((day - pd.Timestamp("2026-01-05")).days),
                            "is_weekend": int(day.day_of_week >= 5),
                            "is_exam": int(21 <= (day - pd.Timestamp("2026-01-05")).days <= 30),
                            "is_holiday": int(day.day_of_week == 6),
                            "rain": 0,
                            "temp_c": float(last_weather["temp_c"]),
                            "menu_score": 1.0,
                            "lag7_headcount": lag7,
                            "lag1_headcount": lag1,
                        }
                    ]
                )
                features, _ = build_mess_features(row)
                X = features.reindex(columns=self.bundle["mess_features"], fill_value=0)
                median = float(self.bundle["mess_head"].predict(X)[0])
                p90 = float(self.bundle["mess_head_p90"].predict(X)[0])
                median = max(20.0, median)
                p90 = max(median, p90)
                portion = MEAL_PORTION_KG[meal]
                # Current policy prepares 12% over last week's headcount. The
                # recommendation never exceeds that baseline, so the reported
                # saving is a real reduction rather than a larger buffer.
                baseline_prep = lag7 * portion * 1.12
                recommended_prep = min(p90 * portion, baseline_prep * 0.97)
                consumed = median * portion * 0.92
                expected_waste = max(0.0, recommended_prep - consumed)
                baseline_waste = max(expected_waste, baseline_prep - consumed)
                confidence = float(np.clip(1 - (p90 - median) / max(median, 1), 0.35, 0.95))
                results.append(
                    MessForecast(
                        date=day.date().isoformat(),
                        meal=meal,
                        mess_id=mess_id,
                        mess_label=self.graph.label(mess_id),
                        predicted_headcount=int(round(median)),
                        p90_headcount=int(round(p90)),
                        prep_kg=round(recommended_prep, 1),
                        expected_waste_kg=round(expected_waste, 1),
                        baseline_waste_kg=round(baseline_waste, 1),
                        waste_saved_kg=round(baseline_waste - expected_waste, 1),
                        confidence=round(confidence, 2),
                    )
                )
        return results

    # ----------------------------------------------------------------- search
    def search_places(self, query: str, limit: int = 8) -> list[PlaceHit]:
        query = (query or "").strip().lower()
        if not query:
            ranked = sorted(self.places, key=lambda p: p["name"])[:limit]
            return [PlaceHit(**place) for place in ranked]
        if query in {"hostel", "hostels", "residence", "residential"}:
            ranked = [place for place in self.places if place["category"] == "residential"]
            return [
                PlaceHit(**place, score=90.0, match_reason="residential category")
                for place in ranked
            ][:limit]
        vector = self.embedder.encode([query])[0]
        semantic = self.place_embeddings @ vector
        hits = []
        for idx, place in enumerate(self.places):
            document = search_document(place)
            name = place["name"].lower()
            aliases = [alias.lower() for alias in place["aliases"]]
            if query == name or query in aliases:
                lexical, reason = 100.0, "exact name or alias"
            elif any(candidate.startswith(query) for candidate in [name, *aliases]):
                lexical, reason = 85.0, "alias prefix"
            elif any(len(candidate) >= 5 and candidate in query for candidate in [name, *aliases]):
                lexical, reason = 75.0, "query contains alias"
            elif query in document:
                lexical, reason = 68.0, "keyword match"
            else:
                tokens = set(query.split())
                overlap = len(tokens & set(document.split())) / max(len(tokens), 1)
                lexical, reason = overlap * 55.0, "semantic neighbourhood"
            score = lexical + max(0.0, float(semantic[idx])) * 45.0
            semantic_floor = 0.30 if self.embedder.backend == "hashing" else 0.40
            if lexical <= 0 and float(semantic[idx]) < semantic_floor:
                continue
            if score <= 0:
                continue
            hits.append(PlaceHit(**place, score=round(score, 2), match_reason=reason))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:limit]

    # ------------------------------------------------------- directory/find
    def departments(self) -> list[Department]:
        return [Department(**item) for item in department_dicts()]

    def service_status(self) -> list[ServiceStatus]:
        return [ServiceStatus(**item) for item in service_dicts()]

    def find(self, query: str, limit: int = 8) -> FindResponse:
        query = " ".join((query or "").split())
        lowered = query.lower()
        if not lowered:
            popular = [place for place in self.places if place.get("popular")][:limit]
            return FindResponse(
                query=query,
                intent="place",
                hits=[
                    PlaceHit(**place, score=100.0, match_reason="popular destination")
                    for place in popular
                ],
                note="Popular destinations whose labels are printed on the shared TIET campus map.",
            )

        faculty_terms = ("professor", "prof ", "faculty", "teacher", "who teaches", "hod", "cabin")
        service_terms = (
            "seat", "timetable", "which room", "course", "live", "queue",
            "available", "availability", "gps", "shuttle", "near me",
        )
        intent = "place"
        if any(term in lowered for term in faculty_terms):
            intent = "faculty"
        elif any(term in lowered for term in service_terms):
            intent = "service"

        hits = self.search_places(query, limit)
        words = {word for word in lowered.split() if len(word) > 3}
        departments: list[Department] = []
        services: list[ServiceStatus] = []
        note = ""

        if intent == "faculty":
            hits = [hit for hit in hits if hit.score >= 60][:2]
            stop = {"professor", "faculty", "teacher", "department", "engineering", "science", "cabin"}
            focus = words - stop
            ranked = [
                item
                for item in self.departments()
                if focus & {token.lower() for token in [*item.name.split(), item.school]}
            ]
            departments = (ranked or self.departments())[:6]
            note = (
                "TIET publishes departments, not individual faculty cabins. "
                "No professor-to-office mapping is invented here."
            )
        elif intent == "service":
            services = [
                item
                for item in self.service_status()
                if words & set((item.name + " " + item.capability + " " + item.detail).lower().split())
            ][:6] or [item for item in self.service_status() if item.status != "connected"][:6]
            note = (
                "Live availability is not connected for this capability. "
                "The status card says so instead of showing a fabricated number."
            )
        elif not hits:
            note = (
                "No verified campus label matched. Try a name printed on the campus map "
                "or a common alias such as canteen, OAT or Vahni."
            )

        return FindResponse(
            query=query,
            intent=intent,
            hits=hits,
            departments=departments,
            services=services,
            note=note,
        )

    # ------------------------------------------------------------ stress/kpis
    def stress_index(self, as_of=None) -> StressIndex:
        hotspots = self.hotspots(as_of)
        crowd = np.mean([h.pressure for h in hotspots[:3]]) * 100 if hotspots else 0.0
        active = self.active_clusters(as_of)
        incident_value = 0.0
        if not active.empty:
            counts = active["priority"].value_counts()
            incident_value = min(
                100.0,
                counts.get("P0", 0) * 50 + counts.get("P1", 0) * 22 + counts.get("P2", 0) * 6,
            )
        plans = self.mess_plan(as_of)
        mess_value = 0.0
        if plans:
            deviations = []
            for plan in plans[:4]:
                history = self.mess[(self.mess["mess_id"] == plan.mess_id) & (self.mess["meal"] == plan.meal)]
                if not history.empty:
                    baseline = float(history["headcount"].tail(7).mean())
                    deviations.append(abs(plan.predicted_headcount - baseline) / max(baseline, 1))
            mess_value = min(100.0, float(np.mean(deviations)) * 300) if deviations else 0.0
        night_penalties = [
            self.graph.edge_risk(edge, True, 0.55, 1) - 1.0 for edge in self.graph.edges
        ]
        mobility_value = min(100.0, float(np.mean(night_penalties)) / 1.6 * 100)
        cart_etas = [self.dispatch(origin, as_of=as_of).eta_min for origin in SNAPSHOT_ORIGINS]
        cart_value = min(100.0, float(np.mean(cart_etas)) * 14)
        components = [
            StressComponent(key="crowd", label="Crowd pressure", value=round(crowd, 1), weight=0.30),
            StressComponent(key="incidents", label="Incident load", value=round(incident_value, 1), weight=0.25),
            StressComponent(key="mess", label="Mess variance", value=round(mess_value, 1), weight=0.15),
            StressComponent(key="mobility", label="Night mobility risk", value=round(mobility_value, 1), weight=0.20),
            StressComponent(key="carts", label="Cart response", value=round(cart_value, 1), weight=0.10),
        ]
        score = round(sum(component.value * component.weight for component in components), 1)
        if score < 25:
            label = "Calm"
        elif score < 45:
            label = "Steady"
        elif score < 65:
            label = "Elevated"
        elif score < 82:
            label = "Strained"
        else:
            label = "Critical"
        return StressIndex(score=score, label=label, components=components)

    def insights(self, as_of=None) -> list[str]:
        hotspots = self.hotspots(as_of)
        queue = self.incident_queue(as_of, 40)
        plans = self.mess_plan(as_of)
        lines = []
        if hotspots:
            top = hotspots[0]
            lines.append(
                f"{top.label} is the current pressure point at {top.occupancy_ratio * 100:.0f}% occupancy "
                f"(queue ~{top.queue_len}, {top.wait_min:.0f} min wait); 30-min forecast {top.predicted_ratio * 100:.0f}%."
            )
        if queue:
            merged = sum(cluster.merged_reports for cluster in queue)
            top = queue[0]
            lines.append(
                f"{merged} reports collapsed into {len(queue)} canonical incidents in the last 24h. "
                f"Top priority: {top.priority} {top.category} at {top.node_label} ({top.merged_reports} reports)."
            )
        if plans:
            saved = sum(plan.waste_saved_kg for plan in plans)
            lines.append(
                f"Next {len(plans)} meal services: recommended prep avoids ~{max(saved, 0):.0f} kg of waste "
                f"versus the current 12% over-prep policy."
            )
        routes = self.route(
            RouteRequest(origin="gate_main", destination="library", night_mode=True), as_of=as_of
        )
        if routes.safest.risk_reduction_pct > 0:
            line = (
                f"Night route to the Central Library: the safest path cuts modelled risk by "
                f"{routes.safest.risk_reduction_pct:.0f}% for "
                f"{routes.safest.distance_m - routes.fastest.distance_m:+.0f} m."
            )
        else:
            line = "Night route to the Central Library: the fastest path is already the lowest-risk path."
        if routes.cart_eta_min is not None:
            line += f" Cart ETA {routes.cart_eta_min:.0f} min."
        lines.append(line)
        return lines

    # ---------------------------------------------------------------- snapshot
    def snapshot(self, as_of=None, refresh: bool = False) -> Snapshot:
        if self._snapshot_cache is not None and not refresh:
            return self._snapshot_cache
        now = self._as_of(as_of)
        csi = self.stress_index(now)
        hotspots = self.hotspots(now)
        queue = self.incident_queue(now, 10)
        plans = self.mess_plan(now)
        carts = self.carts(now)
        active = self.active_clusters(now)

        forecast_nodes = [
            "library", "canteen_main", "foodcourt", "canteen_north", "laundry", "sports",
        ]
        forecasts = {}
        for node_id in forecast_nodes:
            response = self.forecast(node_id, (15, 30, 60), as_of=now)
            history = (
                self.engineered[
                    (self.engineered["node_id"] == node_id) & (self.engineered["ts"] <= now)
                ]
                .sort_values("ts")
                .tail(12)
            )
            forecasts[node_id] = {
                "label": response.node_label,
                "capacity": response.capacity,
                "history": [
                    {"ts": row.ts.isoformat(), "ratio": round(float(row.occ_ratio), 4)}
                    for row in history.itertuples()
                ],
                "points": [point.model_dump() for point in response.points],
                "model": response.model,
            }

        route_table: dict[str, dict[str, dict]] = {}
        dispatch_table: dict[str, DispatchResponse] = {}
        unique_nodes = sorted({place["node_id"] for place in self.places})
        for origin in SNAPSHOT_ORIGINS:
            route_table[origin] = {}
            for node_id in unique_nodes:
                response = self.route(
                    RouteRequest(origin=origin, destination=node_id, night_mode=True), as_of=now
                )
                payload = {
                    "fastest": response.fastest.model_dump(mode="json"),
                    "safest": response.safest.model_dump(mode="json"),
                }
                for place in self.places:
                    if place["node_id"] == node_id:
                        route_table[origin][place["id"]] = payload
            dispatch_table[origin] = self.dispatch(origin, as_of=now)

        benchmark = {}
        benchmark_path = RESULTS_DIR / "benchmark_metrics.json"
        if benchmark_path.exists():
            benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))

        refine = RefineReport(
            raw_rows=self.telemetry_report.raw_rows + self.incident_report.raw_rows,
            accepted_rows=self.telemetry_report.accepted_rows + self.incident_report.accepted_rows,
            dropped_rows=self.telemetry_report.dropped_rows + self.incident_report.dropped_rows,
            duplicate_rows_removed=self.telemetry_report.duplicate_rows_removed,
            incident_reports_merged=self.incident_report.incident_reports_merged,
            clusters_formed=self.incident_report.clusters_formed,
            staleness_gaps=self.telemetry_report.staleness_gaps,
            quality_score=round(
                (self.telemetry_report.quality_score + self.incident_report.quality_score) / 2, 4
            ),
            issues=[*self.telemetry_report.issues, *self.incident_report.issues][:8],
        )
        p0p1 = int(active["priority"].isin(["P0", "P1"]).sum()) if not active.empty else 0
        model_name = (
            f"LightGBM x{len([k for k in self.bundle['forecast_models'] if k.startswith('q')])} + XGBoost"
            f" | {self.embedder.backend} embeddings"
        )
        kpis = {
            "csi_score": csi.score,
            "csi_label": csi.label,
            "busiest_node": f"{hotspots[0].label} {hotspots[0].occupancy_ratio * 100:.0f}%" if hotspots else "-",
            "p0_p1": p0p1,
            "cart_wait_min": dispatch_table["gate_main"].eta_min,
            "waste_saved_kg": round(sum(max(plan.waste_saved_kg, 0) for plan in plans), 1),
            "reports_collapsed": refine.incident_reports_merged,
            "quality_score": refine.quality_score,
            "model": model_name,
            "carts_available": sum(1 for cart in carts if cart.status == "available"),
        }
        snapshot = Snapshot(
            generated_at=datetime.now(timezone.utc),
            mode="replay",
            csi=csi,
            kpis=kpis,
            graph=self.graph.to_dict(),
            places=[Place(**place) for place in self.places],
            departments=self.departments(),
            services=self.service_status(),
            routes=route_table,  # type: ignore[arg-type]
            carts=carts,
            dispatches=dispatch_table,
            forecasts=forecasts,
            hotspots=hotspots,
            triage={
                "queue": [cluster.model_dump(mode="json") for cluster in queue],
                "stats": {
                    "reports_last_24h": int(active["merged_reports"].sum()) if not active.empty else 0,
                    "clusters_last_24h": int(len(active)),
                    "p0_p1": p0p1,
                    "cluster_ratio": round(
                        float(len(active)) / max(int(active["merged_reports"].sum()), 1), 3
                    ) if not active.empty else 0.0,
                },
            },
            mess=plans,
            benchmark=benchmark,
            insights=self.insights(now),
            refine=refine,
        )
        self._snapshot_cache = snapshot
        return snapshot

    def export_snapshot(self, path: Path | None = None, as_of=None) -> Path:
        snapshot = self.snapshot(as_of=as_of)
        target = path or (FRONTEND_DATA_DIR / "snapshot.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(snapshot.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
        return target
