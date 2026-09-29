"""Capacity-aware NetworkX evacuation routing."""
from __future__ import annotations

from math import inf
from typing import Any

import networkx as nx

_NETWORK: dict[str, Any] = {"nodes": [], "edges": []}


def configure_road_network(road_network: dict[str, Any]) -> None:
    global _NETWORK
    _NETWORK = road_network


def _graph(flooded_road_ids: list[str]) -> tuple[nx.Graph, dict[str, dict[str, Any]]]:
    graph = nx.Graph()
    nodes = {node["id"]: node for node in _NETWORK.get("nodes", [])}
    for node_id, node in nodes.items():
        graph.add_node(node_id, **node)
    flooded = set(flooded_road_ids)
    for edge in _NETWORK.get("edges", []):
        graph.add_edge(edge["from"], edge["to"], id=edge["id"], name=edge["name"],
                       weight=inf if edge["id"] in flooded else float(edge["travel_time_min"]))
    return graph, nodes


def _nearest_node(coords: tuple[float, float], nodes: dict[str, dict[str, Any]]) -> str:
    lat, lng = coords
    return min(nodes, key=lambda key: (float(nodes[key]["lat"]) - lat) ** 2 + (float(nodes[key]["lng"]) - lng) ** 2)


def get_flood_safe_route(start_ward_coords: tuple[float, float], shelters_data: list[dict[str, Any]], flooded_road_ids: list[str]) -> dict[str, Any] | None:
    """Find the shortest viable route to a shelter that still has capacity."""
    graph, nodes = _graph(flooded_road_ids)
    if not nodes:
        raise RuntimeError("road network is not configured")
    start = _nearest_node(start_ward_coords, nodes)
    best: dict[str, Any] | None = None
    for shelter in shelters_data:
        if int(shelter["current_occupancy"]) >= int(shelter["capacity"]):
            continue
        target = shelter.get("road_node") or _nearest_node((shelter["lat"], shelter["lng"]), nodes)
        try:
            path = nx.shortest_path(graph, start, target, weight="weight")
            minutes = nx.path_weight(graph, path, "weight")
        except nx.NetworkXNoPath:
            continue
        if minutes == inf:
            continue
        route = {"shelter_id": shelter["id"], "shelter_name": shelter["name"], "travel_time_min": round(minutes, 1),
                 "path_node_ids": path, "coordinates": [[nodes[key]["lat"], nodes[key]["lng"]] for key in path],
                 "remaining_capacity": int(shelter["capacity"]) - int(shelter["current_occupancy"])}
        if best is None or route["travel_time_min"] < best["travel_time_min"]:
            best = route
    return best
