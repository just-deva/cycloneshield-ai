"""Derive the per-coast surge multiplier k from ONE observed event and print an in-sample fit table.

    python scripts/calibrate.py IN-AP

k multiplies (inverse barometer + wind set-up) in app/hazard/surge.py. It absorbs everything the screening
model omits (wave set-up, shelf funnelling, non-steady effects). With n = 1 event per coast this is a
calibration, NOT a validation: the in-sample error is zero by construction and the product says so. The
honest read-out is the range of surge across sectors and against the observation window.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import engine  # noqa: E402
from app.config import get_tenant  # noqa: E402

if __name__ == "__main__":
    tid = sys.argv[1] if len(sys.argv) > 1 else "IN-AP"
    t = get_tenant(tid)
    if not t.calibration:
        sys.exit(f"{tid}: no calibration event configured (tenant is uncalibrated)")
    ctx = engine.get_context(tid)
    for s in ctx.sectors:                      # evaluate with k = 1 so the raw physics is visible
        s["shelf"] = type(s["shelf"])(**{**s["shelf"].__dict__, "k": 1.0})
    r = engine.simulate(tid, t.calibration["storm"], ensemble=False, tide_m=t.tide_default_m)
    lo, hi = t.calibration["observed_surge_m"]
    mid = (lo + hi) / 2
    print(f"{tid} calibration storm {t.calibration['storm']}  observed {lo}-{hi} m at {t.calibration['where']}")
    print(f"{'sector':16s} {'raw surge m':>12s} {'k to hit mid':>13s} {'k range':>14s}")
    for s in r["sectors"]:
        raw = s["surge_m"]
        if raw > 0:
            print(f"{s['id']:16s} {raw:12.2f} {mid / raw:13.2f} {lo / raw:7.2f}-{hi / raw:.2f}")
