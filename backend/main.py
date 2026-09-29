from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from shapely.geometry import shape

from gee_engine import calculate_ward_risks
from gemini_ai import generate_advisory
from parametric import evaluate_parametric_payout
from router import configure_road_network, get_flood_safe_route
from track_engine import get_active_waypoint

SCENARIO_PATH = Path(__file__).resolve().parent.parent / "frontend" / "public" / "mockData.json"
with SCENARIO_PATH.open(encoding="utf-8") as file:
    SCENARIO: dict[str, Any] = json.load(file)
configure_road_network(SCENARIO["road_network"])

app = FastAPI(title="CycloneShield AI", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


class SimulationRequest(BaseModel):
    timeline_step: str = Field(default="T-24h")


class AdvisoryRequest(BaseModel):
    ward_name: str
    risk_level: str
    blocked_roads: list[str] = Field(default_factory=list)
    assigned_shelter: str | None = None
    language: str = "English"


def _flooded_roads(point: dict[str, Any]) -> list[str]:
    flooded: list[str] = []
    if point["wind_speed_kmh"] >= 90:
        flooded.extend(["beach-road", "harbour-road"])
    if point["surge_height_m"] >= 1.5:
        flooded.append("waltair-main-road")
    if point["rainfall_24h_mm"] >= 180:
        flooded.append("gajuwaka-link")
    return flooded


def _simulate(timeline_step: str) -> dict[str, Any]:
    try:
        active = get_active_waypoint(SCENARIO["cyclone_track"], timeline_step)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    risks = calculate_ward_risks(SCENARIO["wards"], active)
    flooded_ids = _flooded_roads(active)
    road_names = {edge["id"]: edge["name"] for edge in SCENARIO["road_network"]["edges"]}
    routes = []
    for ward in SCENARIO["wards"]:
        centroid = shape(ward["geojson"]).centroid
        route = get_flood_safe_route((centroid.y, centroid.x), SCENARIO["shelters"], flooded_ids)
        routes.append({"ward_id": ward["id"], "ward_name": ward["name"], "route": route})
    payout = evaluate_parametric_payout(active["wind_speed_kmh"], active["rainfall_24h_mm"], active["surge_height_m"])
    return {"active_track_point": active, "ward_risks": risks, "routes": routes,
            "flooded_road_ids": flooded_ids, "blocked_roads": [road_names[key] for key in flooded_ids],
            "parametric_payout": payout, "track": SCENARIO["cyclone_track"], "wards": SCENARIO["wards"],
            "shelters": SCENARIO["shelters"], "road_network": SCENARIO["road_network"]}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "online", "system": "CycloneShield AI"}


@app.get("/api/mock-scenario")
def mock_scenario() -> dict[str, Any]:
    """Expose the complete static fallback payload for disconnected frontend use."""
    return SCENARIO


@app.post("/api/simulate-track")
def simulate_track(request: SimulationRequest) -> dict[str, Any]:
    return _simulate(request.timeline_step)


@app.post("/api/generate-advisory")
def advisory(request: AdvisoryRequest) -> dict[str, Any]:
    return generate_advisory(request.ward_name, request.risk_level, request.blocked_roads,
                             request.assigned_shelter, request.language)
