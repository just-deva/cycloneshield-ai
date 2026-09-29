"""Local, explainable ward-risk model; replaceable by a GEE data source."""
from __future__ import annotations

from typing import Any

from shapely.geometry import Point, shape


def _distance_km(a: Point, b: Point) -> float:
    # Accurate enough for this compact pilot geography.
    return a.distance(b) * 111.0


def _level(score: float) -> str:
    if score >= 75:
        return "Critical"
    if score >= 55:
        return "High"
    if score >= 35:
        return "Moderate"
    return "Low"


def calculate_ward_risks(wards_data: list[dict[str, Any]], active_track_point: dict[str, Any]) -> list[dict[str, Any]]:
    """Score wards with the documented Hazard/Exposure/Vulnerability/Criticality mix."""
    storm = Point(float(active_track_point["lng"]), float(active_track_point["lat"]))
    wind, surge = float(active_track_point["wind_speed_kmh"]), float(active_track_point["surge_height_m"])
    max_population = max((int(ward["population"]) for ward in wards_data), default=1)
    results: list[dict[str, Any]] = []
    for ward in wards_data:
        polygon = shape(ward["geojson"])
        distance = _distance_km(polygon.centroid, storm)
        proximity = max(0.0, 100 - distance * 7)
        coastal_lowland = max(0.0, 100 - float(ward["elevation_m"]) * 6)
        intensity = min(100.0, (wind / 130 * 65) + (surge / 2.5 * 35))
        hazard = min(100.0, 0.55 * proximity + 0.25 * coastal_lowland + 0.20 * intensity)
        exposure = min(100.0, int(ward["population"]) / max_population * 100)
        vulnerability = min(100.0, float(ward["non_pucca_housing_pct"]) * 2.4 + coastal_lowland * 0.25)
        assets = ward.get("critical_assets", {})
        asset_count = len(assets.get("hospitals", [])) + len(assets.get("power_substations", []))
        criticality = min(100.0, asset_count * 38 + exposure * 0.24)
        score = round(0.30 * hazard + 0.25 * exposure + 0.25 * vulnerability + 0.20 * criticality, 1)
        results.append({"ward_id": ward["id"], "ward_name": ward["name"], "risk_score": score,
                        "risk_level": _level(score), "hazard_score": round(hazard, 1),
                        "distance_to_track_km": round(distance, 1), "affected_assets": assets})
    return sorted(results, key=lambda item: item["risk_score"], reverse=True)
