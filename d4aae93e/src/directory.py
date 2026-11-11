"""Honest capability registry for the campus assistant.

Two rules drive this module:

1. A capability is only `connected` when this repository actually has the
   data. Simulated data is `demo`. Nothing is presented as live availability
   when it is not.
2. Departments are published by TIET; individual faculty offices and room
   allocations are not. We therefore list departments and explicitly refuse to
   invent a professor-to-cabin mapping.
"""
from __future__ import annotations

from .places import DEPARTMENT_SOURCE, HOSTEL_SOURCE, MAP_SOURCE

DEPARTMENTS: list[dict] = [
    {"name": "Computer Science & Engineering", "school": "Engineering", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "Electronics & Communication Engineering", "school": "Engineering", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "Electrical & Instrumentation Engineering", "school": "Engineering", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "Mechanical Engineering", "school": "Engineering", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "Civil Engineering", "school": "Engineering", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "Chemical Engineering", "school": "Engineering", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "Biotechnology", "school": "Engineering", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "Basic & Engineering Sciences", "school": "Sciences", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "Chemistry & Biochemistry", "school": "Sciences", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "Physics & Materials Science", "school": "Sciences", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "Mathematics", "school": "Sciences", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "Humanities & Social Sciences", "school": "Sciences", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "Energy & Environment", "school": "Sciences", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "L. M. Thapar School of Management", "school": "Management", "source": DEPARTMENT_SOURCE, "verification": "official"},
    {"name": "Thapar School of Liberal Arts & Sciences", "school": "Liberal arts", "source": DEPARTMENT_SOURCE, "verification": "official"},
]

SERVICES: list[dict] = [
    {
        "id": "place-search",
        "name": "Place & alias search",
        "status": "connected",
        "capability": "Find",
        "detail": "26 labels from the shared TIET campus map, with student aliases. Every hit names its source.",
        "source": MAP_SOURCE,
    },
    {
        "id": "wayfinding",
        "name": "Campus wayfinding",
        "status": "connected",
        "capability": "Navigate",
        "detail": "20-node / 35-edge walking graph with verified map anchors. Distances are modelled, not surveyed.",
        "source": "src/graph.py",
    },
    {
        "id": "faculty-directory",
        "name": "Faculty directory",
        "status": "partial",
        "capability": "Find",
        "detail": "TIET publishes departments, not individual cabins. We list departments and do not invent professor offices.",
        "source": DEPARTMENT_SOURCE,
    },
    {
        "id": "hostel-directory",
        "name": "Hostel directory",
        "status": "partial",
        "capability": "Explore",
        "detail": "Hall names come from the campus map; room allocation and occupancy are held by the hostel office.",
        "source": HOSTEL_SOURCE,
    },
    {
        "id": "crowd-forecast",
        "name": "Crowd forecasting",
        "status": "demo",
        "capability": "Explore",
        "detail": "Trained on a synthetic replay stream. Metrics are real, the underlying telemetry is not live campus data.",
        "source": "src/simulator.py",
    },
    {
        "id": "incident-triage",
        "name": "Incident triage",
        "status": "demo",
        "capability": "Ops",
        "detail": "Cluster summaries and evidence snippets are produced from synthetic reports.",
        "source": "data/incidents.csv",
    },
    {
        "id": "mess-planning",
        "name": "Mess demand planning",
        "status": "demo",
        "capability": "Ops",
        "detail": "Headcount and waste figures are forecasts over synthetic history, shown only in Ops.",
        "source": "data/mess_history.csv",
    },
    {
        "id": "cart-dispatch",
        "name": "Golf cart dispatch",
        "status": "demo",
        "capability": "Navigate",
        "detail": "Cart positions and ETAs come from a deterministic simulator. No live GPS feed is connected.",
        "source": "src/simulator.py",
    },
    {
        "id": "library-seats",
        "name": "Library seat availability",
        "status": "not_connected",
        "capability": "Explore",
        "detail": "TIET does not publish live seat counts, so this app shows none instead of a made-up number.",
        "source": "",
    },
    {
        "id": "classroom-timetable",
        "name": "Course to room lookup",
        "status": "not_connected",
        "capability": "Find",
        "detail": "Room allocations live in the department timetable, which is not exposed as open data.",
        "source": "",
    },
    {
        "id": "shuttle-gps",
        "name": "Live shuttle tracking",
        "status": "not_connected",
        "capability": "Navigate",
        "detail": "No vehicle GPS feed is available. Only the simulated dispatch demo is offered.",
        "source": "",
    },
]


def department_dicts() -> list[dict]:
    return [dict(item) for item in DEPARTMENTS]


def service_dicts() -> list[dict]:
    return [dict(item) for item in SERVICES]
