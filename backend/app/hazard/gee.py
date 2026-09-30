"""Google Earth Engine integration: live meteorology, satellite-derived exposure and map tiles.

What it adds on top of the local (open-terrain) engine:
  * live_rain      NOAA GFS forecast rainfall for the tenant (dataset NOAA/GFS0P25, latest model run) - real-time meteorology
  * flood_exposure people (JRC GHSL P2023A population) and buildings (Google Open Buildings v3) inside the MODELLED flood zone
  * tile_layers    Earth Engine map tiles: GFS forecast rain, MERIT Hydro HAND, population density

Authentication: Application Default Credentials (Cloud Run service account) or `earthengine authenticate` locally. The Google Cloud
project must be registered for Earth Engine. Everything here fails soft: `status()` says why Earth Engine is unavailable and the rest
of the product keeps working on the open Terrarium terrain tiles.

Asset IDs used (all checked in the Earth Engine catalog on 2026-09-29): NOAA/GFS0P25, JRC/GHSL/P2023A/GHS_POP,
GOOGLE/Research/open-buildings/v3/polygons, MERIT/Hydro/v1_0_1. Note the deprecated IDs we deliberately avoid:
COPERNICUS/DEM/GLO30 (use GLO30_2024_1), FAO/GAUL/2015/level2 (use GAUL/2025), NASA/SMAP/SPL4SMGP/007 (use /008).
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

import numpy as np

from ..config import Tenant, settings

try:
    import ee
except Exception:  # noqa: BLE001
    ee = None

_LOCK = threading.Lock()
_STATE: dict[str, Any] = {"initialized": False, "error": None, "project": None, "tried": False}
_CACHE: dict[str, tuple[float, Any]] = {}
TTL_S = 900


def _init() -> bool:
    with _LOCK:
        if _STATE["initialized"]:
            return True
        if _STATE["tried"] and _STATE["error"] and time.time() - _STATE.get("t", 0) < 120:
            return False
        _STATE.update(tried=True, t=time.time())
        s = settings()
        if ee is None:
            _STATE["error"] = "earthengine-api is not installed"
            return False
        if not s.ee_enabled:
            _STATE["error"] = "EE_ENABLED=false"
            return False
        try:
            project = s.gcp_project
            if not os.getenv("K_SERVICE"):
                # not on Cloud Run: skip the (slow) GCE metadata-server probe when looking for default credentials
                os.environ.setdefault("NO_GCE_CHECK", "true")
            try:
                import google.auth
                creds, adc_project = google.auth.default(scopes=["https://www.googleapis.com/auth/earthengine",
                                                                 "https://www.googleapis.com/auth/cloud-platform"])
                project = project or adc_project
                ee.Initialize(credentials=creds, project=project)
            except Exception:  # noqa: BLE001 - fall back to credentials stored by `earthengine authenticate`
                ee.Initialize(project=project)
            ee.Number(1).getInfo()               # forces a real round-trip so failures surface here
            _STATE.update(initialized=True, error=None, project=project)
            return True
        except Exception as exc:  # noqa: BLE001
            _STATE["error"] = str(exc)[:300]
            return False


_THREAD: dict[str, Any] = {"t": None}


def warm() -> None:
    """Initialise Earth Engine in the background so /api/health never blocks on it."""
    if _THREAD["t"] is None and not _STATE["initialized"]:
        _THREAD["t"] = threading.Thread(target=_init, daemon=True)
        _THREAD["t"].start()


def status(wait: bool = False) -> dict:
    if wait:
        ok = _init()
    else:
        warm()
        ok = _STATE["initialized"]
        if not ok and not _STATE["error"]:
            return {"available": False, "project": None, "error": None, "initializing": True,
                    "note": "Earth Engine is initialising..."}
    return {"available": ok, "project": _STATE["project"], "error": None if ok else _STATE["error"],
            "note": None if ok else "Earth Engine is not connected: the app uses open Terrarium terrain tiles and skips EE-only layers. "
                                    "Register a Cloud project for Earth Engine and authenticate (see README)."}


def _cached(key: str, fn):
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < TTL_S:
        return hit[1]
    val = fn()
    _CACHE[key] = (time.time(), val)
    return val


def _rect(t: Tenant):
    s, w, n, e = t.bbox
    return ee.Geometry.Rectangle([w, s, e, n])


def live_rain(t: Tenant) -> dict:
    """Latest NOAA GFS run: accumulated forecast rain (mm) over the next 24/72 h at the focus point and the max in the study area."""
    def compute():
        coll = ee.ImageCollection("NOAA/GFS0P25")
        latest = ee.Number(coll.aggregate_max("creation_time"))
        run = coll.filter(ee.Filter.eq("creation_time", latest)).filter(ee.Filter.inList("forecast_hours", [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72]))
        # total_precipitation_surface is a 1-6 h bucket depending on the forecast hour: sum the 6-hourly buckets, never every step.
        def total(hours):
            return run.filter(ee.Filter.lte("forecast_hours", hours)).select("total_precipitation_surface").sum()
        pt = ee.Geometry.Point([t.focus.lon, t.focus.lat])
        out = {}
        for h in (24, 72):
            img = total(h)
            out[f"focus_{h}h_mm"] = img.reduceRegion(ee.Reducer.mean(), pt.buffer(15000), 25000).get("total_precipitation_surface")
            out[f"max_{h}h_mm"] = img.reduceRegion(ee.Reducer.max(), _rect(t), 25000).get("total_precipitation_surface")
        res = ee.Dictionary(out).set("run_ms", latest).getInfo()
        return {"source": "NOAA GFS 0.25 deg via Earth Engine (NOAA/GFS0P25)", "run_utc_ms": res.get("run_ms"),
                **{k: (round(v, 1) if isinstance(v, (int, float)) else None) for k, v in res.items() if k != "run_ms"},
                "note": "Real-time NWP forecast; a coarse 0.25 deg model - it does not resolve the cyclone core, so use it as context, not as a track-aware forecast."}
    if not _init():
        raise RuntimeError(_STATE["error"] or "Earth Engine unavailable")
    return _cached(f"rain:{t.id}", compute)


def _flood_geometry(dem, depth: np.ndarray, cell_deg_m: float = 250.0):
    """Coarsen the modelled flood mask to ~250 m squares and return an ee.Geometry MultiPolygon (small payload)."""
    step = max(1, int(round(cell_deg_m / dem.cell_m)))
    h, w = depth.shape
    wet = np.isfinite(depth) & (depth > 0)
    rects = []
    for r0 in range(0, h, step):
        for c0 in range(0, w, step):
            blk = wet[r0:r0 + step, c0:c0 + step]
            if blk.size and blk.mean() >= 0.25:
                rects.append((r0, c0))
    if not rects:
        return None, 0
    from .dem import px_to_lonlat
    polys = []
    for r0, c0 in rects[:4000]:
        lon0, lat0 = px_to_lonlat(dem.px0 + c0, dem.py0 + r0, dem.z)
        lon1, lat1 = px_to_lonlat(dem.px0 + c0 + step, dem.py0 + r0 + step, dem.z)
        polys.append([[float(lon0), float(lat0)], [float(lon1), float(lat0)], [float(lon1), float(lat1)], [float(lon0), float(lat1)], [float(lon0), float(lat0)]])
    return ee.Geometry.MultiPolygon([[p] for p in polys], geodesic=False), len(polys)


def flood_exposure(t: Tenant, dem, depth: np.ndarray, sim_id: str) -> dict:
    """People and buildings inside the modelled surge-flood zone, from Earth Engine (GHSL population, Open Buildings)."""
    def compute():
        geom, n = _flood_geometry(dem, depth)
        if geom is None:
            return {"people": 0, "buildings": 0, "zone_squares": 0, "note": "No flooded area in this scenario."}
        pop = ee.ImageCollection("JRC/GHSL/P2023A/GHS_POP").filterDate("2025-01-01", "2026-01-01").first()
        people = pop.reduceRegion(ee.Reducer.sum(), geom, 100, maxPixels=1e9).values().get(0)
        bld = (ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons").filterBounds(geom)
               .filter(ee.Filter.gte("confidence", 0.7)).size())
        res = ee.Dictionary({"people": people, "buildings": bld}).getInfo()
        return {"people": int(round(res["people"])) if res.get("people") is not None else None, "buildings": res.get("buildings"),
                "zone_squares": n, "source": "JRC GHSL P2023A population (100 m, 2025) and Google Open Buildings v3 (confidence >= 0.7), inside the MODELLED flood zone (250 m squares, >=25% wet)",
                "note": "GHSL is a modelled population grid and Open Buildings is ML-derived: read as order-of-magnitude exposure, not a census."}
    if not _init():
        raise RuntimeError(_STATE["error"] or "Earth Engine unavailable")
    return _cached(f"exp:{sim_id}", compute)


def tile_layers(t: Tenant) -> dict:
    """Earth Engine map tiles for the Leaflet map (getMapId). Tokens expire: the UI re-requests on error."""
    def compute():
        coll = ee.ImageCollection("NOAA/GFS0P25")
        latest = ee.Number(coll.aggregate_max("creation_time"))
        run = coll.filter(ee.Filter.eq("creation_time", latest)).filter(ee.Filter.inList("forecast_hours", [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72]))
        rain72 = run.select("total_precipitation_surface").sum()
        hand = ee.Image("MERIT/Hydro/v1_0_1").select("hnd")
        pop = ee.ImageCollection("JRC/GHSL/P2023A/GHS_POP").filterDate("2025-01-01", "2026-01-01").first()
        def mid(img, vis):
            return img.getMapId(vis)["tile_fetcher"].url_format
        return {
            "gfs_rain_72h": {"label": "GFS forecast rain, next 72 h (mm)", "url": mid(rain72, {"min": 0, "max": 250, "palette": ["#ffffff00", "#93c5fd", "#2563eb", "#7c3aed", "#be123c"]}),
                             "attribution": "NOAA GFS via Google Earth Engine"},
            "hand": {"label": "Height above nearest drainage < 10 m (MERIT Hydro)", "url": mid(hand.updateMask(hand.lt(10)), {"min": 0, "max": 10, "palette": ["#7c3aed", "#3b82f6", "#bae6fd"]}),
                     "attribution": "MERIT Hydro (Yamazaki et al.) via Earth Engine"},
            "population": {"label": "Population density (GHSL 2025)", "url": mid(pop.updateMask(pop.gt(0)), {"min": 0, "max": 300, "palette": ["#fef3c7", "#f59e0b", "#b91c1c"]}),
                           "attribution": "JRC GHSL P2023A via Earth Engine"},
        }
    if not _init():
        raise RuntimeError(_STATE["error"] or "Earth Engine unavailable")
    return _cached(f"tiles:{t.id}", compute)
