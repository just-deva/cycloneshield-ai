"""Screening-level storm-tide estimate for a coastal sector.

  storm_tide = inverse barometer + wind set-up + astronomical tide      (then x sector calibration k)
  inverse barometer  ~ 1 cm per hPa of pressure drop at the sector
  wind set-up        = tau * L / (rho_w * g * h),  tau = rho_a * Cd * U^2  (steady 1-D shelf balance)
  Cd                 = min((0.75 + 0.067 U) * 1e-3, 2.5e-3)              (saturates in high winds)

L and h are the effective shelf width and mean depth for the sector. Wave set-up is ignored.
This is the same *class* of method as IMD's surge nomograms; it is not a hydrodynamic model (ADCIRC
runs operationally at INCOIS) and is labelled "screening-level" in the product. Where IMD publishes a
surge range in its bulletin, that official number overrides ours for display.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RHO_A = 1.15
RHO_W = 1025.0
G = 9.81
IB_M_PER_HPA = 0.01


@dataclass(frozen=True)
class Shelf:
    """Effective shelf geometry and calibration for one coastal sector."""
    id: str
    lat: float
    lon: float
    width_km: float       # L
    depth_m: float        # mean depth h
    k: float = 1.0        # calibration multiplier on (IB + wind set-up)
    note: str = ""


def drag_coefficient(u10_ms: float) -> float:
    return min((0.75 + 0.067 * u10_ms) * 1e-3, 2.5e-3)


def wind_setup_m(onshore_ms: float, shelf: Shelf) -> float:
    if onshore_ms <= 0:
        return 0.0
    tau = RHO_A * drag_coefficient(onshore_ms) * onshore_ms ** 2
    return tau * shelf.width_km * 1000.0 / (RHO_W * G * shelf.depth_m)


def inverse_barometer_m(local_pressure_hpa: float, p_env_hpa: float = 1010.0) -> float:
    return max(p_env_hpa - local_pressure_hpa, 0.0) * IB_M_PER_HPA


def storm_tide_m(shelf: Shelf, onshore_ms: float, local_pressure_hpa: float, tide_m: float,
                 p_env_hpa: float = 1010.0) -> dict[str, float]:
    ib = inverse_barometer_m(local_pressure_hpa, p_env_hpa)
    ws = wind_setup_m(onshore_ms, shelf)
    surge = shelf.k * (ib + ws)
    return {"inverse_barometer_m": ib, "wind_setup_m": ws, "surge_m": surge, "tide_m": tide_m,
            "total_m": surge + tide_m}


def xu_bathtub_reference_m(wind_ms: float) -> float:
    """CLIMADA-petals TCSurgeBathtub cross-check (Xu 2010; fitted to US SLOSH runs). NOT Indian-calibrated."""
    return 0.1023 * max(wind_ms - 26.8224, 0.0) + 1.8288
