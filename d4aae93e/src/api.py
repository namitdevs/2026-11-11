"""FastAPI surface for CampusPulse. Run: uvicorn src.api:app --reload"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import SNAPSHOT_TS
from .engine import CampusPulseEngine
from .schemas import (
    Cart,
    Department,
    DispatchRequest,
    DispatchResponse,
    FindResponse,
    ForecastResponse,
    Hotspot,
    IncidentCluster,
    IncidentReport,
    MessForecast,
    PlaceHit,
    RouteRequest,
    RouteResponse,
    ServiceStatus,
    Snapshot,
    StressIndex,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = CampusPulseEngine.load_or_bootstrap()
    yield


app = FastAPI(
    title="CampusPulse API",
    version="1.0.0",
    description=(
        "Campus wayfinding and operations: verified TIET place search with aliases, "
        "map-projected walking routes, golf-cart demo, plus crowd forecasting, incident "
        "triage and mess planning on the same campus graph."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_engine() -> CampusPulseEngine:
    engine = getattr(app.state, "engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="engine not ready")
    return engine


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "name": "CampusPulse",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": [
            "/api/v1/snapshot",
            "/api/v1/forecast/{node_id}",
            "/api/v1/hotspots",
            "/api/v1/places",
            "/api/v1/find",
            "/api/v1/departments",
            "/api/v1/services",
            "/api/v1/route",
            "/api/v1/incidents",
            "/api/v1/mess/plan",
            "/api/v1/carts",
            "/api/v1/benchmarks",
        ],
    }


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    engine = get_engine()
    return {
        "status": "ok",
        "embedder": engine.embedder.backend,
        "nodes": len(engine.graph.nodes),
        "edges": len(engine.graph.edges),
        "places": len(engine.places),
        "models": sorted(engine.bundle.get("forecast_models", {}).keys()),
        "trained_at": engine.bundle.get("trained_at"),
    }


@app.get("/api/v1/graph")
def graph() -> dict[str, Any]:
    return get_engine().graph.to_dict()


@app.get("/api/v1/snapshot", response_model=Snapshot)
def snapshot(as_of: str | None = None) -> Snapshot:
    try:
        return get_engine().snapshot(as_of=as_of)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/forecast/{node_id}", response_model=ForecastResponse)
def forecast(node_id: str, horizons: str = Query("15,30,60"), as_of: str | None = None):
    try:
        parsed = tuple(int(value) for value in horizons.split(",") if value.strip())
        return get_engine().forecast(node_id, parsed, as_of=as_of)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown campus node") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/hotspots", response_model=list[Hotspot])
def hotspots(as_of: str | None = None):
    return get_engine().hotspots(as_of=as_of)


@app.get("/api/v1/places", response_model=list[PlaceHit])
def places(q: str = "", limit: int = Query(8, ge=1, le=30)):
    return get_engine().search_places(q, limit=limit)


@app.get("/api/v1/find", response_model=FindResponse)
def find(q: str = "", limit: int = Query(8, ge=1, le=20)):
    """Universal search: verified places, aliases, departments and honest service state."""
    return get_engine().find(q, limit=limit)


@app.get("/api/v1/departments", response_model=list[Department])
def departments():
    return get_engine().departments()


@app.get("/api/v1/services", response_model=list[ServiceStatus])
def services():
    return get_engine().service_status()


@app.post("/api/v1/route", response_model=RouteResponse)
def route(request: RouteRequest, as_of: str | None = None):
    try:
        return get_engine().route(request, as_of=as_of)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown campus node") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/incidents", response_model=IncidentCluster)
def report_incident(report: IncidentReport):
    try:
        return get_engine().triage_report(report)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown campus node") from exc


@app.get("/api/v1/incidents/queue", response_model=list[IncidentCluster])
def incident_queue(as_of: str | None = None, limit: int = Query(10, ge=1, le=30)):
    return get_engine().incident_queue(as_of=as_of, limit=limit)


@app.get("/api/v1/mess/plan", response_model=list[MessForecast])
def mess_plan(as_of: str | None = None):
    return get_engine().mess_plan(as_of=as_of)


@app.get("/api/v1/carts", response_model=list[Cart])
def carts(as_of: str | None = None):
    return get_engine().carts(as_of=as_of)


@app.post("/api/v1/carts/dispatch", response_model=DispatchResponse)
def dispatch(request: DispatchRequest, as_of: str | None = None):
    try:
        return get_engine().dispatch(
            request.pickup_node, request.destination_node, request.passengers, as_of=as_of
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown campus node") from exc


@app.get("/api/v1/stress", response_model=StressIndex)
def stress(as_of: str | None = None):
    return get_engine().stress_index(as_of=as_of)


@app.get("/api/v1/insights")
def insights(as_of: str | None = None):
    return {"insights": get_engine().insights(as_of=as_of)}


@app.get("/api/v1/benchmarks")
def benchmarks():
    import json

    from .config import RESULTS_DIR

    path = RESULTS_DIR / "benchmark_metrics.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="run python -m src.evaluate first")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/v1/demo-scenario")
def demo_scenario() -> dict[str, Any]:
    """The cascade story: one Wi-Fi flood touches triage, routing, mess and CSI."""
    engine = get_engine()
    triage = engine.triage_report(
        {
            "node_id": "hostel_b1",
            "category": "wifi",
            "description": "No internet in the Prithvi Hall wing, eduroam drops every minute",
            "reported_at": "2026-02-06T19:57:00",
        }
    )
    route = engine.route(
        RouteRequest(origin="gate_main", destination="library", night_mode=True)
    )
    plans = engine.mess_plan()
    return {
        "trigger": "23 paraphrased Wi-Fi reports in 18 minutes at Prithvi Hall",
        "refine": {
            "merged_reports": 23,
            "canonical_incidents": 1,
            "quality_score": engine.incident_report.quality_score,
        },
        "triage": triage.model_dump(mode="json"),
        "routing": {
            "origin": route.origin,
            "destination": route.destination,
            "destination_label": route.destination_label,
            "risk_reduction_pct": route.safest.risk_reduction_pct,
            "recommended": route.recommended,
            "cart_eta_min": route.cart_eta_min,
        },
        "mess": [plan.model_dump(mode="json") for plan in plans[:2]],
        "stress": engine.stress_index().model_dump(mode="json"),
        "replay_at": SNAPSHOT_TS,
    }
