"""Storm data model shared by replay, live and bulletin-extracted tracks.

All times are timezone-aware UTC. Winds are kept in knots with the averaging
period recorded per storm, because JTWC (1-min), IMD (3-min) and JMA (10-min)
are not interchangeable (Fani peaked at 150 kt by JTWC and 115 kt by IMD).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

KT_TO_MS = 0.514444
KT_TO_KMH = 1.852
NM_TO_KM = 1.852


class Fix(BaseModel):
    t: datetime
    lat: float
    lon: float
    vmax_kt: float | None = None
    mslp_hpa: float | None = None
    poci_hpa: float | None = Field(default=None, description="Pressure of outermost closed isobar")
    rmw_nm: float | None = None
    # 34/50/64 kt wind radii, nautical miles, quadrants NE, SE, SW, NW
    r34_nm: list[float] | None = None
    r50_nm: list[float] | None = None
    r64_nm: list[float] | None = None

    @property
    def vmax_kmh(self) -> float | None:
        return None if self.vmax_kt is None else self.vmax_kt * KT_TO_KMH


class Storm(BaseModel):
    id: str
    name: str
    basin: str = Field(description="IO = North Indian Ocean, WP = West Pacific, ...")
    season: int
    source: str = Field(description="Where the numbers came from, shown in the UI")
    authority: str = Field(default="JTWC guidance (not an official warning)")
    wind_avg_period_min: int = 1
    kind: Literal["replay", "live", "bulletin", "scenario"] = "replay"
    summary: str = ""
    fixes: list[Fix]
    forecast: list[Fix] = Field(default_factory=list)
    reference: dict = Field(default_factory=dict, description="Observed facts used for calibration/validation")

    @property
    def track(self) -> list[Fix]:
        """Observed + forecast fixes in time order."""
        merged = {f.t: f for f in self.fixes}
        for f in self.forecast:
            merged.setdefault(f.t, f)
        return [merged[k] for k in sorted(merged)]

    def peak_kt(self) -> float:
        return max((f.vmax_kt or 0.0) for f in self.track)
