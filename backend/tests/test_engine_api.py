from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_and_tenants():
    h = client.get("/api/health").json()
    assert h["status"] == "online" and "IN-AP" in h["tenants"]
    ts = {t["id"]: t for t in client.get("/api/tenants").json()}
    assert ts["IN-AP"]["calibrated"] and not ts["VN"]["calibrated"]


def test_simulate_hudhud_visakhapatnam():
    r = client.post("/api/simulate", json={"tenant_id": "IN-AP", "storm_id": "hudhud-2014", "ensemble": False}).json()
    assert r["closest_approach_km"] < 30                     # Hudhud hit Visakhapatnam
    assert r["focus"]["peak_wind_kmh"] > 150
    by = r["summary"]["by_kind"]
    assert by["hospital"]["total"] > 100 and by["substation"]["total"] > 20
    # calibrated surge at the port lands inside the observed 1.2-1.4 m window (in-sample, n=1)
    port = next(s for s in r["sectors"] if s["id"] == "port-gajuwaka")
    assert 1.1 <= port["surge_m"] <= 1.5
    assert r["evacuation"]["summary"]["routed"] > 0
    # the overlay is served and is a PNG
    png = client.get(r["layers"]["inundation"])
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"


def test_weak_near_miss_does_not_cry_wolf():
    r = client.post("/api/simulate", json={"tenant_id": "IN-AP", "storm_id": "montha-2025", "ensemble": False}).json()
    by = r["summary"]["by_kind"]
    assert by["hospital"]["critical"] == 0 and by["hospital"]["at_risk"] == 0
    assert r["flooded_km2"] == 0


def test_scenario_sliders_change_the_outcome():
    base = client.post("/api/simulate", json={"tenant_id": "IN-AP", "storm_id": "hudhud-2014", "ensemble": False}).json()
    weaker = client.post("/api/simulate", json={"tenant_id": "IN-AP", "storm_id": "hudhud-2014", "delta_kt": -40, "ensemble": False}).json()
    assert weaker["focus"]["peak_wind_kmh"] < base["focus"]["peak_wind_kmh"]


def test_unknown_inputs_are_404():
    assert client.post("/api/simulate", json={"tenant_id": "XX", "storm_id": "hudhud-2014"}).status_code == 404
    assert client.post("/api/simulate", json={"tenant_id": "IN-AP", "storm_id": "nope"}).status_code == 404


def test_calibration_is_labelled_in_sample():
    c = client.get("/api/calibration/IN-AP").json()
    assert c["calibrated"] and "NOT a validation" in c["note"]
    assert client.get("/api/calibration/VN").json()["calibrated"] is False


def test_methodology_lists_assumptions():
    m = client.get("/api/methodology").json()
    assert len(m["modules"]) >= 8 and "NOT an official warning" in m["disclaimer"]
