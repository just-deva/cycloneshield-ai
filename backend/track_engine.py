"""Geospatial helpers for the deterministic cyclone track simulation."""
from __future__ import annotations

from typing import Any

from shapely.geometry import LineString, Point, Polygon


def build_track_buffer_cone(track_waypoints: list[dict[str, Any]], buffer_km: float) -> Polygon:
    """Return a buffered track polygon.

    Waypoints are WGS84 dictionaries with ``lat`` and ``lng`` fields.  A single
    point is supported and produces a circular warning zone.
    """
    if buffer_km <= 0:
        raise ValueError("buffer_km must be positive")
    if not track_waypoints:
        raise ValueError("at least one track waypoint is required")
    coordinates = [(float(point["lng"]), float(point["lat"])) for point in track_waypoints]
    geometry = Point(coordinates[0]) if len(coordinates) == 1 else LineString(coordinates)
    # At Visakhapatnam's latitude one degree longitude is roughly 106 km;
    # this degree conversion is adequate for a transparent city-scale MVP.
    return geometry.buffer(buffer_km / 106.0)


def get_active_waypoint(track_waypoints: list[dict[str, Any]], timeline_step: str) -> dict[str, Any]:
    """Return the complete state at a named timeline step."""
    normalized = timeline_step.strip().lower()
    for waypoint in track_waypoints:
        if str(waypoint.get("step", "")).strip().lower() == normalized:
            return {
                "step": waypoint["step"], "lat": float(waypoint["lat"]), "lng": float(waypoint["lng"]),
                "wind_speed_kmh": float(waypoint["wind_speed_kmh"]), "surge_height_m": float(waypoint["surge_height_m"]),
                "rainfall_24h_mm": float(waypoint.get("rainfall_24h_mm", 0)), "timestamp": waypoint["timestamp"],
            }
    valid = ", ".join(str(item.get("step")) for item in track_waypoints)
    raise ValueError(f"Unknown timeline step '{timeline_step}'. Valid values: {valid}")
