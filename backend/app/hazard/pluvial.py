"""Rain "damage pathways" from terrain: waterlogging basins and concentrated-runoff corridors.

  1. Priority-flood depression filling (Barnes et al. 2014) with an epsilon gradient so flats drain.
     fill_depth = filled - original is how deep a closed depression can pond before it spills.
  2. D8 flow direction on the filled surface and flow accumulation -> upstream area (km2).
  3. Rain (R-CLIPER prior or NWP) decides WHEN these pathways activate at each asset.

This is a terrain-based screening tool: it ignores drainage infrastructure (storm drains, pumps),
land-use imperviousness and tide-locking of outfalls, so it is a "where would water collect/flow"
indicator, not a hydraulic forecast. Earth Engine's MERIT Hydro `hnd`/`upa` bands are the alternative
source when EE is authenticated (see gee.py).
"""
from __future__ import annotations

import heapq
from pathlib import Path

import numpy as np

from ..config import DATA_DIR, Tenant
from .dem import Dem
from .inundation import sea_mask

EPS = 1e-4
_N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

# IMD 24-h rainfall classes (mm/day). Lower bound of each class; verify against IMD's glossary.
IMD_HEAVY, IMD_VERY_HEAVY, IMD_EXTREME = 64.5, 115.6, 204.5


def _priority_flood(elev: np.ndarray, outlet: np.ndarray) -> np.ndarray:
    h, w = elev.shape
    flat = elev.astype(np.float64).ravel().tolist()
    out_flat = outlet.ravel()
    visited = bytearray(h * w)
    heap: list[tuple[float, int]] = []
    # seeds: sea cells (outlets) that touch land, and all AOI boundary cells
    for r in range(h):
        for c in (0, w - 1):
            i = r * w + c
            if not visited[i]:
                visited[i] = 1
                heapq.heappush(heap, (flat[i], i))
    for c in range(w):
        for r in (0, h - 1):
            i = r * w + c
            if not visited[i]:
                visited[i] = 1
                heapq.heappush(heap, (flat[i], i))
    sea_idx = np.flatnonzero(out_flat)
    for i in sea_idx.tolist():
        if not visited[i]:
            visited[i] = 1
            heapq.heappush(heap, (flat[i], i))
    push, pop = heapq.heappush, heapq.heappop
    while heap:
        z, i = pop(heap)
        r, c = divmod(i, w)
        for dr, dc in _N8:
            rr, cc = r + dr, c + dc
            if 0 <= rr < h and 0 <= cc < w:
                j = rr * w + cc
                if not visited[j]:
                    visited[j] = 1
                    zj = flat[j]
                    nz = zj if zj > z + EPS else z + EPS
                    flat[j] = nz
                    push(heap, (nz, j))
    return np.asarray(flat, dtype=np.float64).reshape(h, w)


def _flow_direction(filled: np.ndarray, cell_m: float) -> np.ndarray:
    """Index (flat) of the steepest-descent D8 neighbour; -1 for outlets."""
    h, w = filled.shape
    pad = np.pad(filled, 1, mode="edge")
    best_drop = np.full((h, w), 0.0)
    best_k = np.full((h, w), -1, dtype=np.int8)
    for k, (dr, dc) in enumerate(_N8):
        nb = pad[1 + dr:1 + dr + h, 1 + dc:1 + dc + w]
        dist = cell_m * (1.41421356 if dr and dc else 1.0)
        drop = (filled - nb) / dist
        better = drop > best_drop
        best_drop = np.where(better, drop, best_drop)
        best_k = np.where(better, k, best_k)
    rr, cc = np.mgrid[0:h, 0:w]
    dr_arr = np.array([d[0] for d in _N8])
    dc_arr = np.array([d[1] for d in _N8])
    k = np.where(best_k >= 0, best_k, 0)
    nr, nc = rr + dr_arr[k], cc + dc_arr[k]
    down = nr * w + nc
    down[(best_k < 0) | (nr < 0) | (nr >= h) | (nc < 0) | (nc >= w)] = -1
    return down.astype(np.int64)


def analyse(dem: Dem) -> dict[str, np.ndarray]:
    sea = sea_mask(dem)
    elev = np.where(sea, np.minimum(dem.elev, 0.0), dem.elev)
    filled = _priority_flood(elev, sea)
    fill_depth = np.where(sea, 0.0, filled - elev).astype(np.float32)
    down = _flow_direction(filled, dem.cell_m)
    order = np.argsort(-filled.ravel(), kind="stable").tolist()
    acc = np.where(sea.ravel(), 0.0, 1.0).tolist()
    down_l = down.ravel().tolist()
    sea_l = sea.ravel().tolist()
    for i in order:
        d = down_l[i]
        if d >= 0 and not sea_l[i]:
            acc[d] += acc[i]
    upa_km2 = (np.asarray(acc, dtype=np.float32).reshape(dem.shape) * (dem.cell_m / 1000.0) ** 2)
    return {"fill_depth": fill_depth, "upa_km2": upa_km2, "sea": sea}


def basin_mask(fill: np.ndarray, sea: np.ndarray, lo: float = 0.5, hi: float = 3.0,
               artifact_m: float = 10.0, min_cells: int = 20) -> np.ndarray:
    """Plausible waterlogging basins: shallow closed depressions of a few cells or more.

    Very deep fills (reservoirs, quarries, SRTM voids) and single-cell 1 m quantisation noise are dropped.
    """
    from scipy import ndimage as ndi
    cand = (fill >= lo) & ~sea
    lab, n = ndi.label(cand)
    if n == 0:
        return cand
    idx = np.arange(1, n + 1)
    sizes = ndi.sum(cand, lab, idx)
    maxfill = ndi.maximum(fill, lab, idx)
    keep = idx[(sizes >= min_cells) & (maxfill <= artifact_m)]
    return np.isin(lab, keep) & (fill <= hi)


def _cache(tenant: Tenant) -> Path:
    return DATA_DIR / "dem" / f"{tenant.id}_hydro.npz"


_MEM: dict[str, dict[str, np.ndarray]] = {}


def load_hydro(tenant: Tenant, dem: Dem, allow_compute: bool = True) -> dict[str, np.ndarray]:
    if tenant.id in _MEM:
        return _MEM[tenant.id]
    p = _cache(tenant)
    if p.exists():
        d = np.load(p)
        res = {"fill_depth": d["fill_depth"].astype(np.float32), "upa_km2": d["upa_km2"].astype(np.float32),
               "sea": d["sea"].astype(bool)}
    elif allow_compute:
        res = analyse(dem)
        np.savez_compressed(p, fill_depth=res["fill_depth"].astype(np.float16),
                            upa_km2=res["upa_km2"].astype(np.float16), sea=res["sea"])
    else:
        raise FileNotFoundError(f"hydro cache missing for {tenant.id}")
    land_elev = dem.elev[~res["sea"]]
    flat = bool(land_elev.size) and float(np.median(land_elev)) < 15.0
    # In low-relief deltas the DEM's own vertical noise (metres) exceeds shallow depressions, so only deeper,
    # larger closed depressions are treated as waterlogging basins there.
    res["basin"] = basin_mask(res["fill_depth"], res["sea"], lo=1.5 if flat else 0.5, min_cells=60 if flat else 20)
    res["basin_rule"] = "flat-terrain rule (>=1.5 m, >=60 cells)" if flat else "standard rule (>=0.5 m, >=20 cells)"
    _MEM[tenant.id] = res
    return res


def pathway_png(hydro: dict[str, np.ndarray], corridor_km2: float = 0.5, basin_m: float = 0.3) -> bytes:
    """Overlay: orange = concentrated-runoff corridors, purple = waterlogging basins."""
    import io
    from PIL import Image
    upa, sea = hydro["upa_km2"], hydro["sea"]
    rgba = np.zeros(upa.shape + (4,), dtype=np.uint8)
    corridor = (upa >= corridor_km2) & ~sea
    basin = hydro["basin"]
    rgba[corridor] = (249, 115, 22, 200)
    rgba[basin] = (168, 85, 247, 190)
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def classify_rain_24h(mm: float) -> str:
    if mm >= IMD_EXTREME:
        return "extremely heavy"
    if mm >= IMD_VERY_HEAVY:
        return "very heavy"
    if mm >= IMD_HEAVY:
        return "heavy"
    return "below heavy"
