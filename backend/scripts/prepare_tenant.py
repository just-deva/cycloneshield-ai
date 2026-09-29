"""Fetch/cached terrain and compute the hydrology (basins, flow accumulation) for every tenant.

    python scripts/prepare_tenant.py            # all tenants
    python scripts/prepare_tenant.py IN-OR
Outputs data/dem/<tenant>.npz and data/dem/<tenant>_hydro.npz (committed so the container needs no network).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import tenants  # noqa: E402
from app.hazard import dem as D  # noqa: E402
from app.hazard import pluvial as P  # noqa: E402

if __name__ == "__main__":
    ids = sys.argv[1:] or list(tenants())
    for tid in ids:
        t = tenants()[tid]
        t0 = time.time()
        dem = D.load_dem(t)
        h = P.load_hydro(t, dem)
        land = ~h["sea"]
        print(f"{tid}: DEM {dem.shape} cell {dem.cell_m:.0f} m | land {100 * land.mean():.0f}% | "
              f"basins {100 * h['basin'].sum() / max(land.sum(), 1):.1f}% of land | {time.time() - t0:.0f}s")
