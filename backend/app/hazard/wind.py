"""Parametric tropical-cyclone wind field (Holland 1980) evaluated at arbitrary points.

Method
  p(r)  = pc + dp * exp(-(Rm/r)^B)
  Vg(r) = sqrt( (B*dp/rho) * (Rm/r)^B * exp(-(Rm/r)^B) + (r*f/2)^2 ) - r*f/2
  B     = rho * e * Vg_max^2 / dp, clamped to [1.0, 2.5]
Surface wind = SURFACE_FACTOR * Vg (standard gradient-to-surface reduction), rotated inward by
INFLOW_DEG, plus ALPHA * storm translation vector (right-of-track asymmetry).

Assumptions that are NOT from the best track (and shown in the UI methodology panel):
  SURFACE_FACTOR = 0.85, INFLOW_DEG = 20, ALPHA = 0.5, default RMW by intensity.
Wind speeds are on the storm's own averaging basis (JTWC = 1-minute sustained).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..storms.model import KT_TO_MS, NM_TO_KM, Fix
from ..storms.track import EARTH_R_KM

RHO_A = 1.15          # kg m-3
SURFACE_FACTOR = 0.85
INFLOW_DEG = 20.0
ALPHA = 0.5
P_ENV_DEFAULT = 1010.0
OMEGA = 7.2921e-5


@dataclass(frozen=True)
class HollandParams:
    lat: float
    lon: float
    pc_hpa: float
    penv_hpa: float
    vmax_ms: float          # surface (as reported)
    rmw_km: float
    b: float

    @property
    def dp_hpa(self) -> float:
        return self.penv_hpa - self.pc_hpa


def default_rmw_km(vmax_kt: float) -> float:
    """Typical North Indian Ocean radius of maximum wind when the best track has none."""
    if vmax_kt >= 96:
        return 25.0
    if vmax_kt >= 64:
        return 30.0
    if vmax_kt >= 34:
        return 45.0
    return 60.0


def dp_from_vmax_hpa(vmax_kt: float) -> float:
    """Atkinson-Holland (1977): Vmax[kt] = 6.7 * dp^0.644 -> dp[hPa]."""
    return (max(vmax_kt, 15.0) / 6.7) ** (1 / 0.644)


def holland_params(fix: Fix) -> HollandParams:
    vmax_kt = max(fix.vmax_kt or 30.0, 20.0)
    penv = fix.poci_hpa or P_ENV_DEFAULT
    pc = fix.mslp_hpa if fix.mslp_hpa else penv - dp_from_vmax_hpa(vmax_kt)
    dp = max(penv - pc, 3.0)
    vmax_ms = vmax_kt * KT_TO_MS
    vg_max = vmax_ms / SURFACE_FACTOR
    b = RHO_A * math.e * vg_max ** 2 / (dp * 100.0)
    b = min(max(b, 1.0), 2.5)
    rmw = (fix.rmw_nm * NM_TO_KM) if fix.rmw_nm else default_rmw_km(vmax_kt)
    return HollandParams(fix.lat, fix.lon, pc, penv, vmax_ms, max(rmw, 8.0), b)


def _offsets_km(p_lat: float, p_lon: float, lats: np.ndarray, lons: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """East/north offsets (km) of points relative to the storm centre."""
    north = (lats - p_lat) * 111.195
    east = (lons - p_lon) * 111.195 * np.cos(np.radians((lats + p_lat) / 2))
    return east, north


def pressure_hpa(params: HollandParams, r_km: np.ndarray) -> np.ndarray:
    r = np.maximum(r_km, 0.5)
    return params.pc_hpa + params.dp_hpa * np.exp(-((params.rmw_km / r) ** params.b))


def wind_field(params: HollandParams, lats, lons, motion_east_ms: float = 0.0,
               motion_north_ms: float = 0.0) -> dict[str, np.ndarray]:
    """10 m sustained wind at the given points. Returns speed (m/s) and the vector (u, v) the wind blows *toward*."""
    lats = np.atleast_1d(np.asarray(lats, dtype=float))
    lons = np.atleast_1d(np.asarray(lons, dtype=float))
    east, north = _offsets_km(params.lat, params.lon, lats, lons)
    r = np.maximum(np.hypot(east, north), 0.5)
    f = 2 * OMEGA * math.sin(math.radians(abs(params.lat)))
    rm_over_r = (params.rmw_km / r) ** params.b
    r_m = r * 1000.0
    vg = np.sqrt((params.b * params.dp_hpa * 100.0 / RHO_A) * rm_over_r * np.exp(-rm_over_r) + (r_m * f / 2) ** 2) - r_m * f / 2
    vsym = SURFACE_FACTOR * vg
    # cyclonic tangential direction (counter-clockwise in the NH), rotated inward by the inflow angle
    sgn = 1.0 if params.lat >= 0 else -1.0
    tx, ty = -north / r * sgn, east / r * sgn
    inflow = math.radians(INFLOW_DEG)
    ix, iy = -east / r, -north / r
    dx = math.cos(inflow) * tx + math.sin(inflow) * ix
    dy = math.cos(inflow) * ty + math.sin(inflow) * iy
    u = vsym * dx + ALPHA * motion_east_ms
    v = vsym * dy + ALPHA * motion_north_ms
    return {"speed": np.hypot(u, v), "u": u, "v": v, "r_km": r}


def wind_speed_kmh(speed_ms: np.ndarray) -> np.ndarray:
    return speed_ms * 3.6


def onshore_component(u: np.ndarray, v: np.ndarray, onshore_east: float, onshore_north: float) -> np.ndarray:
    """Component of the wind (blowing toward) along the inland-pointing unit vector, clipped at 0."""
    return np.maximum(u * onshore_east + v * onshore_north, 0.0)


def great_circle_r_km(lat1, lon1, lat2, lon2):  # small helper kept for tests
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))
