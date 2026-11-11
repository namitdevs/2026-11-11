"""One unified campus graph powering all five capabilities.

Pillars 1-3 read node/edge context from it, pillar 4 routes on it, and the
wayfinding + cart layer is just another view over the same adjacency map.
"""
from __future__ import annotations

import heapq
import math
from functools import lru_cache

# Display names follow the labels printed on the TIET campus map used by the
# wayfinding view. Internal IDs are kept stable so the graph, simulator and
# snapshot contracts do not churn when a building label is corrected.
NODES = [
    ("gate_main", "Main Entrance", "transit", 832.1, 537.4, 0, 0.9),
    ("gate_north", "North Gate", "transit", 450.0, 46.9, 0, 0.6),
    ("block_a", "CS Block", "academic", 642.9, 270.7, 320, 0.85),
    ("block_b", "G Block", "academic", 639.3, 357.2, 280, 0.8),
    ("block_c", "B Block", "academic", 678.6, 363.6, 240, 0.75),
    ("block_d", "C Block", "academic", 725.0, 365.3, 200, 0.7),
    ("library", "Central Library", "academic", 675.0, 313.5, 420, 0.9),
    ("canteen_main", "Canteen", "food", 585.7, 440.4, 260, 0.95),
    ("canteen_north", "Streat Cafe", "food", 735.7, 464.6, 190, 0.7),
    ("foodcourt", "Food Court", "food", 521.4, 379.8, 320, 0.9),
    ("mess_main", "Aahar", "food", 742.9, 430.7, 700, 0.85),
    ("mess_north", "Staff Quarters", "service", 642.9, 169.7, 420, 0.6),
    ("hostel_b1", "Prithvi Hall", "residential", 214.3, 505.1, 0, 0.55),
    ("hostel_b2", "Vyom Hall", "residential", 278.6, 505.1, 0, 0.55),
    ("hostel_g1", "Vahni Hall", "residential", 539.3, 492.9, 0, 0.5),
    ("laundry", "Stationery & ATM", "service", 657.1, 484.8, 90, 0.6),
    ("sports", "Sports Complex", "sports", 482.1, 234.3, 160, 0.5),
    ("vending_hub", "TAN Block", "service", 564.3, 367.7, 70, 0.75),
    ("medical", "Main Administrative Block", "service", 707.1, 525.3, 40, 0.5),
    ("amphitheatre", "Open Air Theatre (OAT)", "landmark", 260.7, 274.8, 0, 0.4),
]

EDGES = [
    ("gate_main", "canteen_main", 265, True, True, False, 0.9),
    ("gate_main", "foodcourt", 349, True, True, False, 0.85),
    ("gate_main", "medical", 126, True, True, False, 0.8),
    ("gate_main", "hostel_b2", 555, True, False, False, 0.7),
    ("gate_main", "hostel_g1", 296, True, True, False, 0.75),
    ("gate_main", "vending_hub", 318, True, True, False, 0.7),
    ("hostel_b2", "hostel_b1", 64, True, False, False, 0.6),
    ("hostel_b2", "laundry", 379, False, False, False, 0.5),
    ("hostel_b1", "mess_main", 534, True, True, False, 0.7),
    ("mess_main", "canteen_main", 158, True, True, False, 0.8),
    ("mess_main", "library", 135, False, False, False, 0.5),
    ("library", "block_a", 54, False, True, True, 0.6),
    ("block_a", "block_b", 87, True, True, False, 0.85),
    ("block_b", "block_c", 40, True, True, False, 0.85),
    ("block_c", "block_d", 46, True, True, False, 0.8),
    ("block_d", "canteen_north", 100, True, True, False, 0.75),
    ("canteen_north", "mess_north", 309, True, False, False, 0.6),
    ("mess_north", "gate_north", 229, True, True, False, 0.6),
    ("gate_north", "sports", 190, True, False, False, 0.5),
    ("sports", "block_d", 277, False, False, False, 0.4),
    ("sports", "amphitheatre", 225, False, False, False, 0.3),
    ("amphitheatre", "foodcourt", 281, True, True, False, 0.5),
    ("foodcourt", "vending_hub", 45, True, True, False, 0.8),
    ("vending_hub", "laundry", 150, False, False, False, 0.4),
    ("vending_hub", "canteen_main", 77, True, True, False, 0.85),
    ("canteen_main", "block_b", 99, True, True, False, 0.85),
    ("foodcourt", "block_c", 158, True, True, False, 0.8),
    ("medical", "foodcourt", 236, True, True, False, 0.7),
    ("medical", "hostel_g1", 171, False, False, False, 0.4),
    ("hostel_g1", "amphitheatre", 354, False, False, False, 0.35),
    ("laundry", "hostel_b1", 444, True, False, False, 0.55),
    ("block_a", "mess_main", 189, False, False, False, 0.45),
    ("block_b", "vending_hub", 77, True, True, False, 0.8),
    ("canteen_north", "sports", 342, True, False, False, 0.5),
    ("hostel_g1", "gate_north", 455, True, False, False, 0.4),
]


class CampusGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.adj: dict[str, list[dict]] = {}
        for node_id, label, kind, x, y, capacity, footfall in NODES:
            self.nodes[node_id] = {
                "id": node_id,
                "label": label,
                "kind": kind,
                "x": float(x),
                "y": float(y),
                "capacity": int(capacity),
                "footfall": float(footfall),
            }
        for idx, (u, v, dist, lit, cctv, stairs, footfall) in enumerate(EDGES):
            edge = {
                "id": f"e{idx:02d}",
                "u": u,
                "v": v,
                "distance_m": float(dist),
                "lit": bool(lit),
                "cctv": bool(cctv),
                "stairs": bool(stairs),
                "footfall": float(footfall),
            }
            self.edges.append(edge)
            self.adj.setdefault(u, []).append(edge)
            self.adj.setdefault(v, []).append(edge)
        self._distance_cache: dict[tuple[str, str], float] = {}

    # ---- basic accessors -------------------------------------------------
    def label(self, node_id: str) -> str:
        return self.nodes[node_id]["label"]

    def neighbors(self, node_id: str) -> list[tuple[str, dict]]:
        out = []
        for edge in self.adj.get(node_id, []):
            out.append((edge["v"] if edge["u"] == node_id else edge["u"], edge))
        return out

    def edge_between(self, u: str, v: str) -> dict | None:
        for edge in self.adj.get(u, []):
            if {edge["u"], edge["v"]} == {u, v}:
                return edge
        return None

    def edge_lit_ratio(self, node_id: str) -> float:
        edges = self.adj.get(node_id, [])
        if not edges:
            return 0.0
        return sum(1.0 for e in edges if e["lit"]) / len(edges)

    # ---- risk model ------------------------------------------------------
    @staticmethod
    def edge_risk(edge: dict, night: bool, crowd: float, incidents: int) -> float:
        """Dimensionless risk multiplier in [1.0, ~2.6]."""
        penalty = 0.0
        if not edge["lit"]:
            penalty += 0.45
        if not edge["cctv"]:
            penalty += 0.15
        if edge["footfall"] < 0.35:
            penalty += 0.20
        penalty += 0.35 * max(0.0, crowd - 0.65)
        penalty += 0.60 * min(1.0, incidents / 3.0)
        if night:
            penalty *= 1.85
        return 1.0 + penalty

    def _cost(self, edge: dict, mode: str, night: bool, crowd: dict[str, float],
              incidents: dict[str, int], accessible: bool) -> float:
        if accessible and edge["stairs"]:
            return math.inf
        distance = edge["distance_m"]
        if mode == "fastest":
            return distance
        u, v = edge["u"], edge["v"]
        node_crowd = max(crowd.get(u, 0.0), crowd.get(v, 0.0))
        node_incidents = max(incidents.get(u, 0), incidents.get(v, 0))
        return distance * self.edge_risk(edge, night, node_crowd, node_incidents)

    def shortest_path(
        self,
        origin: str,
        destination: str,
        mode: str = "fastest",
        night: bool = False,
        crowd: dict[str, float] | None = None,
        incidents: dict[str, int] | None = None,
        accessible: bool = False,
    ) -> dict:
        if origin not in self.nodes or destination not in self.nodes:
            raise KeyError("unknown campus node")
        crowd = crowd or {}
        incidents = incidents or {}
        if origin == destination:
            return {"path": [origin], "distance_m": 0.0, "cost": 0.0, "risk_index": 0.0}

        queue: list[tuple[float, str]] = [(0.0, origin)]
        best = {origin: 0.0}
        distances = {origin: 0.0}
        prev: dict[str, tuple[str, dict, float]] = {}
        visited: set[str] = set()

        while queue:
            cost, node = heapq.heappop(queue)
            if node in visited:
                continue
            visited.add(node)
            if node == destination:
                break
            for neighbor, edge in self.neighbors(node):
                step = self._cost(edge, mode, night, crowd, incidents, accessible)
                if math.isinf(step):
                    continue
                new_cost = cost + step
                if new_cost < best.get(neighbor, math.inf):
                    best[neighbor] = new_cost
                    distances[neighbor] = distances[node] + edge["distance_m"]
                    prev[neighbor] = (node, edge, step)
                    heapq.heappush(queue, (new_cost, neighbor))

        if destination not in prev:
            raise ValueError("no route available for the given constraints")

        path = [destination]
        cursor = destination
        risk_cost = 0.0
        while cursor != origin:
            parent, edge, step = prev[cursor]
            risk_cost += edge["distance_m"] * self.edge_risk(
                edge,
                night,
                max(crowd.get(edge["u"], 0.0), crowd.get(edge["v"], 0.0)),
                max(incidents.get(edge["u"], 0), incidents.get(edge["v"], 0)),
            )
            path.append(parent)
            cursor = parent
        path.reverse()
        total = distances[destination]
        risk_index = 0.0 if total == 0 else max(0.0, min(100.0, 100.0 * (risk_cost - total) / (total * 1.6)))
        return {"path": path, "distance_m": round(total, 1), "cost": round(best[destination], 1),
                "risk_index": round(risk_index, 2)}

    def distance_m(self, a: str, b: str) -> float:
        key = (a, b) if a <= b else (b, a)
        if key in self._distance_cache:
            return self._distance_cache[key]
        if a == b:
            return 0.0
        try:
            result = self.shortest_path(a, b, mode="fastest")["distance_m"]
        except (KeyError, ValueError):
            result = math.inf
        self._distance_cache[key] = result
        return result

    @lru_cache(maxsize=1)
    def sensor_nodes(self) -> tuple[str, ...]:
        return tuple(n for n, data in self.nodes.items() if data["capacity"] > 0)

    def to_dict(self) -> dict:
        return {
            "nodes": list(self.nodes.values()),
            "edges": [
                {**edge, "risk": round(self.edge_risk(edge, True, 0.5, 1) - 1.0, 3)}
                for edge in self.edges
            ],
        }


def default_graph() -> CampusGraph:
    return CampusGraph()
