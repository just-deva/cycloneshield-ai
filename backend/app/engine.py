"""Simulation engine: storm -> hazards -> asset-level impacts -> evacuation routes.

One call to `simulate()` produces everything the UI, advisory generator, finance monitor and copilot need,
as plain JSON-safe dicts. All numbers in advisories must come from this result (never from the LLM).
"""
from __future__ import annotations

import hashlib
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from .config import Tenant, get_tenant, load_replay
from .exposure import impact as I
from .exposure.assets import Exposure, load_exposure
from .exposure.routing import RoadGraph, build_graph, route_origins
from .hazard import dem as D
from .hazard import inundation as INU
from .hazard import pluvial as PLU
from .hazard import rain as RAIN
from .hazard import surge as SURGE
from .hazard import wind as WIND
from .storms.model import Fix, Storm
from .storms.track import closest_approach, haversine_km, hourly_times, interpolate, motion_ms, scenario_storm

PLACE_RANK = {"city": 0, "town": 1, "suburb": 2, "quarter": 3, "neighbourhood": 4, "village": 5, "hamlet": 6}
ENSEMBLE_SHIFTS_KM = (-40.0, 0.0, 40.0)
ENSEMBLE_DKT = (-10.0, 0.0, 10.0)
SURGE_ONSET_LEAD_H = 3.0      # assumption: surge water reaches the coast ~3 h before peak onshore wind
SURGE_MIN_M = 0.3             # below this the storm surge is not treated as a flood hazard
RAIN_GRID_DEG = 0.015


@dataclass
class Context:
    tenant: Tenant
    dem: D.Dem
    hydro: dict
    dist_km: np.ndarray
    exposure: Exposure
    graph: RoadGraph | None
    sectors: list[dict]
    probes: dict
    rain_grid: dict
    node_info: dict | None


_CTX: dict[str, Context] = {}
_LOCK = threading.Lock()


def _place_sort(a):
    return (PLACE_RANK.get(a.props.get("place"), 9), -(a.props.get("population") or 0))


def get_context(tenant_id: str) -> Context:
    with _LOCK:
        if tenant_id in _CTX:
            return _CTX[tenant_id]
        tenant = get_tenant(tenant_id)
        dem = D.load_dem(tenant)
        hydro = PLU.load_hydro(tenant, dem)
        dist_km = INU.distance_from_sea_km(dem, hydro["sea"])
        hydro["basin_f"] = hydro["basin"].astype(np.float32)
        exp = load_exposure(tenant_id)
        graph = build_graph(exp.roads) if exp.roads else None

        sectors = []
        for s in tenant.sectors:
            ex, ny = INU.onshore_unit(dem, hydro["sea"], s.lat, s.lon)
            sectors.append({"cfg": s, "shelf": s.to_shelf(), "onshore": (ex, ny)})

        # probe points for wind / depth / rain: hospitals, substations, shelters, places, power-line vertices
        kinds, lats, lons, refs = [], [], [], []
        for group, kind in ((exp.hospitals, "hospital"), (exp.substations, "substation"),
                            (exp.shelters, "shelter"), (exp.places, "place")):
            for a in group:
                kinds.append(kind); lats.append(a.lat); lons.append(a.lon); refs.append(a)
        n_assets = len(kinds)
        line_slices = []
        for li, ln in enumerate(exp.power_lines):
            start = len(lats)
            for lon, lat in ln.coords:
                kinds.append("line_vertex"); lats.append(float(lat)); lons.append(float(lon)); refs.append(li)
            line_slices.append((start, len(lats)))
        probes = {"kind": np.array(kinds), "lat": np.array(lats), "lon": np.array(lons), "ref": refs,
                  "n_assets": n_assets, "line_slices": line_slices}

        # coarse rain grid (rain is smooth on the ~10 km scale)
        s_, w_, n_, e_ = tenant.bbox
        glat = np.arange(s_, n_ + RAIN_GRID_DEG, RAIN_GRID_DEG)
        glon = np.arange(w_, e_ + RAIN_GRID_DEG, RAIN_GRID_DEG)
        GLon, GLat = np.meshgrid(glon, glat)
        rain_grid = {"lat": GLat.ravel(), "lon": GLon.ravel(), "shape": GLat.shape, "glat": glat, "glon": glon}

        def gidx(lat, lon):
            ri = np.clip(np.round((np.asarray(lat) - glat[0]) / RAIN_GRID_DEG).astype(int), 0, len(glat) - 1)
            ci = np.clip(np.round((np.asarray(lon) - glon[0]) / RAIN_GRID_DEG).astype(int), 0, len(glon) - 1)
            return ri * len(glon) + ci
        rain_grid["idx"] = gidx
        probes["gidx"] = gidx(probes["lat"], probes["lon"]) if len(lats) else np.array([], dtype=int)

        node_info = None
        if graph is not None:
            nlat, nlon = graph.node_xy[:, 1], graph.node_xy[:, 0]
            node_info = {"lat": nlat, "lon": nlon, "gidx": gidx(nlat, nlon),
                         "corridor": dem.sample(hydro["upa_km2"], nlat, nlon, 0.0) >= 0.5,
                         "basin": dem.sample(hydro["basin_f"], nlat, nlon, 0.0) > 0.5}
        ctx = Context(tenant, dem, hydro, dist_km, exp, graph, sectors, probes, rain_grid, node_info)
        _CTX[tenant_id] = ctx
        return ctx


def _f(x) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


@dataclass
class Hazard:
    storm: Storm
    t0: datetime
    dmin_km: float
    times: list[datetime]
    hours: np.ndarray
    center: list[dict]
    wind: np.ndarray                 # [n_t, n_probe] km/h
    sector_peak: list[dict]
    depth_grid: np.ndarray | None
    flooded_km2: float
    probe_depth: np.ndarray
    rain_cum: np.ndarray             # [n_t, n_grid] mm
    r24: np.ndarray                  # [n_grid] mm (max 24-h)
    focus: dict


def compute_hazard(ctx: Context, storm: Storm, tide_m: float) -> Hazard:
    tenant = ctx.tenant
    P = ctx.probes
    t0, dmin = closest_approach(storm, tenant.focus.lat, tenant.focus.lon)
    times = hourly_times(storm, t0, 72.0, 12.0, 1.0)
    hours = np.array([(t - t0).total_seconds() / 3600.0 for t in times])
    n = len(times)
    nprobe = len(P["lat"])
    W = np.zeros((n, nprobe), dtype=np.float32)
    G = ctx.rain_grid
    rate = np.zeros((n, len(G["lat"])), dtype=np.float32)
    S = ctx.sectors
    sec_lat = np.array([s["cfg"].lat for s in S]); sec_lon = np.array([s["cfg"].lon for s in S])
    surge_t = np.zeros((n, len(S))); onshore_t = np.zeros((n, len(S)))
    center, focus_wind = [], np.zeros(n)
    for k, t in enumerate(times):
        fix = interpolate(storm, t)
        e, no = motion_ms(storm, t)
        hp = WIND.holland_params(fix)
        if nprobe:
            W[k] = WIND.wind_field(hp, P["lat"], P["lon"], e, no)["speed"] * 3.6
        sw = WIND.wind_field(hp, sec_lat, sec_lon, e, no)
        p_loc = WIND.pressure_hpa(hp, sw["r_km"])
        for j, s in enumerate(S):
            on = float(WIND.onshore_component(sw["u"][j:j + 1], sw["v"][j:j + 1], *s["onshore"])[0])
            onshore_t[k, j] = on
            surge_t[k, j] = SURGE.storm_tide_m(s["shelf"], on, float(p_loc[j]), 0.0, hp.penv_hpa)["surge_m"]
        fw = WIND.wind_field(hp, [tenant.focus.lat], [tenant.focus.lon], e, no)
        focus_wind[k] = fw["speed"][0] * 3.6
        rate[k] = RAIN.rcliper_rate_mm_h(fix.vmax_kt or 30.0, haversine_km(fix.lat, fix.lon, G["lat"], G["lon"]))
        center.append({"t": t.isoformat(), "h": round(float(hours[k]), 1), "lat": fix.lat, "lon": fix.lon,
                       "vmax_kt": _f(fix.vmax_kt), "mslp_hpa": _f(fix.mslp_hpa),
                       "dist_focus_km": round(float(haversine_km(fix.lat, fix.lon, tenant.focus.lat, tenant.focus.lon)), 1),
                       "focus_wind_kmh": round(float(focus_wind[k]), 1)})

    # rain: cumulative and 24-h maximum per grid cell
    cum = np.cumsum(rate, axis=0)
    padded = np.vstack([np.zeros((24, cum.shape[1]), dtype=np.float32), cum])
    r24 = (padded[24:] - padded[:-24]).max(axis=0)

    # surge per sector: peak surge, time of peak, storm tide = surge + tide
    sector_peak = []
    levels, sec_xy = {}, {}
    for j, s in enumerate(S):
        kpk = int(np.argmax(surge_t[:, j]))
        surge_m = float(surge_t[kpk, j])
        total = surge_m + tide_m if surge_m >= SURGE_MIN_M else 0.0
        levels[s["cfg"].id] = total
        sec_xy[s["cfg"].id] = (s["cfg"].lat, s["cfg"].lon)
        sector_peak.append({"id": s["cfg"].id, "lat": s["cfg"].lat, "lon": s["cfg"].lon, "surge_m": round(surge_m, 2),
                            "tide_m": tide_m, "storm_tide_m": round(total, 2), "peak_h": round(float(hours[kpk]), 1),
                            "onshore_ms_peak": round(float(onshore_t[kpk, j]), 1),
                            "shelf": f"L={s['cfg'].width_km:g} km, h={s['cfg'].depth_m:g} m, k={s['cfg'].k:g}",
                            "xu_reference_m": round(SURGE.xu_bathtub_reference_m(float(onshore_t[kpk, j])), 2)})
    depth_grid, flooded = None, 0.0
    if max(levels.values(), default=0.0) > 0:
        res = INU.flood_depth(ctx.dem, levels, sec_xy, ctx.hydro["sea"])
        depth_grid, flooded = res["depth"], res["flooded_km2"]
    probe_depth = (np.nan_to_num(ctx.dem.sample(depth_grid, P["lat"], P["lon"], 0.0), nan=0.0)
                   if depth_grid is not None and nprobe else np.zeros(nprobe))
    ifocus = int(np.argmax(focus_wind))
    gf = int(ctx.rain_grid["idx"](np.array([tenant.focus.lat]), np.array([tenant.focus.lon]))[0])
    focus = {"peak_wind_kmh": round(float(focus_wind.max()), 1), "peak_h": round(float(hours[ifocus]), 1),
             "rain24_mm": round(float(r24[gf]), 0), "rain_class": I.rain_class(float(r24[gf])),
             "category": I.imd_category(float(focus_wind.max())),
             "loss_ratio": round(I.emanuel_loss_ratio(float(focus_wind.max()) / 3.6), 4)}
    return Hazard(storm, t0, dmin, times, hours, center, W, sector_peak, depth_grid, flooded, probe_depth, cum, r24, focus)


def _sector_of(ctx: Context, lat, lon) -> np.ndarray:
    sl = np.array([[s["cfg"].lat, s["cfg"].lon] for s in ctx.sectors])
    la, lo = np.atleast_1d(lat), np.atleast_1d(lon)
    d = (la[:, None] - sl[None, :, 0]) ** 2 + ((lo[:, None] - sl[None, :, 1]) * math.cos(math.radians(float(la.mean())))) ** 2
    return d.argmin(axis=1)


def _assess_assets(ctx: Context, hz: Hazard, member_hits: np.ndarray | None) -> list[dict]:
    P = ctx.probes
    out: list[dict] = []
    hours = hz.hours
    sec_idx = _sector_of(ctx, P["lat"][:P["n_assets"]], P["lon"][:P["n_assets"]]) if P["n_assets"] else np.array([], dtype=int)
    for i in range(P["n_assets"]):
        kind = str(P["kind"][i])
        if kind == "place":
            continue
        a = P["ref"][i]
        w = hz.wind[:, i]
        depth = float(hz.probe_depth[i])
        g = P["gidx"][i]
        r24 = float(hz.r24[g])
        cum = hz.rain_cum[:, g]
        ri, ci = ctx.dem.rc(np.array([a.lat]), np.array([a.lon]))
        rr, cc = int(round(float(ri[0]))), int(round(float(ci[0])))
        h_, w_ = ctx.dem.shape
        inside = 0 <= rr < h_ and 0 <= cc < w_
        in_basin = bool(ctx.hydro["basin"][rr, cc]) if inside else False
        in_corr = bool(ctx.hydro["upa_km2"][rr, cc] >= 0.5) if inside else False
        pl = I.pluvial_state(r24, in_basin, in_corr)
        designated = bool(getattr(a, "props", {}).get("designated", False))
        status, reasons, usable = I.assess_point(kind, float(w.max()), depth, pl, designated)
        hazards = [h for h, on in (("wind", float(w.max()) >= I.GALE), ("surge", depth > 0), ("rain", pl != "none")) if on]
        score = float(w.max()) / 50.0 + depth * 3.0 + (2.0 if pl == "likely" else 1.0 if pl == "possible" else 0.0)
        t_surge = hz.sector_peak[int(sec_idx[i])]["peak_h"] - SURGE_ONSET_LEAD_H if depth > 0 else None
        onsets = {
            "gale_h": I.first_time(w, hours, I.GALE), "damaging_h": I.first_time(w, hours, I.DAMAGING),
            "destructive_h": I.first_time(w, hours, I.DESTRUCTIVE), "surge_h": t_surge,
            "pluvial_h": I.first_time(cum, hours, 60.0) if pl != "none" else None,
        }
        active = [v for k, v in onsets.items() if v is not None and (
            (k == "gale_h" and status != "ok") or k in ("damaging_h", "destructive_h", "surge_h", "pluvial_h"))]
        first = min(active) if active else None
        rec = {"id": a.id, "kind": kind, "name": a.name, "lat": a.lat, "lon": a.lon, "status": status, "reasons": reasons,
               "peak_wind_kmh": round(float(w.max()), 0), "peak_wind_h": round(float(hours[int(w.argmax())]), 1),
               "surge_depth_m": round(depth, 2), "rain24_mm": round(r24, 0), "rain_class": I.rain_class(r24),
               "pluvial": pl, "in_basin": in_basin, "in_corridor": in_corr, "first_impact_h": first,
               "onsets": onsets, "props": a.props, "hazards": hazards, "hazard_score": round(score, 2)}
        if kind == "shelter":
            rec["usable"] = usable
        if member_hits is not None:
            rec["scenario_hits"] = int(member_hits[i])
        out.append(rec)
    return out


def _roads(ctx: Context, hz: Hazard, top: int = 60) -> tuple[list[dict], dict]:
    exp = ctx.exposure
    ni = ctx.node_info
    rows, feats = [], []
    cut_km = arterial_km = 0.0
    hpr = {"motorway": 0, "trunk": 1, "primary": 2, "secondary": 3, "tertiary": 4}
    for way in exp.roads:
        base_hw = way.highway.replace("_link", "")
        lon, lat = way.coords[:, 0], way.coords[:, 1]
        depth = np.nan_to_num(ctx.dem.sample(hz.depth_grid, lat, lon, 0.0), nan=0.0) if hz.depth_grid is not None else np.zeros(len(lat))
        gi = ctx.rain_grid["idx"](lat, lon)
        r24 = hz.r24[gi]
        corr = ctx.dem.sample(ctx.hydro["upa_km2"], lat, lon, 0.0) >= 0.5
        basin = ctx.dem.sample(ctx.hydro["basin_f"], lat, lon, 0.0) > 0.5
        # 0 none, 1 possible (heavy), 2 likely (very heavy) - only in waterlogging BASINS (roads cross stream corridors on bridges)
        pl_seg = np.where(~basin, 0, np.where(r24 >= I.IMD_VERY_HEAVY, 2, np.where(r24 >= I.IMD_HEAVY, 1, 0)))
        seg_len = np.hypot(np.diff(lon) * 111.195 * np.cos(np.radians(lat[:-1])), np.diff(lat) * 111.195)
        total_km = float(seg_len.sum())
        if way.arterial:
            arterial_km += total_km
        cut = depth[:-1] >= I.PASSABLE_DEPTH_M
        plk = pl_seg[:-1] == 2
        bad = cut | plk
        if not bad.any() and not (depth > 0).any():
            continue
        bad_km = float(seg_len[bad].sum())
        if way.arterial:
            cut_km += bad_km
        status = "cut" if cut.any() else ("waterlogging_likely" if plk.any() else "watch")
        gsel = gi[int(np.argmax(np.where(bad, 1, 0)))] if bad.any() else gi[0]
        t_pl = I.first_time(hz.rain_cum[:, gsel], hz.hours, 60.0)
        sec = int(_sector_of(ctx, lat.mean(), lon.mean())[0])
        t_cut = hz.sector_peak[sec]["peak_h"] - SURGE_ONSET_LEAD_H if cut.any() else None
        first = min([x for x in (t_cut, t_pl if plk.any() else None) if x is not None], default=None)
        rows.append({"id": way.id, "name": way.name or way.ref or f"{way.highway} road", "ref": way.ref, "highway": way.highway,
                     "bridge": way.bridge, "status": status, "max_depth_m": round(float(depth.max()), 2),
                     "km_affected": round(bad_km, 2), "first_impact_h": first,
                     "cause": ("surge" if cut.any() else "") + ("+" if cut.any() and plk.any() else "") + ("heavy-rain waterlogging" if plk.any() else ""),
                     "_rank": hpr.get(base_hw, 5)})
        if (bad.any() and way.arterial) or cut.any():
            feats.append({"type": "Feature", "properties": {"name": way.name or way.ref, "status": status, "highway": way.highway},
                          "geometry": {"type": "LineString", "coordinates": [[float(x), float(y)] for x, y in way.coords[::2]] + [[float(lon[-1]), float(lat[-1])]]}})
    rows.sort(key=lambda r: (r["_rank"], -(r["km_affected"])))
    for r in rows:
        r.pop("_rank", None)
    named: dict[str, dict] = {}
    for r in rows:                              # merge ways with the same name/ref for the officer-facing table
        key = r["ref"] or r["name"]
        m = named.get(key)
        if m is None:
            named[key] = dict(r)
        else:
            m["km_affected"] = round(m["km_affected"] + r["km_affected"], 2)
            m["max_depth_m"] = max(m["max_depth_m"], r["max_depth_m"])
            m["first_impact_h"] = min([x for x in (m["first_impact_h"], r["first_impact_h"]) if x is not None], default=None)
            if r["status"] == "cut":
                m["status"] = "cut"
    merged = sorted(named.values(), key=lambda r: (r["highway"] not in ("motorway", "trunk", "primary", "secondary"), -r["km_affected"]))[:top]
    return merged, {"features": feats[:400], "arterial_km_total": round(arterial_km, 1), "arterial_km_affected": round(cut_km, 1)}


def _lines_summary(ctx: Context, hz: Hazard) -> dict:
    P = ctx.probes
    bands = {"gale_62": 0.0, "damaging_89": 0.0, "destructive_118": 0.0}
    flooded_km = total_km = 0.0
    wpeak = hz.wind.max(axis=0) if hz.wind.size else np.array([])
    for li, (a, b) in enumerate(P["line_slices"]):
        ln = ctx.exposure.power_lines[li]
        lon, lat = ln.coords[:, 0], ln.coords[:, 1]
        seg = np.hypot(np.diff(lon) * 111.195 * np.cos(np.radians(lat[:-1])), np.diff(lat) * 111.195)
        w = wpeak[a:b - 1]
        d = hz.probe_depth[a:b - 1]
        total_km += float(seg.sum())
        bands["gale_62"] += float(seg[w >= I.GALE].sum())
        bands["damaging_89"] += float(seg[w >= I.DAMAGING].sum())
        bands["destructive_118"] += float(seg[w >= I.DESTRUCTIVE].sum())
        flooded_km += float(seg[d >= 0.5].sum())
    return {"total_km": round(total_km, 1), **{k: round(v, 1) for k, v in bands.items()}, "flooded_km": round(flooded_km, 1)}


def _routes(ctx: Context, hz: Hazard, assets: list[dict]) -> dict:
    if ctx.graph is None or ctx.node_info is None:
        return {"routes": [], "summary": {"note": "no road network for this tenant"}}
    ni = ctx.node_info
    nd = np.nan_to_num(ctx.dem.sample(hz.depth_grid, ni["lat"], ni["lon"], 0.0), nan=0.0) if hz.depth_grid is not None else np.zeros(len(ni["lat"]))
    r24 = hz.r24[ni["gidx"]]
    pl_likely = ni["basin"] & (r24 >= I.IMD_VERY_HEAVY)      # ponding blocks roads; streams are crossed by bridges
    blocked = (nd >= I.PASSABLE_DEPTH_M) | pl_likely
    usable_ids = {a["id"] for a in assets if a["kind"] == "shelter" and a.get("usable")}
    shelters = [s for s in ctx.exposure.shelters if s.id in usable_ids]
    shelters.sort(key=lambda s: (not s.props.get("designated"), s.name))
    origins = sorted([p for p in ctx.exposure.places if p.name and p.name != "place"], key=_place_sort)[:30]
    routes = route_origins(ctx.graph, origins, shelters, blocked)
    pidx = {a.id: i for i, a in enumerate(ctx.probes["ref"][:ctx.probes["n_assets"]])}
    for r in routes:
        i = pidx.get(r["origin_id"])
        if i is None:
            continue
        gale = I.first_time(hz.wind[:, i], hz.hours, I.GALE)
        r["gale_onset_h"] = gale
        if r["status"] == "route" and gale is not None:
            r["depart_by_h"] = round(gale - r["minutes"] / 60.0 - 1.0, 1)      # 1 h safety buffer
    n_route = sum(1 for r in routes if r["status"] == "route")
    stranded = [r["origin"] for r in routes if r["status"] in ("no_route", "origin_flooded")]
    return {"routes": routes, "summary": {"origins": len(routes), "routed": n_route, "stranded": stranded,
                                          "blocked_nodes": int(blocked.sum()), "safe_shelters": len(shelters)}}


def _ensemble(ctx: Context, storm: Storm, tide_m: float) -> tuple[np.ndarray, list[dict]]:
    """9-member what-if ensemble: k/9 = share of members in which an asset is hit."""
    P = ctx.probes
    hits = np.zeros(len(P["lat"]), dtype=int)
    members = []
    sector_series: dict[str, list[float]] = {s["cfg"].id: [] for s in ctx.sectors}
    for shift in ENSEMBLE_SHIFTS_KM:
        for dkt in ENSEMBLE_DKT:
            st = scenario_storm(storm, cross_track_km=shift, delta_kt=dkt)
            hz = compute_hazard(ctx, st, tide_m)
            w = hz.wind.max(axis=0) if hz.wind.size else np.array([])
            g = P["gidx"]
            r24 = hz.r24[g] if len(g) else np.array([])
            hit = (w >= I.DAMAGING) | (hz.probe_depth > 0) | (r24 >= I.IMD_VERY_HEAVY)
            hits += hit.astype(int)
            for s in hz.sector_peak:
                sector_series[s["id"]].append(s["surge_m"])
            members.append({"shift_km": shift, "delta_kt": dkt, "peak_focus_kmh": hz.focus["peak_wind_kmh"],
                            "flooded_km2": round(hz.flooded_km2, 1)})
    return hits, [{"id": k, "surge_min_m": round(min(v), 2), "surge_max_m": round(max(v), 2)} for k, v in sector_series.items()], members


_SIMS: "OrderedDict[str, dict]" = OrderedDict()
_PNG: dict[str, bytes] = {}
_DEPTH: dict[str, np.ndarray | None] = {}


def _sim_key(tenant_id, storm_id, shift, dkt, tide) -> str:
    return hashlib.sha1(f"{tenant_id}|{storm_id}|{shift}|{dkt}|{tide}".encode()).hexdigest()[:12]


def _official_surge(base: Storm) -> dict | None:
    """Surge guidance quoted in an official bulletin (read by Gemini). Shown next to our screening-level numbers and given to advisories."""
    ref = base.reference or {}
    if base.kind == "bulletin" and (ref.get("surge_text") or ref.get("surge_high_m") is not None):
        return {"text": ref.get("surge_text"), "low_m": ref.get("surge_low_m"), "high_m": ref.get("surge_high_m"),
                "source": base.source, "note": "Official guidance overrides our screening-level estimate wherever they differ."}
    return None


_SIM_LOCK = threading.RLock()


def simulate(*args, **kwargs) -> dict:
    """Thread-safe entry point (requests run in a thread pool; the cache and hazard arrays are shared)."""
    with _SIM_LOCK:
        return _simulate(*args, **kwargs)


def _simulate(tenant_id: str, storm: Storm | str, *, cross_track_km: float = 0.0, delta_kt: float = 0.0,
              tide_m: float | None = None, ensemble: bool = True) -> dict:
    ctx = get_context(tenant_id)
    base = load_replay(storm) if isinstance(storm, str) else storm
    tide = ctx.tenant.tide_default_m if tide_m is None else tide_m
    key = _sim_key(tenant_id, base.id, cross_track_km, delta_kt, tide) + ("e" if ensemble else "n")
    if key in _SIMS:
        _SIMS.move_to_end(key)
        return _SIMS[key]
    st = scenario_storm(base, cross_track_km=cross_track_km, delta_kt=delta_kt)
    hz = compute_hazard(ctx, st, tide)
    hits, sec_ranges, members = (None, [], [])
    if ensemble:
        hits, sec_ranges, members = _ensemble(ctx, st, tide)
    assets = _assess_assets(ctx, hz, hits)
    road_rows, road_geo = _roads(ctx, hz)
    lines = _lines_summary(ctx, hz)
    rt = _routes(ctx, hz, assets)
    by_kind: dict[str, dict] = {}
    for a in assets:
        k = by_kind.setdefault(a["kind"], {"total": 0, "ok": 0, "watch": 0, "at_risk": 0, "critical": 0})
        k["total"] += 1
        k[a["status"]] += 1
    ex = ctx.exposure
    sea_ranges = {r["id"]: r for r in sec_ranges}
    for s in hz.sector_peak:
        s.update({k: v for k, v in sea_ranges.get(s["id"], {}).items() if k != "id"})
    n_sh = sum(1 for a in assets if a["kind"] == "shelter")
    result = {
        "sim_id": key,
        "tenant": {"id": ctx.tenant.id, "name": ctx.tenant.name, "focus": ctx.tenant.focus.model_dump(), "bbox": ctx.tenant.bbox},
        "storm": {"id": base.id, "name": base.name, "basin": base.basin, "season": base.season, "source": base.source,
                  "authority": base.authority, "wind_avg_period_min": base.wind_avg_period_min, "kind": st.kind,
                  "summary": base.summary, "peak_kt": st.peak_kt(), "reference": base.reference,
                  "track": [{"t": f.t.isoformat(), "lat": f.lat, "lon": f.lon, "vmax_kt": f.vmax_kt, "mslp_hpa": f.mslp_hpa} for f in st.track]},
        "scenario": {"cross_track_km": cross_track_km, "delta_kt": delta_kt, "tide_m": tide, "ensemble": ensemble},
        "official_surge": _official_surge(base),
        "t0": hz.t0.isoformat(), "closest_approach_km": round(hz.dmin_km, 1),
        "focus": hz.focus, "timeline": hz.center, "sectors": hz.sector_peak,
        "flooded_km2": round(hz.flooded_km2, 1),
        "assets": assets, "roads": road_rows, "roads_geojson": {"type": "FeatureCollection", "features": road_geo["features"]},
        "road_summary": {k: v for k, v in road_geo.items() if k != "features"},
        "power_lines": lines, "evacuation": rt, "ensemble_members": members,
        "summary": {"by_kind": by_kind, "arterial_km_affected": road_geo["arterial_km_affected"],
                    "arterial_km_total": road_geo["arterial_km_total"],
                    "shelters_usable": sum(1 for a in assets if a["kind"] == "shelter" and a.get("usable")), "shelters_total": n_sh,
                    "designated_shelters": ex.source_counts.get("designated_shelters", 0)},
        "exposure_counts": ex.source_counts,
        "layers": {"bounds": ctx.dem.corner_bounds(), "inundation": f"/api/layers/{key}/inundation.png",
                   "pathways": f"/api/layers/{tenant_id}/pathways.png"},
    }
    _SIMS[key] = result
    _DEPTH[key] = hz.depth_grid
    if hz.depth_grid is not None:
        _PNG[key] = INU.depth_png(hz.depth_grid)
    else:
        _PNG[key] = INU.depth_png(np.full(ctx.dem.shape, np.nan, dtype=np.float32))
    while len(_SIMS) > 24:
        old, _ = _SIMS.popitem(last=False)
        _PNG.pop(old, None)
        _DEPTH.pop(old, None)
    return result


def depth_grid_for(sim_id: str):
    return _DEPTH.get(sim_id)


def get_sim(sim_id: str) -> dict | None:
    return _SIMS.get(sim_id)


def inundation_png(sim_id: str) -> bytes | None:
    return _PNG.get(sim_id)


_PATHWAY_PNG: dict[str, bytes] = {}


def pathways_png(tenant_id: str) -> bytes:
    if tenant_id not in _PATHWAY_PNG:
        ctx = get_context(tenant_id)
        _PATHWAY_PNG[tenant_id] = PLU.pathway_png(ctx.hydro)
    return _PATHWAY_PNG[tenant_id]
