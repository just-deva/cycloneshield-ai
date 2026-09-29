"""Load critical-infrastructure assets for a tenant from its OSM GeoJSON extracts."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from ..config import Tenant

DESIGNATED = re.compile(r"cyclone|shelter|MPCS|flood relief", re.I)
ARTERIAL = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link"}


@dataclass
class Asset:
    id: str
    kind: str                 # hospital | substation | shelter | place
    name: str
    lat: float
    lon: float
    props: dict = field(default_factory=dict)


@dataclass
class RoadWay:
    id: str
    name: str
    ref: str
    highway: str
    bridge: bool
    coords: np.ndarray        # (n, 2) lon, lat

    @property
    def arterial(self) -> bool:
        return self.highway in ARTERIAL


@dataclass
class LineAsset:
    id: str
    voltage: str
    kind: str                 # line | minor_line
    coords: np.ndarray


@dataclass
class Exposure:
    hospitals: list[Asset]
    clinics: list[Asset]
    substations: list[Asset]
    shelters: list[Asset]
    places: list[Asset]
    roads: list[RoadWay]
    power_lines: list[LineAsset]
    source_counts: dict


def _clip_runs(coords: np.ndarray, bbox: list[float], margin: float = 0.002) -> list[np.ndarray]:
    """Keep contiguous runs of vertices inside the bbox (OSM 'out geom' returns whole ways, not clipped)."""
    s, w, n, e = bbox
    inside = (coords[:, 1] >= s - margin) & (coords[:, 1] <= n + margin) & (coords[:, 0] >= w - margin) & (coords[:, 0] <= e + margin)
    runs, start = [], None
    for i, ok in enumerate(inside):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if i - start >= 2:
                runs.append(coords[start:i])
            start = None
    if start is not None and len(coords) - start >= 2:
        runs.append(coords[start:])
    return runs


def _read(tenant: Tenant, layer: str) -> list[dict]:
    p = tenant.dir / f"{layer}.geojson"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("features", [])


def _pt(f: dict) -> tuple[float, float] | None:
    g = f["geometry"]
    if g["type"] == "Point":
        return g["coordinates"][1], g["coordinates"][0]
    if g["type"] == "LineString" and g["coordinates"]:
        c = np.asarray(g["coordinates"])
        return float(c[:, 1].mean()), float(c[:, 0].mean())
    return None


def _name(props: dict, fallback: str) -> str:
    return props.get("name:en") or props.get("name") or fallback


@lru_cache(maxsize=8)
def load_exposure(tenant_id: str) -> Exposure:
    from ..config import get_tenant
    t = get_tenant(tenant_id)
    hospitals, clinics, substations, shelters, places = [], [], [], [], []
    seen: set[str] = set()
    for f in _read(t, "hospitals"):
        pt = _pt(f)
        if not pt or f["properties"]["osm"] in seen:
            continue
        seen.add(f["properties"]["osm"])
        p = f["properties"]
        is_hospital = p.get("amenity") == "hospital" or p.get("healthcare") == "hospital"
        a = Asset(p["osm"], "hospital" if is_hospital else "clinic", _name(p, "Hospital (unnamed)" if is_hospital else "Clinic (unnamed)"),
                  pt[0], pt[1], {k: p[k] for k in ("beds", "operator", "healthcare") if k in p})
        (hospitals if is_hospital else clinics).append(a)
    for f in _read(t, "substations"):
        pt = _pt(f)
        if pt:
            p = f["properties"]
            kind = "power plant" if p.get("power") == "plant" else "substation"
            substations.append(Asset(p["osm"], "substation", _name(p, f"{kind.title()} (unnamed)"), pt[0], pt[1],
                                     {k: p[k] for k in ("voltage", "operator", "power") if k in p}))
    for f in _read(t, "shelters"):
        pt = _pt(f)
        if not pt:
            continue
        p = f["properties"]
        nm = _name(p, "")
        designated = bool(DESIGNATED.search(nm)) or p.get("emergency") == "assembly_point"
        kind = p.get("amenity") or p.get("emergency") or "building"
        if not nm and not designated:
            continue                      # unnamed candidates are not useful to officers
        shelters.append(Asset(p["osm"], "shelter", nm or f"{kind} (unnamed)", pt[0], pt[1],
                              {"designated": designated, "type": kind, "capacity": p.get("capacity")}))
    for f in _read(t, "places"):
        pt = _pt(f)
        if pt:
            p = f["properties"]
            pop = None
            try:
                pop = int(str(p.get("population", "")).replace(",", "")) if p.get("population") else None
            except ValueError:
                pop = None
            places.append(Asset(p["osm"], "place", _name(p, "place"), pt[0], pt[1], {"place": p.get("place"), "population": pop}))
    roads = []
    for f in _read(t, "roads"):
        g = f["geometry"]
        if g["type"] != "LineString" or len(g["coordinates"]) < 2:
            continue
        p = f["properties"]
        for ri, run in enumerate(_clip_runs(np.asarray(g["coordinates"], dtype=float), t.bbox)):
            roads.append(RoadWay(f"{p['osm']}#{ri}", p.get("name", ""), p.get("ref", ""), p.get("highway", "unclassified"),
                                 p.get("bridge", "no") not in ("no", ""), run))
    lines = []
    for f in _read(t, "power_lines") + _read(t, "power_minor"):
        g = f["geometry"]
        if g["type"] == "LineString" and len(g["coordinates"]) >= 2:
            p = f["properties"]
            for ri, run in enumerate(_clip_runs(np.asarray(g["coordinates"], dtype=float), t.bbox)):
                lines.append(LineAsset(f"{p['osm']}#{ri}", p.get("voltage", ""), p.get("power", "line"), run))
    counts = {"hospitals": len(hospitals), "clinics": len(clinics), "substations": len(substations),
              "shelters": len(shelters), "designated_shelters": sum(1 for s in shelters if s.props.get("designated")),
              "places": len(places), "road_ways": len(roads), "arterial_road_ways": sum(1 for r in roads if r.arterial),
              "power_line_ways": len(lines)}
    return Exposure(hospitals, clinics, substations, shelters, places, roads, lines, counts)
