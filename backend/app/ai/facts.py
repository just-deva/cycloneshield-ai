"""Facts packet: the ONLY source of numbers an advisory may contain.

Also holds the rule-based severity/stage logic (tiers are decided by code from IMD's 4-stage warning clock and the modelled
hazard; the LLM never sets severity) and the audience-specific views for each recipient role.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ..config import get_tenant
from ..exposure.impact import STATUS_ORDER

# IMD four-stage cyclone warning system (timings confirmed against rsmcnewdelhi.imd.gov.in/four-stage-warning.php;
# the colour mapping yellow/orange/red is from IMD practice and not re-verified in this build)
STAGES = [
    (72.0, 1, "Pre-Cyclone Watch", "watch", "T0"),
    (48.0, 2, "Cyclone Alert", "yellow", "T1"),
    (24.0, 3, "Cyclone Warning", "orange", "T2"),
    (12.0, 4, "Post-Landfall Outlook", "red", "T3"),
]
TIER_NAMES = {0: ("Monitor - no action", "green"), 1: ("Pre-Cyclone Watch", "watch"), 2: ("Cyclone Alert", "yellow"),
              3: ("Cyclone Warning", "orange"), 4: ("Post-Landfall Outlook", "red")}
FINANCE_TIER = {0: None, 1: "T0 Readiness", 2: "T1 Alert", 3: "T2 Warning", 4: "T3 Landfall"}


def stage_level(lead_h: float) -> int:
    """IMD stage reached when `lead_h` hours remain to the closest approach."""
    lvl = 0
    for threshold, level, *_ in STAGES:
        if lead_h <= threshold:
            lvl = level
    return lvl


def hazard_level(sim: dict) -> tuple[int, list[str]]:
    """0 none .. 4 extreme, from peak wind at the focus point, storm surge and rain (IMD-style thresholds)."""
    f = sim["focus"]
    w = f["peak_wind_kmh"]
    surge = max((s["surge_m"] for s in sim["sectors"]), default=0.0)
    rain = f.get("rain24_mm", 0.0)
    lvl, why = 0, []
    if w >= 167:
        lvl = 4; why.append(f"peak wind {w:.0f} km/h at {sim['tenant']['focus']['label']} (extreme, >=167)")
    elif w >= 118:
        lvl = 3; why.append(f"peak wind {w:.0f} km/h (destructive, >=118)")
    elif w >= 89:
        lvl = 2; why.append(f"peak wind {w:.0f} km/h (damaging, >=89)")
    elif w >= 62:
        lvl = 1; why.append(f"peak wind {w:.0f} km/h (gale, >=62)")
    if surge >= 1.5:
        lvl = max(lvl, 3); why.append(f"storm surge up to {surge:.1f} m")
    elif surge >= SURGE_FLOOD:
        lvl = max(lvl, 2); why.append(f"storm surge up to {surge:.1f} m")
    if rain >= 204.5:
        lvl = max(lvl, 3); why.append(f"24-h rain {rain:.0f} mm (extremely heavy)")
    elif rain >= 115.6:
        lvl = max(lvl, 2); why.append(f"24-h rain {rain:.0f} mm (very heavy)")
    elif rain >= 64.5:
        lvl = max(lvl, 1); why.append(f"24-h rain {rain:.0f} mm (heavy)")
    return lvl, why


SURGE_FLOOD = 0.3


def severity(sim: dict, lead_h: float) -> dict:
    """Advisory tier = min(IMD stage reached, modelled hazard level). Decided by rules, never by the LLM."""
    hl, why = hazard_level(sim)
    sl = stage_level(lead_h)
    lvl = min(sl, hl) if hl > 0 else 0
    name, colour = TIER_NAMES[lvl]
    return {"level": lvl, "name": name, "colour": colour, "stage_level": sl, "hazard_level": hl, "hazard_reasons": why,
            "finance_tier": FINANCE_TIER[lvl],
            "rule": "tier = min(IMD stage reached at this lead time, modelled hazard level); a storm with no modelled hazard stays at Monitor"}


def tz(tenant_id: str) -> timezone:
    return timezone(timedelta(hours=get_tenant(tenant_id).utc_offset_hours))


def clock(sim: dict, rel_h: float | None) -> str | None:
    if rel_h is None:
        return None
    t0 = datetime.fromisoformat(sim["t0"])
    t = (t0 + timedelta(hours=rel_h)).astimezone(tz(sim["tenant"]["id"]))
    return t.strftime("%a %d %b %H:%M ") + get_tenant(sim["tenant"]["id"]).tz_label


def _rank(a: dict):
    return (-STATUS_ORDER[a["status"]], -a["hazard_score"], a["first_impact_h"] if a["first_impact_h"] is not None else 99)


def _asset_view(sim: dict, a: dict) -> dict:
    v = {"name": a["name"], "status": a["status"].replace("_", " "), "why": a["reasons"][:3],
         "peak_wind_kmh": int(a["peak_wind_kmh"]), "surge_depth_m": a["surge_depth_m"],
         "first_impact": clock(sim, a["first_impact_h"])}
    if "scenario_hits" in a:
        v["hit_in_scenarios"] = f"{a['scenario_hits']} of 9"
    return v


def top_assets(sim: dict, kind: str, n: int, min_status: str = "watch") -> list[dict]:
    items = [a for a in sim["assets"] if a["kind"] == kind and STATUS_ORDER[a["status"]] >= STATUS_ORDER[min_status]]
    items.sort(key=_rank)
    named = [a for a in items if "(unnamed)" not in a["name"]] or items
    return [_asset_view(sim, a) for a in named[:n]]


def build_facts(sim: dict, lead_h: float, role: str) -> dict:
    """Assemble the audience-specific facts packet. Every number here may appear in an advisory; nothing else may."""
    ten = sim["tenant"]
    sev = severity(sim, lead_h)
    view_rel = -lead_h
    timeline = sim["timeline"]
    gale = next((c for c in timeline if c["focus_wind_kmh"] >= 62), None)
    routes = sim["evacuation"]["routes"]
    depart = [r["depart_by_h"] for r in routes if r.get("depart_by_h") is not None]
    facts: dict = {
        "event": {"name": sim["storm"]["name"], "basin": sim["storm"]["basin"], "kind": sim["storm"]["kind"],
                  "data_source": sim["storm"]["source"], "wind_basis": f"{sim['storm']['wind_avg_period_min']}-minute sustained",
                  "official_authority": get_tenant(ten["id"]).authority["forecaster"],
                  "is_replay": sim["storm"]["kind"] in ("replay", "scenario")},
        "place": {"district": ten["name"], "focus_point": ten["focus"]["label"]},
        "timing": {"as_of": clock(sim, view_rel), "closest_approach": clock(sim, 0.0), "lead_time_hours": lead_h,
                   "gale_onset_at_focus": clock(sim, gale["h"] if gale else None),
                   "closest_approach_km": sim["closest_approach_km"]},
        "warning_stage": {"tier": sev["name"], "colour": sev["colour"], "rule": sev["rule"]},
        "hazard": {"peak_wind_kmh": int(sim["focus"]["peak_wind_kmh"]), "category": sim["focus"]["category"],
                   "peak_wind_time": clock(sim, sim["focus"]["peak_h"]), "rain_24h_mm": int(sim["focus"].get("rain24_mm", 0)),
                   "rain_class": sim["focus"].get("rain_class", ""), "flooded_area_km2": sim["flooded_km2"],
                   "surge_by_sector_m": [{"sector": s["id"], "low": s.get("surge_min_m", s["surge_m"]),
                                          "high": s.get("surge_max_m", s["surge_m"]), "central": s["surge_m"],
                                          "peak_time": clock(sim, s["peak_h"])} for s in sim["sectors"]],
                   "why_this_tier": sev["hazard_reasons"]},
        "official_surge_guidance": sim.get("official_surge"),
        "uncertainty": {"method": "9 what-if scenarios: track 40 km left/right and intensity 10 kt weaker/stronger",
                        "note": "surge figures are screening-level ranges, not an official forecast; official surge guidance comes from IMD/INCOIS",
                        "wind_note": "winds are on the storm source's own averaging basis (see wind_basis)"},
    }
    summ = sim["summary"]["by_kind"]
    facts["counts"] = {k: {s: v[s] for s in ("total", "critical", "at_risk", "watch")} for k, v in summ.items()}
    role_view: dict = {}
    if role in ("district_collector", "hospital"):
        role_view["hospitals_most_exposed"] = top_assets(sim, "hospital", 6 if role == "hospital" else 4)
    if role in ("district_collector", "power"):
        role_view["substations_most_exposed"] = top_assets(sim, "substation", 6 if role == "power" else 4)
        pl = sim["power_lines"]
        role_view["power_lines"] = {"total_km": pl["total_km"], "km_in_damaging_wind_89": pl["damaging_89"],
                                    "km_in_destructive_wind_118": pl["destructive_118"], "km_flooded": pl["flooded_km"]}
    if role in ("district_collector", "roads"):
        role_view["roads_affected"] = [{"road": r["name"], "status": r["status"].replace("_", " "), "km": r["km_affected"],
                                        "max_depth_m": r["max_depth_m"], "first_impact": clock(sim, r["first_impact_h"]),
                                        "cause": r["cause"]} for r in sim["roads"][:8] if r["status"] != "watch"]
        role_view["arterial_road_km_affected"] = sim["road_summary"]["arterial_km_affected"]
    if role in ("district_collector", "shelter"):
        shs = [a for a in sim["assets"] if a["kind"] == "shelter"]
        des = [a["name"] for a in shs if a["props"].get("designated")][:5]
        role_view["shelters"] = {"usable": sim["summary"]["shelters_usable"], "total_candidates": sim["summary"]["shelters_total"],
                                 "designated_named": des,
                                 "note": "most are OSM schools/community halls flagged as CANDIDATE shelters; designated cyclone shelters need the state list"}
        es = sim["evacuation"]["summary"]
        role_view["evacuation"] = {"origins_checked": es.get("origins"), "with_safe_route": es.get("routed"),
                                   "stranded_places": es.get("stranded", [])[:8],
                                   "latest_safe_departure": clock(sim, min(depart) if depart else None),
                                   "example_routes": [{"from": r["origin"], "to": r["shelter"], "minutes": r["minutes"],
                                                       "depart_by": clock(sim, r.get("depart_by_h"))} for r in routes if r["status"] == "route"][:4]}
    if role == "fisheries":
        role_view["sea_state"] = {"peak_onshore_wind_ms": max((s["onshore_ms_peak"] for s in sim["sectors"]), default=0),
                                  "surge_max_m": max((s.get("surge_max_m", s["surge_m"]) for s in sim["sectors"]), default=0),
                                  "gale_onset_at_focus": clock(sim, gale["h"] if gale else None)}
    facts["audience"] = {"role": role, "view": role_view}
    facts["known_names"] = _names(sim)
    return facts


def _names(sim: dict) -> list[str]:
    names = {sim["tenant"]["name"], sim["tenant"]["focus"]["label"], sim["storm"]["name"]}
    names.update(a["name"] for a in sim["assets"] if a["status"] != "ok")
    names.update(r["name"] for r in sim["roads"])
    names.update(r["origin"] for r in sim["evacuation"]["routes"])
    names.update(r.get("shelter", "") for r in sim["evacuation"]["routes"])
    names.update(s["id"] for s in sim["sectors"])
    return sorted(n for n in names if n)


_NUM = re.compile(r"\d+(?:\.\d+)?")


def _walk(x, acc: set[float]) -> None:
    if isinstance(x, bool):
        return
    if isinstance(x, (int, float)):
        acc.add(float(x))
    elif isinstance(x, str):
        for m in _NUM.findall(x):
            acc.add(float(m))
    elif isinstance(x, dict):
        for k, v in x.items():
            if k != "known_names":
                _walk(v, acc)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _walk(v, acc)


def allowed_numbers(facts: dict) -> set[float]:
    """Every number in the packet, plus its rounded variants (an advisory may round 206.1 to 206)."""
    base: set[float] = set()
    _walk(facts, base)
    out = set(base)
    for x in base:
        out.update({float(round(x)), round(x, 1), round(x, 2)})
    return out
