"""Track-only rainfall prior: R-CLIPER (Tuleya, Demaria & Kuligowski 2007).

R-CLIPER gives an azimuthally symmetric rain rate from the storm's intensity alone, so it works
when only a track is known. It has no orography, no vertical shear and is US-trained, which means it
UNDER-predicts stalled/monsoon-interacting events (e.g. Michaung over Chennai). We therefore treat it
as a scenario prior and blend it with NWP rainfall (Open-Meteo GFS ensemble) when available.

  U  = 1 + (Vmax_kt - 35)/33
  T0 = -1.10 + 3.96 U,  Tm = -1.60 + 4.80 U      [inch/day]
  rm = 64.5 - 13.0 U,   re = 150 - 16.0 U        [km]
  r <= rm : R = T0 + (Tm - T0) r / rm
  r  > rm : R = Tm exp(-(r - rm)/re)
Coefficients were read from CLIMADA-petals `tc_rainfield.py` (TCRain, R-CLIPER branch).
"""
from __future__ import annotations

import numpy as np

INCH_DAY_TO_MM_H = 25.4 / 24.0
MAX_RADIUS_KM = 300.0


def rcliper_rate_mm_h(vmax_kt: float, r_km) -> np.ndarray:
    r = np.asarray(r_km, dtype=float)
    u = 1.0 + (max(vmax_kt, 20.0) - 35.0) / 33.0
    t0 = -1.10 + 3.96 * u
    tm = -1.60 + 4.80 * u
    rm = 64.5 - 13.0 * u
    re = 150.0 - 16.0 * u
    inner = t0 + (tm - t0) * r / rm
    outer = tm * np.exp(-(r - rm) / re)
    rate = np.where(r <= rm, inner, outer) * INCH_DAY_TO_MM_H
    rate = np.where(r > MAX_RADIUS_KM, 0.0, rate)
    return np.maximum(rate, 0.0)
