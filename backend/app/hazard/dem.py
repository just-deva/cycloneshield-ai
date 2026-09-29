"""Elevation grid for a tenant AOI from the open AWS/Mapzen "Terrarium" terrain tiles.

Terrarium tiles are keyless, global and include ocean bathymetry; over India the land heights derive
mainly from SRTM (a surface model: it is biased high over canopy and buildings, which UNDER-predicts
coastal flooding - stated in the product). The grid lives in Web-Mercator pixel space so it can be shown
in Leaflet with a plain ImageOverlay and sampled with simple arithmetic.

Attribution: Mapzen/AWS Terrain Tiles (https://registry.opendata.aws/terrain-tiles/), which credits SRTM,
GMTED, ETOPO1 and others. The Earth Engine path in gee.py uses NASADEM instead when authenticated.
"""
from __future__ import annotations

import io
import math
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ..config import DATA_DIR, Tenant

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
UA = "CycloneShieldAI/0.1 (hackathon prototype)"


def lonlat_to_px(lon, lat, z: int):
    n = 256.0 * (2 ** z)
    lat_r = np.radians(lat)
    px = (np.asarray(lon) + 180.0) / 360.0 * n
    py = (1.0 - np.arcsinh(np.tan(lat_r)) / math.pi) / 2.0 * n
    return px, py


def px_to_lonlat(px, py, z: int):
    n = 256.0 * (2 ** z)
    lon = np.asarray(px) / n * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * np.asarray(py) / n))))
    return lon, lat


@dataclass
class Dem:
    elev: np.ndarray        # float32 metres, ocean < 0
    z: int
    px0: int                # global pixel x/y of array[0, 0]
    py0: int
    cell_m: float           # approximate cell size at the AOI centre latitude

    @property
    def shape(self) -> tuple[int, int]:
        return self.elev.shape

    def rc(self, lat, lon):
        """Fractional (row, col) for lat/lon arrays."""
        px, py = lonlat_to_px(lon, lat, self.z)
        return py - self.py0, px - self.px0

    def sample(self, arr: np.ndarray, lat, lon, default=np.nan):
        r, c = self.rc(np.atleast_1d(lat), np.atleast_1d(lon))
        ri, ci = np.round(r).astype(int), np.round(c).astype(int)
        h, w = arr.shape
        ok = (ri >= 0) & (ri < h) & (ci >= 0) & (ci < w)
        out = np.full(ri.shape, default, dtype=float)
        out[ok] = arr[ri[ok], ci[ok]]
        return out

    def corner_bounds(self):
        """[[south, west], [north, east]] in lat/lon for Leaflet's ImageOverlay."""
        h, w = self.shape
        lon_w, lat_n = px_to_lonlat(self.px0, self.py0, self.z)
        lon_e, lat_s = px_to_lonlat(self.px0 + w, self.py0 + h, self.z)
        return [[float(lat_s), float(lon_w)], [float(lat_n), float(lon_e)]]

    def latlon_grid(self):
        h, w = self.shape
        cols = np.arange(w) + self.px0 + 0.5
        rows = np.arange(h) + self.py0 + 0.5
        lon, _ = px_to_lonlat(cols, np.full_like(cols, self.py0), self.z)
        _, lat = px_to_lonlat(np.full_like(rows, self.px0), rows, self.z)
        return lat, lon


def _fetch_tile(z: int, x: int, y: int) -> np.ndarray:
    req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        img = np.asarray(Image.open(io.BytesIO(resp.read())).convert("RGB"), dtype=np.float32)
    return img[..., 0] * 256.0 + img[..., 1] + img[..., 2] / 256.0 - 32768.0


def build_dem(bbox: list[float], z: int) -> Dem:
    s, w, n, e = bbox
    px_w, py_n = lonlat_to_px(w, n, z)
    px_e, py_s = lonlat_to_px(e, s, z)
    px0, py0 = int(math.floor(px_w)), int(math.floor(py_n))
    px1, py1 = int(math.ceil(px_e)), int(math.ceil(py_s))
    tx0, tx1 = px0 // 256, (px1 - 1) // 256
    ty0, ty1 = py0 // 256, (py1 - 1) // 256
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), dtype=np.float32)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = _fetch_tile(z, tx, ty)
    oy, ox = py0 - ty0 * 256, px0 - tx0 * 256
    elev = mosaic[oy:oy + (py1 - py0), ox:ox + (px1 - px0)]
    lat_c = (s + n) / 2
    cell_m = 40075016.686 * math.cos(math.radians(lat_c)) / (256.0 * 2 ** z)
    return Dem(elev=elev, z=z, px0=px0, py0=py0, cell_m=cell_m)


def _cache_path(tenant: Tenant) -> Path:
    return DATA_DIR / "dem" / f"{tenant.id}.npz"


_CACHE: dict[str, Dem] = {}


def load_dem(tenant: Tenant, allow_fetch: bool = True) -> Dem:
    if tenant.id in _CACHE:
        return _CACHE[tenant.id]
    path = _cache_path(tenant)
    if path.exists():
        d = np.load(path)
        dem = Dem(elev=d["elev"].astype(np.float32), z=int(d["z"]), px0=int(d["px0"]), py0=int(d["py0"]),
                  cell_m=float(d["cell_m"]))
    elif allow_fetch:
        dem = build_dem(tenant.bbox, tenant.dem_zoom)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, elev=dem.elev.astype(np.float16), z=dem.z, px0=dem.px0, py0=dem.py0, cell_m=dem.cell_m)
    else:
        raise FileNotFoundError(f"DEM cache missing for {tenant.id}")
    _CACHE[tenant.id] = dem
    return dem
