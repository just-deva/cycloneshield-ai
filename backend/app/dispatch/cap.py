"""Common Alerting Protocol (OASIS CAP 1.2) generator in the profile NDMA SACHET uses.

Profile facts (read from a live SACHET alert, 29 Sep 2026): `cap:` prefixed elements in namespace
urn:oasis:names:tc:emergency:cap:1.2, `sent` with a +05:30 offset, `language` en-IN, category Met, districts
identified by `geocode valueName="LGD District Code"`, and a "Polygon URL" parameter.

SAFETY: our output is ALWAYS status=Exercise, scope=Restricted and carries our own sender id. It is never
`Actual`/`Public` and never uses an SDMA or IMD sender - only authorised originators can publish into SACHET.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from ..config import get_tenant

NS = "urn:oasis:names:tc:emergency:cap:1.2"
ET.register_namespace("cap", NS)
SENDER = "cycloneshield-demo"

# tier level -> (responseType, urgency, severity, certainty)
TIER_MAP = {0: ("Monitor", "Future", "Minor", "Possible"), 1: ("Prepare", "Future", "Moderate", "Possible"),
            2: ("Prepare", "Expected", "Moderate", "Likely"), 3: ("Evacuate", "Expected", "Severe", "Likely"),
            4: ("Shelter", "Immediate", "Extreme", "Likely")}


def _sub(parent, tag, text=None):
    el = ET.SubElement(parent, f"{{{NS}}}{tag}")
    if text is not None:
        el.text = str(text)
    return el


def _iso(dt: datetime, offset_h: float) -> str:
    return dt.astimezone(timezone(timedelta(hours=offset_h))).isoformat(timespec="seconds")


def _polygon(bbox: list[float]) -> str:
    s, w, n, e = bbox
    pts = [(s, w), (s, e), (n, e), (n, w), (s, w)]
    return " ".join(f"{la:.5f},{lo:.5f}" for la, lo in pts)


def _info(alert, adv: dict, sim: dict, lang_locale: str, text: dict, tenant) -> None:
    lvl = adv["tier"]["level"]
    resp, urg, sev, cert = TIER_MAP[lvl]
    t0 = datetime.fromisoformat(sim["t0"])
    info = _sub(alert, "info")
    _sub(info, "language", lang_locale)
    _sub(info, "category", "Met")
    _sub(info, "event", f"Cyclone {sim['storm']['name']}")
    _sub(info, "responseType", resp)
    _sub(info, "urgency", urg)
    _sub(info, "severity", sev)
    _sub(info, "certainty", cert)
    _sub(info, "effective", _iso(datetime.now(timezone.utc), tenant.utc_offset_hours))
    _sub(info, "onset", _iso(t0 - timedelta(hours=adv["lead_h"]), tenant.utc_offset_hours))
    _sub(info, "expires", _iso(t0 + timedelta(hours=24), tenant.utc_offset_hours))
    _sub(info, "senderName", "CycloneShield AI (decision support, exercise)")
    _sub(info, "headline", text["headline"])
    _sub(info, "description", (text.get("situation") or "") + " " + (text.get("uncertainty") or ""))
    actions = text.get("actions", [])
    _sub(info, "instruction", " ".join(f"[{a['who']}] {a['action']} (by {a['deadline']})." for a in actions) or "Keep monitoring official bulletins.")
    for name, value in (("TierRule", adv["tier"]["rule"]), ("WarningTier", adv["tier"]["name"]), ("FactsSHA256", adv["facts_sha256"]),
                        ("Audience", adv["role"]), ("DataSource", sim["storm"]["source"][:120])):
        p = _sub(info, "parameter")
        _sub(p, "valueName", name)
        _sub(p, "value", value)
    area = _sub(info, "area")
    _sub(area, "areaDesc", tenant.admin_label)
    _sub(area, "polygon", _polygon(tenant.bbox))
    if tenant.lgd_district_code:
        g = _sub(area, "geocode")
        _sub(g, "valueName", "LGD District Code")
        _sub(g, "value", tenant.lgd_district_code)


def build_cap(adv: dict, sim: dict, *, msg_type: str = "Alert", references: str | None = None) -> str:
    tenant = get_tenant(sim["tenant"]["id"])
    alert = ET.Element(f"{{{NS}}}alert")
    _sub(alert, "identifier", f"CS-{adv['id']}" + ("" if msg_type == "Alert" else f"-{msg_type[:3].upper()}"))
    _sub(alert, "sender", SENDER)
    _sub(alert, "sent", _iso(datetime.now(timezone.utc), tenant.utc_offset_hours))
    _sub(alert, "status", "Exercise")
    _sub(alert, "msgType", msg_type)
    _sub(alert, "source", "CycloneShield AI")
    _sub(alert, "scope", "Restricted")
    _sub(alert, "restriction", "Authorised disaster-management recipients only")
    _sub(alert, "note", adv["disclaimer"])
    if references:
        _sub(alert, "references", references)
    _info(alert, adv, sim, "en-IN", adv["english"], tenant)
    if adv.get("localized") and adv["localized"].get("headline") and adv["language"] != "English":
        _info(alert, adv, sim, adv["locale"], adv["localized"], tenant)
    ET.indent(alert)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(alert, encoding="unicode")


def check_cap(xml: str) -> list[str]:
    """Structural checks for the safety rules and required CAP 1.2 elements. Returns a list of problems (empty = ok)."""
    root = ET.fromstring(xml.split("?>", 1)[-1])
    q = lambda t: f"{{{NS}}}{t}"  # noqa: E731
    problems = []
    for req in ("identifier", "sender", "sent", "status", "msgType", "scope"):
        if root.find(q(req)) is None:
            problems.append(f"missing required element {req}")
    if root.findtext(q("status")) != "Exercise":
        problems.append("status must be Exercise")
    if root.findtext(q("scope")) != "Restricted":
        problems.append("scope must be Restricted")
    if root.findtext(q("sender")) != SENDER:
        problems.append("sender must be our own id")
    for info in root.findall(q("info")):
        for req in ("category", "event", "urgency", "severity", "certainty"):
            if info.find(q(req)) is None:
                problems.append(f"info missing {req}")
    return problems
