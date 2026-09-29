"""Extract critical-infrastructure exposure layers from OpenStreetMap for a tenant AOI.

OFFLINE step (the app never calls Overpass at request time: a 25 km query took ~98 s in our probe and
statewide queries fail). Output is compact GeoJSON under data/exposure/<tenant>/.

    python scripts/fetch_osm.py IN-AP            # one tenant
    python scripts/fetch_osm.py                   # all tenants

Data (c) OpenStreetMap contributors, ODbL. OSM covers high-voltage grid, arterial roads and urban
hospitals reasonably; it is sparse for distribution poles and has almost no designated cyclone shelters,
so schools/community halls are labelled "candidate shelters" in the product.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_tenant, tenants  # noqa: E402

MIRRORS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
UA = "CycloneShieldAI/0.1 (hackathon prototype; contact divyavdarshini@gmail.com)"

KEEP = ("name", "name:en", "amenity", "healthcare", "emergency", "power", "voltage", "operator", "highway", "bridge",
        "lanes", "ref", "oneway", "place", "population", "beds", "capacity", "building", "substation", "man_made")


def layers(b: str) -> dict[str, tuple[str, str]]:
    """layer -> (overpass body, output mode)."""
    return {
        "hospitals": (f'(nwr["amenity"="hospital"]({b});nwr["healthcare"="hospital"]({b});nwr["amenity"="clinic"]({b}););', "center"),
        "substations": (f'(nwr["power"="substation"]({b});nwr["power"="plant"]({b}););', "center"),
        "power_lines": (f'way["power"="line"]({b});', "geom"),
        "power_minor": (f'way["power"="minor_line"]({b});', "geom"),
        "roads": (f'way["highway"~"^(motorway|trunk|primary|secondary|tertiary)(_link)?$"]({b});', "geom"),
        "shelters": (f'(nwr["amenity"~"^(shelter|school|college|community_centre|townhall)$"]({b});'
                     f'nwr["emergency"="assembly_point"]({b});nwr["name"~"cyclone|shelter",i]({b}););', "center"),
        "places": (f'node["place"~"^(city|town|suburb|village|neighbourhood|quarter|hamlet)$"]["name"]({b});', "tags"),
    }


def run_query(body: str, mode: str) -> dict:
    out = {"center": "out center tags;", "geom": "out geom tags;", "tags": "out center tags;"}[mode]
    query = f"[out:json][timeout:180];{body}{out}"
    data = urllib.parse.urlencode({"data": query}).encode()
    last: Exception | None = None
    for attempt in range(3):
        url = MIRRORS[attempt % len(MIRRORS)]
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=240) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:  # noqa: BLE001 - we retry on anything
            last = exc
            print(f"    attempt {attempt + 1} failed on {url}: {exc}")
            time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"Overpass failed: {last}")


def r5(x: float) -> float:
    return round(x, 5)


def to_features(elements: list[dict]) -> list[dict]:
    feats = []
    for el in elements:
        tags = {k: el["tags"][k] for k in KEEP if k in el.get("tags", {})}
        props = {"osm": f"{el['type'][0]}{el['id']}", **tags}
        if el["type"] == "node" and "lat" in el:
            geom = {"type": "Point", "coordinates": [r5(el["lon"]), r5(el["lat"])]}
        elif "geometry" in el and len(el["geometry"]) >= 2:
            geom = {"type": "LineString", "coordinates": [[r5(p["lon"]), r5(p["lat"])] for p in el["geometry"]]}
        elif "center" in el:
            geom = {"type": "Point", "coordinates": [r5(el["center"]["lon"]), r5(el["center"]["lat"])]}
            props["from_area"] = True
        else:
            continue
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    return feats


def fetch_tenant(tenant_id: str) -> None:
    t = get_tenant(tenant_id)
    s, w, n, e = t.bbox
    bbox = f"{s},{w},{n},{e}"
    out_dir = t.dir
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"== {t.id} {t.name} bbox={bbox}")
    for name, (body, mode) in layers(bbox).items():
        target = out_dir / f"{name}.geojson"
        if target.exists() and "--force" not in sys.argv:
            print(f"  {name}: exists, skipping (use --force)")
            continue
        t0 = time.time()
        try:
            raw = run_query(body, mode)
        except RuntimeError as exc:
            print(f"  {name}: FAILED ({exc}); continuing - re-run later to fill this layer")
            continue
        feats = to_features(raw.get("elements", []))
        target.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")), encoding="utf-8")
        print(f"  {name}: {len(feats)} features in {time.time() - t0:.0f}s -> {target.stat().st_size // 1024} KB")
        time.sleep(3)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for tid in (args or list(tenants())):
        fetch_tenant(tid)
