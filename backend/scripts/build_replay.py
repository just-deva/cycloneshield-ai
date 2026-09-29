"""Build the bundled replay library from JTWC best-track (b-deck) files.

Source: UCAR RAL open mirror of JTWC best tracks
        https://hurricanes.ral.ucar.edu/repository/data/bdecks_open/
Run once (needs network); the resulting JSON files are committed so the demo never
depends on a live feed:

    python scripts/build_replay.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storms.atcf import storm_from_bdeck  # noqa: E402

BASE = "https://hurricanes.ral.ucar.edu/repository/data/bdecks_open"
UA = {"User-Agent": "CycloneShieldAI/0.1 (hackathon; contact divyavdarshini@gmail.com)"}
OUT = ROOT / "data" / "storms"

# reference observations are used ONLY for calibration/validation displays and carry their
# confidence + source; nothing here is fed to the LLM as ground truth for a live event.
CATALOG = [
    dict(id="hudhud-2014", basin="io", num="03", year=2014, name="Hudhud",
         summary="Very Severe Cyclonic Storm that made landfall at Visakhapatnam on 12 Oct 2014.",
         reference={"observed_surge_m": [1.2, 1.4], "where": "Visakhapatnam tide gauge",
                    "note": "Max surge 1.4 m at the tide gauge off Vizag; peak about 1.2 m above astronomical tide (IMD RSMC report).",
                    "url": "https://rsmcnewdelhi.imd.gov.in/uploads/report/26/26_fac6af_hud.pdf",
                    "confidence": "medium-high"}),
    dict(id="phailin-2013", basin="io", num="02", year=2013, name="Phailin",
         summary="Very Severe Cyclonic Storm; landfall near Gopalpur, Odisha, on 12 Oct 2013 (about 1 million evacuated).",
         reference={"observed_surge_m": [2.0, 2.5], "where": "near Gopalpur",
                    "note": "2-2.5 m above astronomical tide near landfall; >3 m reported in parts (NIDM lessons-learnt).",
                    "url": "https://nidm.gov.in/pdf/pubs/proc%20phailin-14.pdf", "confidence": "medium"}),
    dict(id="fani-2019", basin="io", num="01", year=2019, name="Fani",
         summary="Extremely Severe Cyclonic Storm; first land contact near Puri, Odisha, on 3 May 2019.",
         reference={"observed_surge_m": [1.2, 1.8], "where": "Puri coast",
                    "note": "About 1.5 m reported; INCOIS guidance days earlier suggested up to ~4 m, so forecast-vs-observed gaps of ~2 m are normal.",
                    "url": "https://floodlist.com/asia/india-bangladesh-tropical-cyclone-fani-may-2019", "confidence": "medium",
                    "damage_reports": "Media-reported (unverified): ~1.56 lakh electric poles and >10,000 distribution transformers damaged in Odisha."}),
    dict(id="amphan-2020", basin="io", num="01", year=2020, name="Amphan",
         summary="Super Cyclonic Storm; landfall in the Sundarbans (West Bengal) on 20 May 2020.",
         reference={"observed_surge_m": [4.0, 5.0], "where": "Sundarbans",
                    "note": "IMD warned of 4-5 m above astronomical tide; about 5 m reported in media (low-medium confidence).",
                    "url": "https://weather.com/storms/hurricane/news/2020-05-16-tropical-cyclone-one-amphan-bay-of-bengal-india-bangladesh",
                    "confidence": "low-medium"}),
    dict(id="michaung-2023", basin="io", num="08", year=2023, name="Michaung",
         summary="Severe Cyclonic Storm; rainfall-dominated impact on Chennai and coastal Andhra Pradesh, Dec 2023.",
         reference={"observed_rain_mm_24h": 196, "where": "Meenambakkam (Chennai)",
                    "note": "196 mm in 24 h to 05:30 IST on 4 Dec 2023 (IMD press release).",
                    "url": "https://internal.imd.gov.in/press_release/20231204_pr_2671.pdf", "confidence": "medium"}),
    dict(id="montha-2025", basin="io", num="03", year=2025, name="Montha",
         summary="Severe Cyclonic Storm; landfall process near Kakinada, Andhra Pradesh, on the evening of 28 Oct 2025.",
         reference={"note": "Damage reported in Srikakulam, Vizianagaram, Visakhapatnam, Anakapalle, Konaseema and Kakinada; the exact landfall time (17:30 vs 19:00 IST) and the 76,000-sheltered figure are unverified.",
                    "confidence": "medium"}),
    dict(id="one-26", basin="io", num="01", year=2026, name="ONE-26",
         summary="Bay of Bengal depression (JTWC 01B), 22-24 Sep 2026, crossing near Kalingapatnam - weak (35-45 kt); a last-week live-data example, not a damage case.",
         reference={"note": "IMD handled it as a depression / deep depression; wind damage is negligible at this intensity.", "confidence": "medium"}),
    dict(id="yagi-2024", basin="wp", num="12", year=2024, name="Yagi",
         summary="Typhoon Yagi (Sep 2024) - West Pacific system that hit northern Vietnam; used to show the pipeline is basin-agnostic.",
         reference={"note": "Cross-border demonstration only; no calibration data attached.", "confidence": "n/a"}),
]


def fetch(url: str) -> str:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for c in CATALOG:
        url = f"{BASE}/{c['year']}/b{c['basin']}{c['num']}{c['year']}.dat"
        text = fetch(url)
        storm = storm_from_bdeck(
            text, storm_id=c["id"], season=c["year"], basin=c["basin"].upper(),
            source=f"JTWC best track via UCAR RAL ({url})", summary=c["summary"],
            reference=c["reference"], fallback_name=c["name"],
        )
        (OUT / f"{c['id']}.json").write_text(storm.model_dump_json(indent=1), encoding="utf-8")
        f0, f1 = storm.fixes[0], storm.fixes[-1]
        index.append({"id": storm.id, "name": storm.name, "basin": storm.basin, "season": storm.season,
                      "peak_kt_1min": storm.peak_kt(), "start": f0.t.isoformat(), "end": f1.t.isoformat(),
                      "n_fixes": len(storm.fixes), "summary": storm.summary})
        print(f"{storm.id:14s} {len(storm.fixes):3d} fixes  peak {storm.peak_kt():.0f} kt  {f0.t:%Y-%m-%d} -> {f1.t:%Y-%m-%d}")
    (OUT / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
