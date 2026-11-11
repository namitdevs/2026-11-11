from __future__ import annotations

import math

import pytest

from src.graph import default_graph


@pytest.fixture(scope="module")
def graph():
    return default_graph()


def test_graph_is_connected_and_symmetric(graph):
    assert len(graph.nodes) == 20
    assert len(graph.edges) == 35
    for node_id, edges in graph.adj.items():
        assert node_id in graph.nodes
        for edge in edges:
            neighbour = edge["v"] if edge["u"] == node_id else edge["u"]
            assert neighbour in graph.nodes
            reverse = graph.edge_between(neighbour, node_id)
            assert reverse is not None
            assert reverse["distance_m"] == pytest.approx(edge["distance_m"])
            assert edge["distance_m"] > 0


def test_shortest_path_is_a_walk_on_the_graph(graph):
    for origin, destination in [
        ("gate_main", "library"),
        ("hostel_b1", "sports"),
        ("mess_north", "medical"),
        ("amphitheatre", "block_a"),
    ]:
        result = graph.shortest_path(origin, destination, mode="fastest")
        path = result["path"]
        assert path[0] == origin and path[-1] == destination
        total = 0.0
        for u, v in zip(path, path[1:]):
            edge = graph.edge_between(u, v)
            assert edge is not None
            total += edge["distance_m"]
        assert result["distance_m"] == pytest.approx(total, abs=0.11)


def test_fastest_is_never_longer_than_safest(graph):
    for origin, destination in [("gate_main", "library"), ("block_d", "hostel_g1"), ("gate_north", "mess_main")]:
        fastest = graph.shortest_path(origin, destination, mode="fastest")
        safest = graph.shortest_path(origin, destination, mode="safest", night=True)
        assert fastest["distance_m"] <= safest["distance_m"] + 1e-6
        assert 0.0 <= safest["risk_index"] <= 100.0


def test_safest_night_route_prefers_lit_edges(graph):
    day = graph.shortest_path("block_d", "hostel_g1", mode="safest", night=False)
    night = graph.shortest_path("block_d", "hostel_g1", mode="safest", night=True)
    # Night weighting may pick a longer but fully lit path, so the night route
    # must be no riskier than the one chosen without lighting penalties.
    assert night["risk_index"] <= day["risk_index"]
    night_edges = [graph.edge_between(u, v) for u, v in zip(night["path"], night["path"][1:])]
    assert all(edge is not None for edge in night_edges)
    assert all(edge["lit"] and edge["cctv"] for edge in night_edges)


def test_accessible_mode_excludes_stairs(graph):
    stairs = [edge for edge in graph.edges if edge["stairs"]]
    assert stairs, "fixture must include at least one stair edge"
    result = graph.shortest_path("library", "block_a", mode="fastest", accessible=True)
    used = [graph.edge_between(u, v) for u, v in zip(result["path"], result["path"][1:])]
    assert used
    assert not any(edge["stairs"] for edge in used)


def test_crowd_and_incident_pressure_increase_risk(graph):
    base = graph.shortest_path("gate_main", "library", mode="safest", night=True)
    pressured = graph.shortest_path(
        "gate_main",
        "library",
        mode="safest",
        night=True,
        crowd={"vending_hub": 1.0, "block_b": 1.0, "gate_main": 1.0},
        incidents={"vending_hub": 3, "block_b": 3, "gate_main": 3},
    )
    assert pressured["risk_index"] >= base["risk_index"]


def test_origin_equals_destination_and_unknown_nodes(graph):
    same = graph.shortest_path("library", "library", mode="safest")
    assert same["path"] == ["library"]
    assert same["distance_m"] == 0.0
    with pytest.raises(KeyError):
        graph.shortest_path("library", "moon_base")
    assert math.isinf(graph.distance_m("library", "moon_base"))


def test_routing_is_deterministic(graph):
    first = graph.shortest_path("gate_main", "hostel_g1", mode="safest", night=True)
    second = graph.shortest_path("gate_main", "hostel_g1", mode="safest", night=True)
    assert first == second
