"""Anticipatory-finance TRIGGER MONITOR and release-recommendation memo. Simulation only - no money moves.

What real programmes do (design references, see research/06): CCRIF pays when modelled loss reaches an attachment point,
within 14 days; the IFRC / Bangladesh Red Crescent cyclone Early Action Protocol releases pre-agreed funds when a forecast
wind of >125 km/h (about a 1-in-5-year event) coincides with a lead time of ~30 h and >=25% expected household-asset damage;
India funds response from SDRF/NDRF (ex-gratia Rs 4 lakh per death under the 2022-26 MHA norms). This module shows WHEN
such a pre-agreed trigger would fire, WHICH conditions are met, and WHAT share of a pre-arranged pool would be recommended
for release - with the basis-risk caveats - and hands a human a memo to approve. The tier percentages are OUR illustrative
design choices, not sourced values, and are labelled as such.
"""
from __future__ import annotations

import hashlib
import json

from .ai.facts import clock, severity, stage_level
from .exposure.impact import emanuel_loss_ratio

# cumulative share of the pre-arranged pool recommended for release at each tier (ILLUSTRATIVE design choice)
TIERS = [
    {"tier": "T0 Readiness", "level": 1, "stage": "Pre-Cyclone Watch (>=72 h)", "cumulative_pct": 10,
     "condition": "district inside the modelled hazard footprint", "actions": "pre-position relief stock, fuel and DG sets; staff recall"},
    {"tier": "T1 Alert", "level": 2, "stage": "Cyclone Alert (>=48 h)", "cumulative_pct": 35,
     "condition": "modelled peak wind >= 89 km/h (Severe Cyclonic Storm or stronger)", "actions": "open shelters, recall fishermen, tree-cutting teams"},
    {"tier": "T2 Warning", "level": 3, "stage": "Cyclone Warning (24 h)", "cumulative_pct": 75,
     "condition": "peak wind >= 118 km/h OR surge >= 1.5 m, AND expected loss ratio >= 25%", "actions": "evacuation transport, cash to vulnerable households, hospital fuel"},
    {"tier": "T3 Landfall", "level": 4, "stage": "Post-Landfall Outlook (>=12 h)", "cumulative_pct": 100,
     "condition": "peak wind >= 167 km/h (Extremely Severe Cyclonic Storm or stronger)", "actions": "stage restoration crews; complete remaining release"},
]


def evaluate(sim: dict, lead_h: float, pool_crore: float = 10.0) -> dict:
    sev = severity(sim, lead_h)
    f = sim["focus"]
    wind = f["peak_wind_kmh"]
    surge = max((s["surge_m"] for s in sim["sectors"]), default=0.0)
    loss = emanuel_loss_ratio(wind / 3.6)
    stage = stage_level(lead_h)
    conds = {
        1: {"stage_reached": stage >= 1, "hazard": sev["hazard_level"] >= 1},
        2: {"stage_reached": stage >= 2, "hazard": wind >= 89},
        3: {"stage_reached": stage >= 3, "hazard": (wind >= 118 or surge >= 1.5) and loss >= 0.25},
        4: {"stage_reached": stage >= 4, "hazard": wind >= 167},
    }
    rows, fired = [], 0
    for t in TIERS:
        c = conds[t["level"]]
        ok = c["stage_reached"] and c["hazard"]
        fired = t["level"] if ok else fired
        rows.append({**t, "stage_reached": c["stage_reached"], "hazard_condition_met": c["hazard"], "fired": ok})
    # tiers are cumulative: a higher tier can only fire if all lower ones did
    lvl = 0
    for r in rows:
        if r["fired"] and r["level"] == lvl + 1:
            lvl = r["level"]
        else:
            r["fired"] = r["level"] <= lvl
    pct = next((t["cumulative_pct"] for t in TIERS if t["level"] == lvl), 0)
    result = {
        "sim_id": sim["sim_id"], "lead_h": lead_h, "as_of": clock(sim, -lead_h), "pool_crore_inr": pool_crore,
        "tier_reached": next((t["tier"] for t in TIERS if t["level"] == lvl), "No trigger"), "level": lvl,
        "recommended_release_pct": pct, "recommended_release_crore_inr": round(pool_crore * pct / 100.0, 2),
        "inputs": {"peak_wind_kmh": wind, "max_surge_m": surge, "expected_loss_ratio": round(loss, 3), "hazard_level": sev["hazard_level"]},
        "tiers": rows,
        "basis_risk": [
            "Triggers use a MODELLED footprint from a screening model, not a measured loss: the trigger can fire without loss, or miss loss that occurs.",
            "Expected loss ratio is the Emanuel (2011) sigmoid with a North-Indian-Ocean calibration - an aggregate expected fraction of exposed value, near zero below ~50 kt, and not calibrated for this district.",
            "Mitigation: tiers not a cliff, a small no-regret readiness tranche at 72 h, and an ex-post true-up against IMD's final best track.",
        ],
        "human_step": "A duty officer must approve this memo; nothing is transferred by this software.",
        "references": ["CCRIF payouts: https://www.ccrif.org/aboutus/ccrif-spc-payouts",
                       "IFRC/BDRCS cyclone EAP: https://www.anticipation-hub.org/Documents/EAPs/EAP_Bangladesh_Cyclone_2021BD06_MDRBD033-1.pdf",
                       "MHA SDRF/NDRF norms 2022-26: https://ndmindia.mha.gov.in/ndmi/viewUploadedDocument?uid=NEW151"],
        "illustrative": "Tier percentages and the pool are illustrative design choices for this prototype, not sourced values.",
    }
    result["memo"] = memo(sim, result)
    result["memo_sha256"] = hashlib.sha256(json.dumps({k: v for k, v in result.items() if k != "memo"}, sort_keys=True, default=str).encode()).hexdigest()
    return result


def memo(sim: dict, r: dict) -> str:
    ten = sim["tenant"]
    met = [t for t in r["tiers"] if t["fired"]]
    lines = [f"ANTICIPATORY RELEASE RECOMMENDATION (draft for approval) - EXERCISE",
             f"District: {ten['name']}   Event: {sim['storm']['name']}   As of: {r['as_of']} (lead time {r['lead_h']:g} h)",
             "",
             f"Recommendation: release {r['recommended_release_pct']}% of the pre-arranged pool = Rs {r['recommended_release_crore_inr']} crore "
             f"(pool Rs {r['pool_crore_inr']} crore, illustrative). Tier reached: {r['tier_reached']}."]
    if met:
        lines += ["", "Conditions met:"] + [f"  - {t['tier']}: {t['stage']}; {t['condition']}" for t in met]
        lines += ["", "Suggested early actions: " + "; ".join(t["actions"] for t in met[-2:])]
    else:
        lines += ["", "No trigger has fired: continue monitoring official bulletins."]
    lines += ["", "Basis risk: " + " ".join(r["basis_risk"][:1]), "This is decision support. No funds are moved by this system; an authorised officer must approve."]
    return "\n".join(lines)
