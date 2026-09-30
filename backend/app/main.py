"""CycloneShield AI - FastAPI application (API + static single-page UI on one Cloud Run service)."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import engine
from .ai import bulletin as bulletin_mod
from .config import get_tenant, load_replay, settings, storm_index, tenants
from .exposure.impact import METHODOLOGY
from .routes import router as ops_router
from .routes import start_telegram_polling

log = logging.getLogger("cycloneshield")
STATIC = Path(__file__).resolve().parent / "static"

@asynccontextmanager
async def lifespan(_: FastAPI):
    from .hazard import gee
    gee.warm()
    _warm()
    start_telegram_polling()
    yield


app = FastAPI(title="CycloneShield AI", version="1.0.0", lifespan=lifespan,
              description="Asset-level cyclone impact forecasting and advisory dispatch for disaster-management authorities. "
                          "Decision support only: official warnings are issued by IMD and public alerts by NDMA/SDMAs.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


class SimulateRequest(BaseModel):
    tenant_id: str
    storm_id: str
    cross_track_km: float = Field(default=0.0, ge=-150, le=150)
    delta_kt: float = Field(default=0.0, ge=-40, le=60)
    tide_m: float | None = Field(default=None, ge=-1.0, le=3.0)
    ensemble: bool = True


def _tenant_or_404(tid: str):
    try:
        return get_tenant(tid)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


def _ee_available() -> bool:
    from .hazard import gee
    return bool(gee.status()["available"]) if settings().ee_enabled else False


@app.get("/api/health")
def health() -> dict:
    s = settings()
    return {"status": "online", "system": "CycloneShield AI", "version": app.version,
            "features": {"gemini": bool(s.gemini_api_key), "gemini_model": s.gemini_model,
                         "earth_engine": _ee_available(), "telegram": bool(s.telegram_bot_token),
                         "webhook": bool(s.dispatch_webhook_url)},
            "tenants": list(tenants()), "replay_storms": len(storm_index())}


@app.get("/api/tenants")
def list_tenants() -> list[dict]:
    out = []
    for t in tenants().values():
        out.append({"id": t.id, "name": t.name, "country": t.country, "focus": t.focus.model_dump(), "bbox": t.bbox,
                    "languages": t.languages, "replay_storms": t.replay_storms, "utc_offset_hours": t.utc_offset_hours, "tz_label": t.tz_label,
                    "sectors": [{"id": x.id, "lat": x.lat, "lon": x.lon} for x in t.sectors], "calibrated": t.calibration is not None,
                    "authority": t.authority, "recipients": [r.model_dump() for r in t.recipients],
                    "attribution": t.attribution})
    return out


@app.get("/api/storms")
def list_storms() -> list[dict]:
    return storm_index()


@app.get("/api/storms/{storm_id}")
def get_storm(storm_id: str) -> dict:
    try:
        return load_replay(storm_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/simulate")
def simulate(req: SimulateRequest) -> dict:
    _tenant_or_404(req.tenant_id)
    try:
        storm = bulletin_mod.get_storm(req.storm_id) if req.storm_id.startswith("bulletin-") else req.storm_id
        return engine.simulate(req.tenant_id, storm, cross_track_km=req.cross_track_km, delta_kt=req.delta_kt,
                               tide_m=req.tide_m, ensemble=req.ensemble)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/layers/{sim_id}/inundation.png")
def inundation_layer(sim_id: str) -> Response:
    png = engine.inundation_png(sim_id)
    if png is None:
        raise HTTPException(404, "simulation expired; run it again")
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=300"})


@app.get("/api/layers/{tenant_id}/pathways.png")
def pathways_layer(tenant_id: str) -> Response:
    _tenant_or_404(tenant_id)
    return Response(engine.pathways_png(tenant_id), media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/methodology")
def methodology() -> dict:
    return {"modules": METHODOLOGY,
            "disclaimer": DISCLAIMER}


@app.get("/api/calibration/{tenant_id}")
def calibration(tenant_id: str) -> dict:
    t = _tenant_or_404(tenant_id)
    if not t.calibration:
        return {"calibrated": False, "note": "This tenant is UNCALIBRATED: sector multipliers are 1.0 and surge should be read as indicative."}
    r = engine.simulate(tenant_id, t.calibration["storm"], ensemble=False)
    lo, hi = t.calibration["observed_surge_m"]
    rows = [{"sector": s["id"], "modelled_surge_m": s["surge_m"], "observed_low_m": lo, "observed_high_m": hi,
             "k": next(c.k for c in t.sectors if c.id == s["id"]), "shelf": s["shelf"]} for s in r["sectors"]]
    return {"calibrated": True, "storm": t.calibration["storm"], "where": t.calibration["where"],
            "observed_surge_m": [lo, hi], "sectors": rows,
            "note": "In-sample calibration on a single event (n=1): the multiplier k was fitted to the observation, so agreement is by construction. "
                    "It is NOT a validation. Shelf width/depth are hand-set."}


DISCLAIMER = ("CycloneShield AI provides decision-support advisories generated with AI from public forecasts and models. "
              "It is NOT an official warning. Official cyclone warnings are issued only by the India Meteorological Department, and public "
              "alerts only by NDMA/SDMAs through authorised channels. Estimates carry uncertainty. Always act on the latest IMD bulletin "
              "and the instructions of your district administration. Financial figures are indicative recommendations, not an insurance "
              "contract or payment instruction.")


def _warm() -> None:
    """Pre-compute the default replay of each tenant so the first click is instant."""
    def run() -> None:
        for t in tenants().values():
            try:
                if t.replay_storms:
                    engine.simulate(t.id, t.replay_storms[0], ensemble=True)
            except Exception:  # noqa: BLE001 - warm-up must never crash the service
                log.exception("warm-up failed for %s", t.id)
    threading.Thread(target=run, daemon=True).start()


@app.middleware("http")
async def _revalidate_static(request, call_next):
    """The UI ships as plain ES modules: make browsers revalidate (ETag) on every load so a redeploy is never masked by a stale cached script."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.include_router(ops_router)

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")
