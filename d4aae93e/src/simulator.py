"""Deterministic simulator for the campus digital twin.

The generator encodes a documented timetable/weather/calendar process, then
adds measurement noise and injected anomalies so the refiner and models have
real work to do. It is deliberately not a random toy: queue length, mess
headcount, incident floods and cart demand all share the same calendar and
weather signals. Real deployments swap this module for CSV/live adapters.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from .config import (
    ANCHOR,
    CATEGORIES,
    INCIDENT_DAYS,
    MEAL_PORTION_KG,
    MESS_DAYS,
    SEED,
    SIM_DAYS,
)
from .graph import CampusGraph, default_graph

SERVICE_MIN = {
    "library": 3.2,
    "canteen_main": 2.1,
    "canteen_north": 2.0,
    "foodcourt": 2.4,
    "laundry": 5.0,
    "sports": 2.0,
    "vending_hub": 1.4,
    "block_a": 1.2,
    "block_b": 1.2,
    "block_c": 1.2,
    "block_d": 1.2,
    "mess_main": 1.8,
    "mess_north": 1.8,
    "medical": 4.0,
}

BASE_HEADCOUNT = {
    ("mess_main", "breakfast"): 340,
    ("mess_main", "lunch"): 920,
    ("mess_main", "snack"): 230,
    ("mess_main", "dinner"): 640,
    ("mess_north", "breakfast"): 190,
    ("mess_north", "lunch"): 540,
    ("mess_north", "snack"): 120,
    ("mess_north", "dinner"): 380,
}

INCIDENT_TEMPLATES = {
    "wifi": [
        "Wi-Fi keeps dropping near {node} since the last ten minutes",
        "No internet in {node}, eduroam shows connected but nothing loads",
        "Wifi is dead in the {node} wing and nobody can submit assignments",
        "Frequent disconnections on the {node} access point tonight",
        "{node} has zero signal bars and the hotspot says no internet",
        "Internet down in {node}, the whole floor is affected",
        "Campus wifi not working in {node}, authentication keeps failing",
        "Cannot connect to eduroam in {node}, it times out every time",
    ],
    "electrical": [
        "Lights flickering and a burning smell in {node}",
        "Power socket sparked in {node}, please check immediately",
        "No electricity in the {node} corridor since twenty minutes",
        "Switchboard is buzzing loudly in {node}",
        "The {node} breaker keeps tripping every few minutes",
        "Fan and lights dead in {node}, main switch looks tripped",
    ],
    "plumbing": [
        "Water leaking from the ceiling in {node}",
        "Tap is overflowing in {node} and water is spreading",
        "Washroom drain blocked in {node}, water is standing",
        "Pipe burst near {node}, please send someone fast",
        "No water supply in the {node} washroom since morning",
        "Leaking joint under the sink in {node}, floor is slippery",
    ],
    "food": [
        "Food smells stale at {node}, please check the batch",
        "Undercooked rice served at {node} during lunch",
        "Insect found near the serving counter at {node}",
        "The milk at {node} tastes sour today",
        "Hygiene issue at the {node} counter, plates look unwashed",
        "Curry at {node} has a strange smell, please inspect",
    ],
    "safety": [
        "Streetlight is off on the path near {node}, it is very dark",
        "Group loitering and passing comments near {node}",
        "Stray dog pack near {node}, students are scared to walk",
        "Slippery floor near {node}, someone almost fell",
        "Emergency exit near {node} is blocked by parked carts",
        "Suspicious person following students near {node} after dark",
    ],
    "cleanliness": [
        "Garbage bins overflowing at {node}",
        "Spilled food on the floor at {node}, nobody is cleaning it",
        "Washroom at {node} is dirty and out of soap",
        "Litter all around the {node} seating area",
        "Dustbins not cleared outside {node} for two days",
        "Tables at {node} are sticky and uncleaned",
    ],
    "infrastructure": [
        "Broken chair and exposed nail in the {node} seating area",
        "Ceiling tile fell down in {node}, area is unsafe",
        "Door latch broken at {node}, it will not close",
        "Lift stuck between floors at {node}, please check",
        "Cracked pavement outside {node}, trip hazard",
        "Window glass cracked in {node} after the storm",
    ],
}

CATEGORY_BASE_SEVERITY = {
    "wifi": 1,
    "electrical": 2,
    "plumbing": 1,
    "food": 2,
    "safety": 3,
    "cleanliness": 0,
    "infrastructure": 1,
}

CATEGORY_NODES = {
    "wifi": ["hostel_b1", "hostel_b2", "hostel_g1", "block_a", "block_b", "library", "block_c"],
    "electrical": ["hostel_b1", "hostel_b2", "hostel_g1", "block_a", "block_d"],
    "plumbing": ["hostel_b1", "hostel_b2", "hostel_g1", "laundry", "block_b"],
    "food": ["canteen_main", "canteen_north", "foodcourt", "mess_main", "mess_north"],
    "safety": ["amphitheatre", "hostel_g1", "library", "sports", "gate_north", "laundry"],
    "cleanliness": ["canteen_main", "foodcourt", "mess_main", "vending_hub"],
    "infrastructure": ["block_c", "block_d", "amphitheatre", "sports", "library"],
}


def _gauss(minutes: np.ndarray, center: float, width: float) -> np.ndarray:
    return np.exp(-0.5 * ((minutes - center) / width) ** 2)


def _calendar(ts: pd.Series) -> pd.DataFrame:
    day_index = (ts - pd.Timestamp(ANCHOR)).dt.days
    return pd.DataFrame(
        {
            "is_weekend": ts.dt.day_of_week.isin([5, 6]).astype(int),
            "is_exam": day_index.between(21, 30).astype(int),
            "is_holiday": (day_index.isin([9, 41]) | ts.dt.day_of_week.eq(6)).astype(int),
            "day_index": day_index,
        },
        index=ts.index,
    )


def _weather(ts: pd.Series, rng: np.random.Generator) -> pd.DataFrame:
    day = (ts - pd.Timestamp(ANCHOR)).dt.total_seconds() / 86400.0
    hour = ts.dt.hour + ts.dt.minute / 60.0
    temp = 22.5 + 6.5 * np.sin(2 * np.pi * (day - 18) / 70) + 4.5 * np.sin(
        2 * np.pi * (hour - 8) / 24
    )
    temp = temp + rng.normal(0, 0.8, len(ts))
    rain = (rng.random(len(ts)) < 0.055).astype(int)
    return pd.DataFrame({"temp_c": np.round(temp, 1), "rain": rain}, index=ts.index)


def _occupancy_ratio(node_id: str, minutes: np.ndarray, weekend: np.ndarray,
                     exam: np.ndarray, rain: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    if node_id == "library":
        ratio = 0.18 + 0.52 * _gauss(minutes, 12 * 60, 150) + 0.72 * _gauss(minutes, 19 * 60, 170)
        ratio -= 0.08 * weekend
        ratio += 0.10 * exam + 0.05 * rain
    elif node_id == "canteen_main":
        ratio = 0.08 + 0.86 * _gauss(minutes, 13 * 60, 62) + 0.78 * _gauss(minutes, 19 * 60 + 20, 78)
        ratio += 0.18 * _gauss(minutes, 9 * 60, 55)
        ratio *= 1 - 0.22 * weekend
        ratio += 0.06 * rain
    elif node_id == "foodcourt":
        ratio = 0.10 + 0.70 * _gauss(minutes, 13 * 60 + 30, 90) + 0.84 * _gauss(minutes, 20 * 60, 105)
        ratio *= 1 + 0.12 * weekend
        ratio += 0.05 * rain
    elif node_id == "canteen_north":
        ratio = 0.09 + 0.70 * _gauss(minutes, 12 * 60 + 45, 75) + 0.62 * _gauss(minutes, 19 * 60 + 15, 70)
        ratio *= 1 - 0.25 * weekend
    elif node_id == "laundry":
        ratio = 0.06 + 0.78 * _gauss(minutes, 18 * 60, 115) + 0.22 * _gauss(minutes, 10 * 60, 100)
        ratio *= 1 - 0.08 * weekend
        ratio += 0.20 * rain
    elif node_id == "sports":
        ratio = 0.05 + 0.52 * _gauss(minutes, 7 * 60, 55) + 0.72 * _gauss(minutes, 18 * 60, 95)
        ratio *= 1 + 0.25 * weekend
        ratio -= 0.20 * rain
    elif node_id == "vending_hub":
        ratio = 0.16 + 0.38 * _gauss(minutes, 13 * 60, 120) + 0.44 * _gauss(minutes, 20 * 60, 145)
        ratio *= 1 - 0.15 * weekend
        ratio += 0.05 * rain
    elif node_id in ("mess_main", "mess_north"):
        scale = 1.0 if node_id == "mess_main" else 0.62
        ratio = 0.05 + scale * (
            0.45 * _gauss(minutes, 8 * 60, 45)
            + 0.62 * _gauss(minutes, 13 * 60, 55)
            + 0.30 * _gauss(minutes, 17 * 60 + 30, 35)
            + 0.58 * _gauss(minutes, 20 * 60, 65)
        )
        ratio *= 1 - 0.18 * weekend
        ratio += 0.04 * exam
    elif node_id == "medical":
        ratio = 0.08 + 0.30 * _gauss(minutes, 11 * 60, 150) + 0.12 * _gauss(minutes, 17 * 60, 120)
        ratio -= 0.05 * weekend
    else:  # academic blocks
        ratio = 0.05 + 0.74 * _gauss(minutes, 11 * 60, 120) + 0.66 * _gauss(minutes, 15 * 60, 125)
        ratio += 0.08 * _gauss(minutes, 17 * 60, 70)
        ratio *= 1 - 0.82 * weekend
        ratio += 0.55 * exam * weekend + 0.05 * exam

    ratio = ratio + rng.normal(0, 0.035, len(ratio))
    # small autocorrelated jitter so lags carry genuine signal
    for i in range(1, len(ratio)):
        ratio[i] = 0.72 * ratio[i] + 0.28 * ratio[i - 1]
    return np.clip(ratio, 0.01, 1.06)


def simulate_telemetry(days: int = SIM_DAYS, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp(ANCHOR)
    index = pd.date_range(start, periods=days * 96, freq="15min")
    ts = pd.Series(index, index=index)
    cal = _calendar(ts)
    weather = _weather(ts, rng)
    minutes = (index.hour * 60 + index.minute).to_numpy()
    graph = default_graph()
    frames = []
    for node_id in graph.sensor_nodes():
        capacity = graph.nodes[node_id]["capacity"]
        ratio = _occupancy_ratio(
            node_id,
            minutes,
            cal["is_weekend"].to_numpy(),
            cal["is_exam"].to_numpy(),
            weather["rain"].to_numpy(),
            rng,
        )
        occupancy = np.round(ratio * capacity).astype(int)
        queue = np.maximum(0, (ratio - 0.55) * capacity * 0.18 + rng.normal(0, 2.0, len(ratio)))
        queue = np.round(queue).astype(int)
        wait = np.maximum(0.2, queue * SERVICE_MIN.get(node_id, 2.0) + rng.normal(0, 1.2, len(ratio)))
        frame = pd.DataFrame(
            {
                "ts": index,
                "node_id": node_id,
                "occupancy": occupancy,
                "capacity": capacity,
                "queue_len": queue,
                "wait_min": np.round(wait, 2),
                "temp_c": weather["temp_c"].to_numpy(),
                "rain": weather["rain"].to_numpy(),
                **{k: cal[k].to_numpy() for k in ("is_weekend", "is_exam", "is_holiday", "day_index")},
                "source": "sensor",
            }
        )
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True)

    # injected measurement faults for the refiner to catch
    outlier_idx = rng.choice(df.index, size=max(8, int(0.004 * len(df))), replace=False)
    df.loc[outlier_idx, "occupancy"] = (df.loc[outlier_idx, "capacity"] * 1.35).astype(int)
    negative_idx = rng.choice(df.index, size=max(5, int(0.002 * len(df))), replace=False)
    df.loc[negative_idx, "occupancy"] = -4
    df["ts"] = pd.to_datetime(df["ts"])
    return df.sort_values(["ts", "node_id"]).reset_index(drop=True)


def _make_incident_row(rng, ts, node_id, category, template, cluster_id, severity, resolve):
    graph = default_graph()
    description = template.format(node=graph.label(node_id))
    return {
        "report_id": "r-" + hashlib.sha256(f"{cluster_id}|{ts.isoformat()}|{node_id}|{rng.integers(0, 10**9)}".encode()).hexdigest()[:10],
        "node_id": node_id,
        "category": category,
        "description": description,
        "reported_at": ts,
        "reporter_hash": hashlib.sha256(f"student-{rng.integers(0, 99999)}".encode()).hexdigest()[:16],
        "severity": severity,
        "resolve_minutes": resolve,
        "cluster_id": cluster_id,
    }


def _severity(rng, category: str, cluster_size: int, hour: int) -> int:
    base = CATEGORY_BASE_SEVERITY[category]
    bump = 1 if cluster_size >= 8 else 0
    night = 1 if (hour >= 21 or hour <= 5) and category in ("safety", "electrical") else 0
    noise = int(rng.choice([-1, 1])) if rng.random() < 0.15 else 0
    return int(np.clip(base + bump + night + noise, 0, 3))


def simulate_incidents(days: int = INCIDENT_DAYS, seed: int = SEED + 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp(ANCHOR)
    rows: list[dict] = []
    graph = default_graph()
    templates_by_cat = INCIDENT_TEMPLATES

    # Forced demo incidents near the dashboard snapshot time (day 32 evening)
    demo_specs = [
        ("hostel_b1", "wifi", 19 * 60 + 40, 16, 18),
        ("foodcourt", "food", 18 * 60 + 5, 7, 11),
        ("amphitheatre", "safety", 20 * 60 + 10, 5, 14),
        ("block_c", "electrical", 17 * 60 + 20, 6, 9),
    ]
    cluster_no = 0
    for node_id, category, minute, n_reports, span in demo_specs:
        day = 32
        base_ts = start + pd.Timedelta(days=day, minutes=minute)
        offsets = sorted(rng.integers(0, span, size=n_reports))
        severity = _severity(rng, category, n_reports, base_ts.hour)
        resolve = int(np.clip(25 + severity * 55 + rng.normal(0, 12), 15, 360))
        cluster_id = f"flood-{cluster_no:03d}"
        for off in offsets:
            ts = base_ts + pd.Timedelta(minutes=int(off))
            template = templates_by_cat[category][int(rng.integers(0, len(templates_by_cat[category])))]
            rows.append(_make_incident_row(rng, ts, node_id, category, template, cluster_id, severity, resolve))
        cluster_no += 1

    for _ in range(82):
        day = int(rng.integers(0, days))
        hour = int(rng.choice([7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]))
        category = str(rng.choice(CATEGORIES))
        node_id = str(rng.choice(CATEGORY_NODES[category]))
        base_ts = start + pd.Timedelta(days=day, hours=hour, minutes=int(rng.integers(0, 60)))
        n_reports = int(rng.integers(5, 19))
        span = int(rng.integers(5, 21))
        severity = _severity(rng, category, n_reports, hour)
        resolve = int(np.clip(25 + severity * 55 + rng.normal(0, 14), 15, 420))
        cluster_id = f"flood-{cluster_no:03d}"
        for _ in range(n_reports):
            ts = base_ts + pd.Timedelta(minutes=int(rng.integers(0, span)))
            template = templates_by_cat[category][int(rng.integers(0, len(templates_by_cat[category])))]
            rows.append(_make_incident_row(rng, ts, node_id, category, template, cluster_id, severity, resolve))
        cluster_no += 1

    for i in range(70):
        day = int(rng.integers(0, days))
        hour = int(rng.integers(0, 24))
        category = str(rng.choice(CATEGORIES))
        node_id = str(rng.choice(list(graph.nodes.keys())))
        ts = start + pd.Timedelta(days=day, hours=hour, minutes=int(rng.integers(0, 60)))
        severity = _severity(rng, category, 1, hour)
        resolve = int(np.clip(20 + severity * 40 + rng.normal(0, 15), 10, 300))
        template = templates_by_cat[category][int(rng.integers(0, len(templates_by_cat[category])))]
        rows.append(_make_incident_row(rng, ts, node_id, category, template, f"single-{i:03d}", severity, resolve))

    df = pd.DataFrame(rows)
    df["reported_at"] = pd.to_datetime(df["reported_at"])
    return df.sort_values("reported_at").reset_index(drop=True)


def simulate_mess(days: int = MESS_DAYS, seed: int = SEED + 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp(ANCHOR)
    index = pd.date_range(start, periods=days, freq="D")
    ts = pd.Series(index, index=index)
    cal = _calendar(ts)
    weather = _weather(ts, rng)
    rows = []
    for mess_id, meal in BASE_HEADCOUNT:
        base = BASE_HEADCOUNT[(mess_id, meal)]
        headcounts = []
        menus = []
        for day in range(days):
            weekend = int(cal["is_weekend"].iloc[day])
            exam = int(cal["is_exam"].iloc[day])
            rain = int(weather["rain"].iloc[day])
            menu = float(rng.uniform(0.82, 1.12))
            menus.append(menu)
            day_factor = 1 + (0.025 * day / days)
            weekend_factor = 1 - (0.24 if meal in ("breakfast", "snack") else 0.12) * weekend
            value = base * weekend_factor * (1 + 0.05 * exam) * (1 + 0.035 * rain) * menu * day_factor
            value *= 1 + rng.normal(0, 0.055)
            headcounts.append(max(20, value))
        series = pd.Series(headcounts)
        lag7 = series.shift(7).bfill()
        lag1 = series.shift(1).bfill()
        for day, headcount in enumerate(headcounts):
            portion = MEAL_PORTION_KG[meal]
            prepared = lag7.iloc[day] * portion * 1.12 * (1 + rng.normal(0, 0.04))
            consumed = headcount * portion * 0.92
            waste = max(0.0, prepared - consumed)
            rows.append(
                {
                    "date": index[day].date().isoformat(),
                    "mess_id": mess_id,
                    "meal": meal,
                    "headcount": int(round(headcount)),
                    "prepared_kg": round(prepared, 1),
                    "waste_kg": round(waste, 1),
                    "menu_score": round(float(menus[day]), 3),
                    "lag7_headcount": round(float(lag7.iloc[day]), 1),
                    "lag1_headcount": round(float(lag1.iloc[day]), 1),
                    "is_weekend": int(cal["is_weekend"].iloc[day]),
                    "is_exam": int(cal["is_exam"].iloc[day]),
                    "is_holiday": int(cal["is_holiday"].iloc[day]),
                    "rain": int(weather["rain"].iloc[day]),
                    "temp_c": float(weather["temp_c"].iloc[day]),
                    "day_index": int(cal["day_index"].iloc[day]),
                }
            )
    df = pd.DataFrame(rows).sort_values(["date", "mess_id", "meal"]).reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])
    return df


CART_LOOPS = [
    ("cart-01", "CART-01", ["gate_main", "canteen_main", "vending_hub", "foodcourt", "medical", "gate_main"], 0),
    ("cart-02", "CART-02", ["gate_main", "hostel_b2", "laundry", "mess_main", "canteen_main", "gate_main"], 37),
    ("cart-03", "CART-03", ["library", "block_a", "mess_main", "hostel_b1", "library"], 63),
    ("cart-04", "CART-04", ["gate_north", "sports", "amphitheatre", "foodcourt", "gate_north"], 21),
    ("cart-05", "CART-05", ["hostel_g1", "medical", "gate_main", "vending_hub", "hostel_g1"], 48),
    ("cart-06", "CART-06", ["library", "block_b", "block_c", "canteen_north", "library"], 80),
]


def simulate_carts(ts: pd.Timestamp | str, graph: CampusGraph | None = None) -> list[dict]:
    graph = graph or default_graph()
    ts = pd.Timestamp(ts)
    minute = ts.hour * 60 + ts.minute
    carts = []
    for idx, (cart_id, label, loop, offset) in enumerate(CART_LOOPS):
        segments = []
        total = 0.0
        for a, b in zip(loop, loop[1:]):
            dist = graph.distance_m(a, b)
            segments.append((a, b, dist))
            total += dist
        progress_m = (minute * 0.42 + offset * 7.5) % max(total, 1.0)
        running = 0.0
        current, nxt, local = loop[0], loop[1], 0.0
        for a, b, dist in segments:
            if progress_m <= running + dist:
                current, nxt = a, b
                local = (progress_m - running) / max(dist, 1.0)
                break
            running += dist
        status = "available" if idx % 3 != 1 else "on_trip"
        if idx == 5:
            status = "charging"
        carts.append(
            {
                "id": cart_id,
                "label": label,
                "node_id": current,
                "next_node": nxt,
                "status": status,
                "capacity": 4,
                "progress": round(local, 2),
            }
        )
    return carts


def simulate_all(force: bool = False) -> dict[str, str]:
    from .config import RAW_DIR

    paths = {
        "telemetry": RAW_DIR / "telemetry.csv",
        "incidents": RAW_DIR / "incidents.csv",
        "mess": RAW_DIR / "mess.csv",
    }
    if force or not paths["telemetry"].exists():
        simulate_telemetry().to_csv(paths["telemetry"], index=False)
    if force or not paths["incidents"].exists():
        simulate_incidents().to_csv(paths["incidents"], index=False)
    if force or not paths["mess"].exists():
        simulate_mess().to_csv(paths["mess"], index=False)
    return {k: str(v) for k, v in paths.items()}
