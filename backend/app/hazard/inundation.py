"""Sea-connected, distance-attenuated inundation ("connected bathtub") on a DEM.

For every cell:  effective_level = storm_tide(nearest sector) - ATTENUATION_M_PER_KM * distance_from_sea
A cell floods when elevation < effective_level AND it is hydraulically connected to the sea through
other flooded cells (a plain bathtub also floods inland depressions the sea cannot reach). Depth =
effective_level - elevation, reported in classes because DEM vertical error dominates surge error.

Limits (also shown in the product): screening-level; surface-model DEM biased high in built-up/vegetated
areas (under-predicts); no wave run-up, friction, duration or drainage; inland decay 0.2 m/km follows
Pielke & Pielke (1997) as used by CLIMADA's TCSurgeBathtub, which also caps reach at 50 km.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

from .dem import Dem

ATTENUATION_M_PER_KM = 0.2
MAX_INLAND_KM = 50.0
MIN_SEA_KM2 = 2.0

CLASS_EDGES = (0.0, 0.5, 1.5)          # m: <0.5 shallow, 0.5-1.5 moderate, >1.5 deep
CLASS_LABELS = ("shallow (<0.5 m)", "moderate (0.5-1.5 m)", "deep (>1.5 m)")
CLASS_RGB = ((147, 197, 253), (37, 99, 235), (107, 33, 168))


def sea_mask(dem: Dem) -> np.ndarray:
    """Large connected water body at or below 0 m (the open sea and connected lagoons)."""
    low = dem.elev <= 0.0
    labels, n = ndi.label(low)
    if n == 0:
        return np.zeros_like(low)
    sizes = ndi.sum(low, labels, index=np.arange(1, n + 1))
    min_cells = MIN_SEA_KM2 * 1e6 / (dem.cell_m ** 2)
    keep = np.where(sizes >= min_cells)[0] + 1
    sea = np.isin(labels, keep)
    # Harbours/creeks whose entrance is narrower than one DEM cell show up as separate small water
    # bodies. Merge any sub-zero water within ~200 m of the sea; it is the same water.
    grow = int(max(2, round(200.0 / dem.cell_m)))
    near_sea = ndi.binary_dilation(sea, iterations=grow)
    merge = np.unique(labels[near_sea & low & (labels > 0)])
    return np.isin(labels, merge)


def distance_from_sea_km(dem: Dem, sea: np.ndarray) -> np.ndarray:
    return ndi.distance_transform_edt(~sea) * dem.cell_m / 1000.0


def onshore_unit(dem: Dem, sea: np.ndarray, lat: float, lon: float) -> tuple[float, float]:
    """Inland-pointing unit vector (east, north) at a coast point, from the gradient of distance-to-sea."""
    dist = ndi.gaussian_filter(distance_from_sea_km(dem, sea), 3)
    r, c = dem.rc(np.array([lat]), np.array([lon]))
    ri, ci = int(round(float(r[0]))), int(round(float(c[0])))
    h, w = dist.shape
    ri, ci = min(max(ri, 2), h - 3), min(max(ci, 2), w - 3)
    d_row = (dist[ri + 2, ci] - dist[ri - 2, ci]) / 4.0     # +row = south
    d_col = (dist[ri, ci + 2] - dist[ri, ci - 2]) / 4.0     # +col = east
    east, north = d_col, -d_row
    norm = float(np.hypot(east, north))
    if norm < 1e-9:
        return 0.0, 1.0
    return east / norm, north / norm


def flood_depth(dem: Dem, levels: dict[str, float], sectors: dict[str, tuple[float, float]],
                sea: np.ndarray | None = None) -> dict:
    """Depth grid (m, NaN where dry) for per-sector storm-tide levels (m above MSL)."""
    sea = sea_mask(dem) if sea is None else sea
    dist_km = distance_from_sea_km(dem, sea)
    ids = list(levels)
    lat, lon = dem.latlon_grid()
    # nearest sector for every cell (sector positions -> pixel space, cheap KD-tree on a decimated grid)
    sec_px = np.array([[float(v[0]) for v in dem.rc(np.array([sectors[i][0]]), np.array([sectors[i][1]]))] for i in ids])
    tree = cKDTree(sec_px)
    rr, cc = np.mgrid[0:dem.shape[0]:4, 0:dem.shape[1]:4]
    _, near_small = tree.query(np.c_[rr.ravel(), cc.ravel()])
    near_small = near_small.reshape(rr.shape)
    near = np.kron(near_small, np.ones((4, 4), dtype=int))[:dem.shape[0], :dem.shape[1]]
    lvl_arr = np.array([levels[i] for i in ids])[near]
    eff = lvl_arr - ATTENUATION_M_PER_KM * dist_km
    # cells at/below ~0 m are water bodies (sea, harbours, lagoons): a "depth" there is meaningless
    candidate = (dem.elev < eff) & ~sea & (dem.elev > 0.0) & (dist_km <= MAX_INLAND_KM)
    labels, _ = ndi.label(candidate | sea, structure=np.ones((3, 3)))
    sea_labels = np.unique(labels[sea & (labels > 0)])
    connected = np.isin(labels, sea_labels) & candidate
    depth = np.where(connected, eff - dem.elev, np.nan).astype(np.float32)
    return {"depth": depth, "sea": sea, "dist_km": dist_km, "flooded_km2": float(connected.sum() * (dem.cell_m / 1000.0) ** 2)}


def depth_class(depth_m: np.ndarray) -> np.ndarray:
    """0 = dry, 1..3 = shallow/moderate/deep."""
    d = np.asarray(depth_m, dtype=float)
    cls = np.zeros(d.shape, dtype=np.int8)
    wet = np.isfinite(d) & (d > 0)
    cls[wet] = 1
    cls[wet & (d >= CLASS_EDGES[1])] = 2
    cls[wet & (d >= CLASS_EDGES[2])] = 3
    return cls


def depth_png(depth: np.ndarray, alpha: int = 170) -> bytes:
    cls = depth_class(depth)
    rgba = np.zeros(depth.shape + (4,), dtype=np.uint8)
    for k, rgb in enumerate(CLASS_RGB, start=1):
        m = cls == k
        rgba[m, :3] = rgb
        rgba[m, 3] = alpha
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
