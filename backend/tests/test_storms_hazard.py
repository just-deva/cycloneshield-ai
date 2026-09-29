from __future__ import annotations

import json
import math
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

from app.hazard import rain, surge, wind
from app.storms.atcf import parse_bdeck, parse_tcw
from app.storms.model import Storm
from app.storms.track import closest_approach, haversine_km, interpolate, motion_ms, scenario_storm

DATA = Path(__file__).resolve().parent.parent / "data" / "storms"

BDECK = """\
IO, 01, 2026092218,   , BEST,   0, 176N, 0848E,  35,  991, XX,  34, NEQ,    0,   35,   65,   60, 1004,  220,  25,   0,   0,   L,   0,    ,   0,   0,     ONE, D,
IO, 01, 2026092400,   , BEST,   0, 181N, 0837E,  35,  987, XX,  34, NEQ,   25,   40,   45,   35, 1004,  315,  20,   0,   0,   L,   0,    ,   0,   0,     ONE, D,
"""

TCW = """\
WTPN51 PGTW 291500
WARNING    ATCG MIL 25W NWP 260929133256
2026092912 25W SURIGAE    026  01 080 12 SATL 030
T000 292N 1363E 045 R034 060 NE QD 080 SE QD 080 SW QD 040 NW QD
T012 305N 1383E 040 R034 060 NE QD 080 SE QD 070 SW QD 035 NW QD
"""


def load(storm_id: str) -> Storm:
    return Storm.model_validate(json.loads((DATA / f"{storm_id}.json").read_text(encoding="utf-8")))


def test_parse_bdeck_units_and_radii():
    fixes, name = parse_bdeck(BDECK)
    assert name == "ONE"
    assert len(fixes) == 2
    assert fixes[0].lat == pytest.approx(17.6) and fixes[0].lon == pytest.approx(84.8)
    assert fixes[1].vmax_kt == 35 and fixes[1].mslp_hpa == 987
    assert fixes[1].r34_nm == [25.0, 40.0, 45.0, 35.0]
    assert fixes[1].rmw_nm == 20


def test_parse_tcw_forecast():
    fixes, name = parse_tcw(TCW)
    assert name == "SURIGAE"
    assert [f.t.hour for f in fixes] == [12, 0]
    assert fixes[0].lat == pytest.approx(29.2) and fixes[0].lon == pytest.approx(136.3)
    assert fixes[1].r34_nm == [60.0, 80.0, 70.0, 35.0]


def test_replay_library_is_real_and_complete():
    for sid, peak in {"hudhud-2014": 115, "fani-2019": 135, "amphan-2020": 145, "yagi-2024": 130}.items():
        s = load(sid)
        assert s.peak_kt() == peak
        assert len(s.fixes) >= 8


def test_hudhud_closest_approach_to_visakhapatnam():
    s = load("hudhud-2014")
    t0, d = closest_approach(s, 17.6868, 83.2185)
    assert d < 60.0            # Hudhud made landfall at Visakhapatnam
    assert t0.day == 12 and t0.month == 10


def test_interpolation_between_fixes():
    s = load("hudhud-2014")
    a, b = s.fixes[3], s.fixes[4]
    mid = interpolate(s, a.t + (b.t - a.t) / 2)
    assert min(a.lat, b.lat) <= mid.lat <= max(a.lat, b.lat)
    assert min(a.vmax_kt, b.vmax_kt) <= mid.vmax_kt <= max(a.vmax_kt, b.vmax_kt)


def test_scenario_shift_moves_track_and_scales_pressure():
    s = load("fani-2019")
    shifted = scenario_storm(s, cross_track_km=50, delta_kt=20)
    d = haversine_km(s.fixes[10].lat, s.fixes[10].lon, shifted.fixes[10].lat, shifted.fixes[10].lon)
    assert d == pytest.approx(50.0, abs=1.0)
    assert shifted.fixes[10].vmax_kt == s.fixes[10].vmax_kt + 20
    assert shifted.fixes[10].mslp_hpa < s.fixes[10].mslp_hpa


def test_holland_peak_matches_reported_vmax():
    fix = load("hudhud-2014").fixes[-1]           # 105 kt, 944 hPa, RMW 15 nm
    p = wind.holland_params(fix)
    assert 1.0 <= p.b <= 2.5
    east = np.linspace(-150, 150, 601)
    lats = np.full_like(east, fix.lat)
    lons = fix.lon + east / (111.195 * math.cos(math.radians(fix.lat)))
    w = wind.wind_field(p, lats, lons)
    assert w["speed"].max() == pytest.approx(p.vmax_ms, rel=0.05)
    # maximum sits near the radius of maximum wind
    r_at_max = w["r_km"][w["speed"].argmax()]
    assert abs(r_at_max - p.rmw_km) < 10


def test_wind_is_cyclonic_and_stronger_on_the_right_of_track():
    fix = load("hudhud-2014").fixes[-1]
    p = wind.holland_params(fix)
    # storm moving north at 5 m/s; NH cyclonic flow -> right side (east) sees stronger wind
    east_pt = wind.wind_field(p, [fix.lat], [fix.lon + 0.3], 0.0, 5.0)
    west_pt = wind.wind_field(p, [fix.lat], [fix.lon - 0.3], 0.0, 5.0)
    assert east_pt["speed"][0] > west_pt["speed"][0]
    # counter-clockwise: east of centre the wind blows toward north (v>0)
    assert east_pt["v"][0] > 0 and west_pt["v"][0] < 0


def test_wind_decays_with_distance():
    p = wind.holland_params(load("fani-2019").fixes[-1])
    near = wind.wind_field(p, [p.lat], [p.lon + 0.3])["speed"][0]
    far = wind.wind_field(p, [p.lat], [p.lon + 3.0])["speed"][0]
    assert near > far


def test_surge_worked_examples_from_research():
    vizag = surge.Shelf("v", 17.7, 83.4, width_km=30, depth_m=50)
    odisha = surge.Shelf("o", 19.8, 85.9, width_km=60, depth_m=20)
    assert surge.wind_setup_m(50, vizag) == pytest.approx(0.43, abs=0.03)
    assert surge.wind_setup_m(50, odisha) == pytest.approx(2.15, abs=0.1)
    assert surge.wind_setup_m(0, vizag) == 0.0


def test_surge_budget_adds_up_and_inverse_barometer():
    sh = surge.Shelf("v", 17.7, 83.4, 30, 50, k=1.0)
    out = surge.storm_tide_m(sh, onshore_ms=40, local_pressure_hpa=960, tide_m=0.3)
    assert out["inverse_barometer_m"] == pytest.approx(0.5, abs=0.01)
    assert out["total_m"] == pytest.approx(out["surge_m"] + 0.3)


def test_rcliper_shape_and_units():
    r = np.array([0, 30, 60, 120, 250, 400])
    rate = rain.rcliper_rate_mm_h(80, r)
    assert (rate[:-1] > 0).all() and rate[-1] == 0          # cut-off at 300 km
    assert rate[2] > rate[4]                                  # decays outward
    assert rain.rcliper_rate_mm_h(120, 40) > rain.rcliper_rate_mm_h(50, 40)   # stronger storm rains more


def test_motion_of_hudhud_is_northwestward():
    s = load("hudhud-2014")
    e, n = motion_ms(s, s.fixes[-3].t)
    assert n > 0 and e < 0.5
