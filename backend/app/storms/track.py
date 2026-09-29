"""Track utilities: geometry, interpolation, closest approach and what-if scenarios."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np

from .model import KT_TO_MS, Fix, Storm

EARTH_R_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km; accepts scalars or numpy arrays."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(a))


def offset_km(lat: float, lon: float, east_km: float, north_km: float) -> tuple[float, float]:
    """Move a point by an east/north offset in km (small-distance approximation)."""
    dlat = north_km / 111.195
    dlon = east_km / (111.195 * max(math.cos(math.radians(lat)), 1e-6))
    return lat + dlat, lon + dlon


def _lerp(a: float | None, b: float | None, w: float) -> float | None:
    if a is None:
        return b
    if b is None:
        return a
    return a + (b - a) * w


def interpolate(storm: Storm, t: datetime) -> Fix:
    """Linear interpolation of the (observed + forecast) track; clamps outside the range."""
    track = storm.track
    if t <= track[0].t:
        return track[0]
    if t >= track[-1].t:
        return track[-1]
    for a, b in zip(track, track[1:]):
        if a.t <= t <= b.t:
            span = (b.t - a.t).total_seconds()
            w = 0.0 if span == 0 else (t - a.t).total_seconds() / span
            return Fix(
                t=t,
                lat=a.lat + (b.lat - a.lat) * w,
                lon=a.lon + (b.lon - a.lon) * w,
                vmax_kt=_lerp(a.vmax_kt, b.vmax_kt, w),
                mslp_hpa=_lerp(a.mslp_hpa, b.mslp_hpa, w),
                poci_hpa=_lerp(a.poci_hpa, b.poci_hpa, w),
                rmw_nm=_lerp(a.rmw_nm, b.rmw_nm, w),
            )
    return track[-1]


def motion_ms(storm: Storm, t: datetime, dt_hours: float = 3.0) -> tuple[float, float]:
    """Translation velocity (east, north) in m/s from the track around time t."""
    a = interpolate(storm, t - timedelta(hours=dt_hours / 2))
    b = interpolate(storm, t + timedelta(hours=dt_hours / 2))
    secs = dt_hours * 3600.0
    north = (b.lat - a.lat) * 111195.0 / secs
    east = (b.lon - a.lon) * 111195.0 * math.cos(math.radians((a.lat + b.lat) / 2)) / secs
    return east, north


def closest_approach(storm: Storm, lat: float, lon: float, step_hours: float = 0.5) -> tuple[datetime, float]:
    """Time (UTC) and distance (km) of the storm centre's closest approach to a point."""
    track = storm.track
    t = track[0].t
    end = track[-1].t
    best_t, best_d = t, float("inf")
    while t <= end:
        f = interpolate(storm, t)
        d = float(haversine_km(f.lat, f.lon, lat, lon))
        if d < best_d:
            best_t, best_d = t, d
        t += timedelta(hours=step_hours)
    return best_t, best_d


def hourly_times(storm: Storm, t0: datetime, before_h: float, after_h: float, step_h: float = 1.0) -> list[datetime]:
    lo = max(storm.track[0].t, t0 - timedelta(hours=before_h))
    hi = min(storm.track[-1].t, t0 + timedelta(hours=after_h))
    out, t = [], lo
    while t <= hi:
        out.append(t)
        t += timedelta(hours=step_h)
    return out


def scenario_storm(storm: Storm, *, cross_track_km: float = 0.0, delta_kt: float = 0.0,
                   name_suffix: str = "") -> Storm:
    """What-if variant: shift the whole track sideways and/or change intensity.

    cross_track_km > 0 shifts to the right of the direction of motion (north-west track
    shift for a storm moving north-west is a left shift). Intensity change also scales the
    central pressure deficit so wind and pressure stay physically consistent
    (dp ~ (vmax / 6.7)^(1/0.644), Atkinson-Holland relation).
    """
    if cross_track_km == 0.0 and delta_kt == 0.0:
        return storm
    track = storm.track
    fixes: list[Fix] = []
    for i, f in enumerate(track):
        a = track[max(i - 1, 0)]
        b = track[min(i + 1, len(track) - 1)]
        dy = (b.lat - a.lat) * 111.195
        dx = (b.lon - a.lon) * 111.195 * math.cos(math.radians(f.lat))
        norm = math.hypot(dx, dy) or 1.0
        # right-hand normal of the direction of motion
        rx, ry = dy / norm, -dx / norm
        lat, lon = offset_km(f.lat, f.lon, rx * cross_track_km, ry * cross_track_km)
        nf = f.model_copy(update={"lat": lat, "lon": lon})
        if f.vmax_kt is not None and delta_kt:
            v_new = max(20.0, f.vmax_kt + delta_kt)
            nf.vmax_kt = v_new
            if f.mslp_hpa:
                penv = f.poci_hpa or 1010.0
                dp_old = max(penv - f.mslp_hpa, 1.0)
                dp_new = dp_old * (v_new / max(f.vmax_kt, 1.0)) ** (1 / 0.644)
                nf.mslp_hpa = penv - dp_new
        fixes.append(nf)
    label = []
    if cross_track_km:
        label.append(f"track {cross_track_km:+.0f} km")
    if delta_kt:
        label.append(f"intensity {delta_kt:+.0f} kt")
    return storm.model_copy(update={
        "fixes": fixes, "forecast": [], "kind": "scenario",
        "id": f"{storm.id}~s", "name": f"{storm.name} ({', '.join(label)})" + name_suffix,
    })


def knots_to_ms(kt: float) -> float:
    return kt * KT_TO_MS


def track_to_geojson(storm: Storm) -> dict:
    coords = [[f.lon, f.lat] for f in storm.track]
    feats = [{"type": "Feature", "properties": {"kind": "track", "name": storm.name},
              "geometry": {"type": "LineString", "coordinates": coords}}]
    for f in storm.track:
        feats.append({"type": "Feature",
                      "properties": {"kind": "fix", "t": f.t.isoformat(), "vmax_kt": f.vmax_kt, "mslp_hpa": f.mslp_hpa},
                      "geometry": {"type": "Point", "coordinates": [f.lon, f.lat]}})
    return {"type": "FeatureCollection", "features": feats}
