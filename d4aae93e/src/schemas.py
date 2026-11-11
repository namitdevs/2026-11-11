"""Pydantic v2 contracts shared by the API, engine and tests."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

IncidentCategory = Literal[
    "wifi", "electrical", "plumbing", "food", "safety", "cleanliness", "infrastructure"
]
Priority = Literal["P0", "P1", "P2", "P3"]
RouteMode = Literal["fastest", "safest"]
Verification = Literal["map", "official", "third-party", "unverified", "demo"]
ServiceState = Literal["connected", "partial", "demo", "not_connected"]


class Node(BaseModel):
    id: str
    label: str
    kind: str
    x: float
    y: float
    capacity: int = 0
    footfall: float = 0.5


class Edge(BaseModel):
    id: str
    u: str
    v: str
    distance_m: float = Field(gt=0)
    lit: bool = True
    cctv: bool = True
    stairs: bool = False
    footfall: float = 0.5
    risk: float = 0.0


class GraphPayload(BaseModel):
    nodes: list[Node]
    edges: list[Edge]


class TelemetryPoint(BaseModel):
    node_id: str
    ts: datetime
    occupancy: int = Field(ge=0)
    capacity: int = Field(gt=0)
    queue_len: int = Field(ge=0)
    wait_min: float = Field(ge=0)
    temp_c: float = 24.0
    rain: bool = False


class ForecastPoint(BaseModel):
    horizon_min: int
    p10: float
    p50: float
    p90: float


class ForecastResponse(BaseModel):
    node_id: str
    node_label: str
    generated_at: datetime
    model: str
    points: list[ForecastPoint]
    current_occupancy_ratio: float
    capacity: int


class Place(BaseModel):
    id: str
    name: str
    node_id: str
    category: str
    aliases: list[str] = Field(default_factory=list)
    floor: str = "Ground"
    landmark: str = ""
    tone: int = 160
    open_hours: str = "Not connected"
    verification: Verification = "unverified"
    source: str = ""
    description: str = ""
    popular: bool = False


class PlaceHit(Place):
    score: float = 0.0
    match_reason: str = ""


class Department(BaseModel):
    name: str
    school: str = ""
    source: str = ""
    verification: Verification = "official"


class ServiceStatus(BaseModel):
    id: str
    name: str
    status: ServiceState
    capability: str
    detail: str
    source: str = ""


class FindResponse(BaseModel):
    query: str
    intent: Literal["place", "faculty", "service", "unknown"] = "place"
    hits: list[PlaceHit] = Field(default_factory=list)
    departments: list["Department"] = Field(default_factory=list)
    services: list[ServiceStatus] = Field(default_factory=list)
    note: str = ""


class IncidentReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    node_id: str
    category: IncidentCategory
    description: str = Field(min_length=8, max_length=600)
    reported_at: datetime | None = None
    reporter_hash: str | None = Field(default=None, max_length=64)

    @field_validator("description")
    @classmethod
    def _clean(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 8:
            raise ValueError("description too short after normalisation")
        return value


class IncidentCluster(BaseModel):
    cluster_id: str
    node_id: str
    node_label: str
    category: IncidentCategory
    merged_reports: int
    reported_at: datetime
    priority: Priority
    priority_confidence: float = Field(ge=0, le=1)
    sla_minutes: int = Field(ge=0)
    summary: str
    playbook: str
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_snippets: list[str] = Field(default_factory=list)
    mean_similarity: float = Field(default=0.0, ge=0, le=1)
    embedding_backend: str = "hashing"


class RefineReport(BaseModel):
    raw_rows: int = 0
    accepted_rows: int = 0
    dropped_rows: int = 0
    duplicate_rows_removed: int = 0
    incident_reports_merged: int = 0
    clusters_formed: int = 0
    staleness_gaps: int = 0
    quality_score: float = Field(default=1.0, ge=0, le=1)
    issues: list[str] = Field(default_factory=list)


class RouteStep(BaseModel):
    from_node: str
    to_node: str
    instruction: str
    distance_m: float


class RouteResult(BaseModel):
    mode: RouteMode
    path: list[str]
    labels: list[str]
    steps: list[RouteStep]
    distance_m: float
    eta_min: float
    risk_index: float = Field(ge=0, le=100)
    risk_reduction_pct: float = 0.0
    accessible: bool = False
    night_mode: bool = False


class RouteRequest(BaseModel):
    origin: str
    destination: str
    night_mode: bool = False
    accessible: bool = False


class RouteResponse(BaseModel):
    origin: str
    destination: str
    destination_label: str
    landmark: str = ""
    fastest: RouteResult
    safest: RouteResult
    recommended: RouteMode
    cart_eta_min: float | None = None


class Cart(BaseModel):
    id: str
    label: str
    node_id: str
    status: Literal["available", "on_trip", "charging"]
    capacity: int = 4
    progress: float = 0.0
    next_node: str | None = None


class DispatchRequest(BaseModel):
    pickup_node: str
    destination_node: str | None = None
    passengers: int = Field(default=1, ge=1, le=4)


class DispatchResponse(BaseModel):
    cart_id: str
    cart_label: str
    pickup_node: str
    eta_min: float
    walk_min: float
    reason: str
    alternatives: list[str] = Field(default_factory=list)


class MessForecast(BaseModel):
    date: str
    meal: str
    mess_id: str
    mess_label: str
    predicted_headcount: int
    p90_headcount: int
    prep_kg: float
    expected_waste_kg: float
    baseline_waste_kg: float
    waste_saved_kg: float
    confidence: float = Field(ge=0, le=1)


class StressComponent(BaseModel):
    key: str
    label: str
    value: float = Field(ge=0, le=100)
    weight: float


class StressIndex(BaseModel):
    score: float = Field(ge=0, le=100)
    label: str
    components: list[StressComponent]


class Hotspot(BaseModel):
    node_id: str
    label: str
    occupancy_ratio: float
    predicted_ratio: float
    pressure: float
    queue_len: int
    wait_min: float


class Snapshot(BaseModel):
    generated_at: datetime
    mode: str
    csi: StressIndex
    kpis: dict[str, float | int | str]
    graph: GraphPayload
    places: list[Place]
    departments: list[Department] = Field(default_factory=list)
    services: list[ServiceStatus] = Field(default_factory=list)
    routes: dict[str, dict[str, dict[str, RouteResult]]]
    carts: list[Cart]
    dispatches: dict[str, DispatchResponse]
    forecasts: dict[str, dict]
    hotspots: list[Hotspot]
    triage: dict
    mess: list[MessForecast]
    benchmark: dict
    insights: list[str]
    refine: RefineReport
