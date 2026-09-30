from __future__ import annotations

from app import engine
from app.ai.bulletin import Bulletin, Point, to_storm


def _bulletin(**kw) -> Bulletin:
    base = dict(storm_name="testa", agency="IMD", bulletin_no="7", issued_utc="2025-10-27T09:00:00Z", wind_averaging_min=3,
                current=Point(time_utc="2025-10-27T09:00:00Z", lat=15.8, lon=83.0, wind=45, wind_unit="kt"),
                forecast=[Point(hours_from_issue=12, lat=16.5, lon=82.4, wind=80, wind_unit="kmph"),
                          Point(time_utc="2025-10-28T09:00:00Z", lat=17.4, lon=82.0, wind=55, wind_unit="kt")],
                surge_text="Storm surge of about 1 m above astronomical tide", surge_low_m=1.0, surge_high_m=1.0)
    base.update(kw)
    return Bulletin(**base)


def test_units_times_and_track_are_normalised():
    storm, issues = to_storm(_bulletin(), "abc12345feed")
    assert storm is not None and storm.kind == "bulletin" and storm.wind_avg_period_min == 3
    assert storm.fixes[0].vmax_kt == 45
    fc = {round(f.vmax_kt) for f in storm.forecast}
    assert 43 in fc and 55 in fc                                     # 80 km/h -> ~43 kt
    assert any("converted 80 km/h" in i["msg"] for i in issues)
    times = [f.t for f in storm.track]
    assert times == sorted(times)


def test_implausible_position_or_wind_is_rejected_not_trusted():
    b = _bulletin(forecast=[Point(hours_from_issue=12, lat=75.0, lon=82.4, wind=60, wind_unit="kt"),      # 75N: read error
                            Point(hours_from_issue=24, lat=17.0, lon=82.0, wind=900, wind_unit="kt")])   # 900 kt: unit error
    storm, issues = to_storm(b, "deadbeef0000")
    assert any("outside the plausible basin box" in i["msg"] for i in issues)
    assert any("implausible" in i["msg"] for i in issues)
    assert all(f.lat < 35 for f in storm.track)
    assert all((f.vmax_kt or 0) <= 200 for f in storm.track)


def test_missing_time_points_are_dropped_and_reported():
    b = _bulletin(issued_utc=None, forecast=[Point(lat=16.0, lon=83.0, wind=50, wind_unit="kt")])
    storm, issues = to_storm(b, "0123456789ab")
    assert any(i["level"] == "error" for i in issues)               # no issue time
    assert storm is None or len(storm.track) >= 1


def test_no_valid_points_returns_no_storm():
    b = _bulletin(current=None, forecast=[Point(hours_from_issue=6, lat=80, lon=10, wind=40, wind_unit="kt")])
    storm, issues = to_storm(b, "ffffffffffff")
    assert storm is None and any("no valid track points" in i["msg"] for i in issues)


def test_official_surge_from_a_bulletin_is_carried_into_the_simulation():
    storm, _ = to_storm(_bulletin(current=Point(time_utc="2025-10-27T09:00:00Z", lat=16.0, lon=83.6, wind=60, wind_unit="kt"),
                                  forecast=[Point(time_utc="2025-10-28T09:00:00Z", lat=17.7, lon=83.2, wind=80, wind_unit="kt")]), "cafebabe1234")
    sim = engine.simulate("IN-AP", storm, ensemble=False)
    assert sim["storm"]["kind"] == "bulletin"
    assert sim["official_surge"]["high_m"] == 1.0 and "astronomical tide" in sim["official_surge"]["text"]
    assert "read by Gemini" in sim["storm"]["source"]


def test_replay_has_no_official_surge():
    assert engine.simulate("IN-AP", "hudhud-2014", ensemble=False)["official_surge"] is None
