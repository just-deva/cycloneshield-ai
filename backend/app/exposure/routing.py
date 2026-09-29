"""Flood-aware evacuation routing on the real OSM road graph (NetworkX).

Graph: nodes = OSM way vertices (rounded to 1e-5 deg), edges between consecutive vertices, travel time from
length and a class-based free-flow speed. A node is BLOCKED when modelled flood depth >= 0.3 m (vehicle
passability threshold after Pregnolato et al. 2017; exact curve not re-verified), or when the modelled
pluvial state marks it as waterlogged. Routing is multi-source Dijkstra from all SAFE shelters, so every
origin gets its nearest reachable shelter; an origin with no route gets an explicit "shelter in place /
request air-lift" verdict instead of a silent blank.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import networkx as nx
import numpy as np
from scipy.spatial import cKDTree

from .assets import Asset, RoadWay

SPEED_KMH = {"motorway": 60, "motorway_link": 40, "trunk": 45, "trunk_link": 35, "primary": 35, "primary_link": 30,
             "secondary": 30, "secondary_link": 25, "tertiary": 25, "tertiary_link": 20}
PASSABLE_DEPTH_M = 0.3


@dataclass
class RoadGraph:
    graph: nx.Graph
    node_xy: np.ndarray            # (n, 2) lon, lat
    tree: cKDTree
    node_keys: list[tuple[int, int]]
    way_of_node: list[int]

    @property
    def n_nodes(self) -> int:
        return len(self.node_keys)

    def nearest(self, lat: float, lon: float) -> tuple[int, float]:
        d, i = self.tree.query([lat, lon * math.cos(math.radians(lat))])
        return int(i), float(d * 111.195)


def build_graph(roads: list[RoadWay]) -> RoadGraph:
    g = nx.Graph()
    index: dict[tuple[int, int], int] = {}
    xy: list[tuple[float, float]] = []
    way_of: list[int] = []

    def node(lon: float, lat: float, way_i: int) -> int:
        key = (int(round(lon * 1e5)), int(round(lat * 1e5)))
        i = index.get(key)
        if i is None:
            i = len(xy)
            index[key] = i
            xy.append((lon, lat))
            way_of.append(way_i)
        return i

    for wi, way in enumerate(roads):
        speed = SPEED_KMH.get(way.highway, 25)
        prev = None
        for lon, lat in way.coords:
            cur = node(float(lon), float(lat), wi)
            if prev is not None and prev != cur:
                (x0, y0), (x1, y1) = xy[prev], xy[cur]
                km = math.hypot((x1 - x0) * 111.195 * math.cos(math.radians((y0 + y1) / 2)), (y1 - y0) * 111.195)
                g.add_edge(prev, cur, km=km, minutes=km / speed * 60.0, way=wi)
            prev = cur
    arr = np.asarray(xy)
    keys = list(index)
    tree = cKDTree(np.c_[arr[:, 1], arr[:, 0] * math.cos(math.radians(float(arr[:, 1].mean())))])
    return RoadGraph(g, arr, tree, keys, way_of)


def route_origins(rg: RoadGraph, origins: list[Asset], shelters: list[Asset], blocked: np.ndarray) -> list[dict]:
    """Nearest safe shelter for each origin over the unblocked network.

    `blocked` is a boolean array over graph nodes. Returns one dict per origin.
    """
    g = rg.graph
    view = nx.subgraph_view(g, filter_node=lambda n: not blocked[n])
    sh_nodes: dict[int, Asset] = {}
    for s in shelters:
        i, d_km = rg.nearest(s.lat, s.lon)
        if d_km < 1.0 and not blocked[i]:
            sh_nodes.setdefault(i, s)
    out: list[dict] = []
    if not sh_nodes:
        return [{"origin": o.name, "origin_id": o.id, "status": "no_safe_shelter"} for o in origins]
    dist, paths = nx.multi_source_dijkstra(view, list(sh_nodes), weight="minutes")
    for o in origins:
        i, d_km = rg.nearest(o.lat, o.lon)
        rec = {"origin": o.name, "origin_id": o.id, "lat": o.lat, "lon": o.lon, "population": o.props.get("population")}
        if d_km > 1.5:
            rec["status"] = "off_network"
        elif blocked[i]:
            rec["status"] = "origin_flooded"
        elif i in paths:
            path = paths[i][::-1]                    # origin -> shelter
            sh = sh_nodes[path[-1]]
            rec.update(status="route", shelter=sh.name, shelter_id=sh.id, minutes=round(dist[i] + d_km / 20 * 60, 1),
                       coords=[[float(rg.node_xy[n][1]), float(rg.node_xy[n][0])] for n in path[::max(1, len(path) // 60)]] +
                              [[float(rg.node_xy[path[-1]][1]), float(rg.node_xy[path[-1]][0])]])
        else:
            rec["status"] = "no_route"
        out.append(rec)
    return out
