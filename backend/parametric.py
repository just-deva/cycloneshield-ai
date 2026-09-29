"""Transparent trigger evaluation with tamper-evident payload evidence."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def evaluate_parametric_payout(wind_speed_kmh: float, rainfall_24h_mm: float, surge_height_m: float) -> dict[str, Any]:
    status = "TIER_1_DISASTER_LIQUIDITY_RELEASED" if (
        rainfall_24h_mm > 150 or wind_speed_kmh > 90 or surge_height_m > 1.5
    ) else "PENDING"
    evidence = {"timestamp": datetime.now(timezone.utc).isoformat(), "district": "Visakhapatnam",
                "wind": wind_speed_kmh, "rainfall": rainfall_24h_mm, "surge": surge_height_m, "status": status}
    canonical = json.dumps(evidence, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {"status": status, "triggered": status != "PENDING", "evidence": evidence,
            "sha256": hashlib.sha256(canonical).hexdigest()}
