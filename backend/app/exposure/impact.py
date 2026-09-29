"""Transparent hazard -> consequence rules. Every threshold is listed in METHODOLOGY and shown in the UI.

Nothing here is a black box: statuses come from explicit thresholds; the numbers an LLM may quote come
from these functions, never from the model. Thresholds are decision-support screening values, not
engineering fragility curves - a bare Emanuel/Eberenz loss ratio in particular describes aggregate
economic loss, not the failure probability of a given pole or hospital.
"""
from __future__ import annotations

import numpy as np

# wind bands (km/h, on the storm's own averaging basis) aligned with IMD cyclone classes
GALE, DAMAGING, DESTRUCTIVE, EXTREME = 62.0, 89.0, 118.0, 167.0
PASSABLE_DEPTH_M = 0.3
HOSPITAL_CRITICAL_DEPTH_M = 1.0
SUBSTATION_CRITICAL_DEPTH_M = 0.5
IMD_HEAVY, IMD_VERY_HEAVY, IMD_EXTREME = 64.5, 115.6, 204.5

# Emanuel (2011) sigmoid: f = v^3 / (1 + v^3), v = max(V - V_thresh, 0) / (V_half - V_thresh).
# V_half for the North Indian Ocean: value shipped in CLIMADA's Eberenz et al. (2021) calibration table
# (RMSF-optimised). The paper text quotes 55.8 m/s; the referee found 58.7 in the shipped file, so we use that.
EMANUEL_V_THRESH = 25.7
EMANUEL_V_HALF_NI = 58.7

STATUS_ORDER = {"ok": 0, "watch": 1, "at_risk": 2, "critical": 3}

METHODOLOGY = [
    {"module": "Storm input", "method": "JTWC best track (replay) / JTWC+GDACS live / IMD bulletin read by Gemini", "assumptions": "1-min winds (JTWC) run ~5-10% above IMD 3-min winds; official warnings come only from IMD."},
    {"module": "Wind field", "method": "Holland (1980) parametric profile from best-track vmax, MSLP and radius of max wind; surface = 0.85 x gradient wind; 20 deg inflow; +0.5 x translation vector on the right of track", "assumptions": "0.85, 20 deg and 0.5 are standard-practice choices, not fitted here; default RMW (25-60 km by intensity) when the best track has none."},
    {"module": "Storm surge", "method": "Inverse barometer (1 cm/hPa) + steady wind set-up tau*L/(rho*g*h) + tide, x sector calibration k", "assumptions": "Screening-level (same class as IMD nomograms). L and h are hand-set per sector; k is calibrated on 1-2 events per coast (see calibration table). No wave set-up, no hydrodynamics."},
    {"module": "Inundation", "method": "Sea-connected bathtub: elevation < surge level - 0.2 m/km x distance from sea; only cells hydraulically connected to the sea flood", "assumptions": "DEM is a surface model (SRTM-derived), biased high under buildings/trees, so it under-predicts; depths are shown as classes."},
    {"module": "Rain", "method": "R-CLIPER track-only rain rate (Tuleya et al. 2007) integrated along the track, 24-h maximum", "assumptions": "Symmetric, no orography, US-trained: under-predicts stalled/monsoon-interacting events. Blend with NWP when available."},
    {"module": "Damage pathways", "method": "Priority-flood depression filling + D8 flow accumulation on the DEM: waterlogging basins (0.5-3 m fill) and runoff corridors (>=0.5 km2 upstream); active when 24-h rain reaches IMD heavy (64.5 mm) / very heavy (115.6 mm)", "assumptions": "No drainage network, pumps, land-use imperviousness or tide-locking. Indicates where water collects/flows, not depth."},
    {"module": "Asset status", "method": "Hospital/substation/shelter status from wind band, surge depth and pluvial state (thresholds in the asset table's reasons)", "assumptions": "Screening thresholds, not engineering fragility. OSM covers HV lines/roads/urban hospitals well, distribution poles and designated cyclone shelters poorly."},
    {"module": "Roads and evacuation", "method": "NetworkX Dijkstra on the OSM road graph; nodes blocked at flood depth >= 0.3 m or pluvial-likely; routes only to safe shelters", "assumptions": "Free-flow speeds by road class; no traffic, capacity or shelter occupancy."},
    {"module": "Confidence", "method": "9 scenarios: track -40/0/+40 km cross-track x intensity -10/0/+10 kt; k/9 = share of scenarios in which the hazard reaches the asset", "assumptions": "Not a calibrated probability."},
    {"module": "Expected loss ratio", "method": "Emanuel (2011) sigmoid with North-Indian-Ocean V_half = 58.7 m/s (CLIMADA/Eberenz 2021 shipped calibration), V_thresh = 25.7 m/s", "assumptions": "Aggregate expected fraction of exposed value lost, not a structural failure probability. Near zero below ~50 kt."},
]


def imd_category(kmh: float) -> str:
    """IMD-style class label for a maximum sustained wind (km/h)."""
    if kmh >= 222:
        return "Super Cyclonic Storm"
    if kmh >= 167:
        return "Extremely Severe Cyclonic Storm"
    if kmh >= 118:
        return "Very Severe Cyclonic Storm"
    if kmh >= 89:
        return "Severe Cyclonic Storm"
    if kmh >= 62:
        return "Cyclonic Storm"
    if kmh >= 50:
        return "Deep Depression"
    if kmh >= 31:
        return "Depression"
    return "Low pressure / weaker"


def emanuel_loss_ratio(v_ms: float, v_half: float = EMANUEL_V_HALF_NI, v_thresh: float = EMANUEL_V_THRESH) -> float:
    vn = max(v_ms - v_thresh, 0.0) / (v_half - v_thresh)
    return float(vn ** 3 / (1 + vn ** 3))


def rain_class(mm24: float) -> str:
    if mm24 >= IMD_EXTREME:
        return "extremely heavy"
    if mm24 >= IMD_VERY_HEAVY:
        return "very heavy"
    if mm24 >= IMD_HEAVY:
        return "heavy"
    return "below heavy"


def pluvial_state(mm24: float, in_basin: bool, in_corridor: bool) -> str:
    if not (in_basin or in_corridor):
        return "none"
    if mm24 >= IMD_VERY_HEAVY:
        return "likely"
    if mm24 >= IMD_HEAVY:
        return "possible"
    return "none"


def _worse(a: str, b: str) -> str:
    return a if STATUS_ORDER[a] >= STATUS_ORDER[b] else b


def assess_point(kind: str, wind_kmh: float, depth_m: float, pluvial: str,
                 designated: bool = False) -> tuple[str, list[str], bool]:
    """Return (status, reasons, usable_as_shelter)."""
    reasons: list[str] = []
    status = "ok"
    crit_depth = HOSPITAL_CRITICAL_DEPTH_M if kind == "hospital" else SUBSTATION_CRITICAL_DEPTH_M
    if kind in ("hospital", "substation"):
        if depth_m >= crit_depth:
            status = _worse(status, "critical"); reasons.append(f"surge depth {depth_m:.1f} m (>= {crit_depth:.1f} m critical for a {kind})")
        elif depth_m >= PASSABLE_DEPTH_M:
            status = _worse(status, "at_risk"); reasons.append(f"surge depth {depth_m:.1f} m (>= {PASSABLE_DEPTH_M} m)")
        elif depth_m > 0:
            status = _worse(status, "watch"); reasons.append(f"shallow surge water {depth_m:.1f} m")
        if wind_kmh >= DESTRUCTIVE:
            status = _worse(status, "critical"); reasons.append(f"wind {wind_kmh:.0f} km/h (>= {DESTRUCTIVE:.0f}, destructive)")
        elif wind_kmh >= DAMAGING:
            status = _worse(status, "at_risk"); reasons.append(f"wind {wind_kmh:.0f} km/h (>= {DAMAGING:.0f}, damaging)")
        elif wind_kmh >= GALE:
            status = _worse(status, "watch"); reasons.append(f"gale-force wind {wind_kmh:.0f} km/h")
        if pluvial == "likely":
            status = _worse(status, "at_risk"); reasons.append("in a waterlogging basin / runoff corridor with very heavy rain")
        elif pluvial == "possible":
            status = _worse(status, "watch"); reasons.append("in a waterlogging basin / runoff corridor with heavy rain")
        return status, reasons, False
    # shelter: cyclone shelters exist to ride out the wind, so only FLOODING makes one unusable. Wind
    # matters for (a) how long people have to reach it and (b) non-rated candidate buildings.
    usable = True
    if depth_m > 0:
        usable = False; status = "critical"; reasons.append(f"flooded by surge ({depth_m:.1f} m)")
    if pluvial == "likely":
        usable = False; status = _worse(status, "at_risk"); reasons.append("waterlogging likely at the site")
    elif pluvial == "possible":
        status = _worse(status, "watch"); reasons.append("waterlogging possible at the site")
    if not designated:
        if wind_kmh >= EXTREME:
            status = _worse(status, "at_risk"); reasons.append(f"wind {wind_kmh:.0f} km/h: candidate building is not cyclone-rated (prefer designated shelters)")
        elif wind_kmh >= DESTRUCTIVE:
            status = _worse(status, "watch"); reasons.append(f"destructive wind {wind_kmh:.0f} km/h: candidate building, not cyclone-rated")
    return status, reasons, usable


def first_time(series: np.ndarray, hours: np.ndarray, threshold: float) -> float | None:
    """First hour (relative to landfall reference) at which a per-time series reaches a threshold."""
    idx = np.flatnonzero(series >= threshold)
    return None if idx.size == 0 else float(hours[idx[0]])
