"""Operational API: advisories + dispatch, finance, copilot, bulletin ingestion, audit, Telegram, trace."""
from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from . import engine, finance
from .ai import advisory as advisory_mod
from .ai import bulletin as bulletin_mod
from .ai import copilot as copilot_mod
from .ai import gemini_client as gc
from .ai import trace
from .config import settings
from .dispatch import audit, cap, channels, workflow

log = logging.getLogger("cycloneshield.routes")
router = APIRouter(prefix="/api")

MAX_UPLOAD = 15 * 1024 * 1024
ROLES = list(advisory_mod.ROLE_GUIDE)


def _sim(sim_id: str) -> dict:
    sim = engine.get_sim(sim_id)
    if sim is None:
        raise HTTPException(410, "That simulation is no longer cached - run it again.")
    return sim


def _wf(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except workflow.WorkflowError as exc:
        raise HTTPException(409, str(exc)) from exc


def _gemini(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except gc.GeminiUnavailable as exc:
        raise HTTPException(503, f"Gemini unavailable: {exc}") from exc


# ---------------- advisories ----------------
class DraftRequest(BaseModel):
    sim_id: str
    lead_h: float = Field(default=24, ge=0, le=96)
    role: str = "district_collector"
    language: str = "English"
    actor: str = "Duty officer (maker)"
    use_ai: bool = True
    refresh: bool = False          # bypass the primed AI cache and call Gemini live


class ActorRequest(BaseModel):
    actor: str = "Duty officer (maker)"
    reason: str = ""


class EditRequest(BaseModel):
    actor: str = "Duty officer (maker)"
    headline: str
    situation: str
    uncertainty: str
    actions: list[advisory_mod.Action]


@router.post("/advisories/draft")
def draft(req: DraftRequest) -> dict:
    sim = _sim(req.sim_id)
    if req.role not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    adv = _gemini(advisory_mod.draft_advisory, sim, req.lead_h, req.role, req.language, use_ai=req.use_ai, refresh=req.refresh)
    rec = workflow.register({**adv}, sim, req.actor)
    return workflow.public_view(rec)


@router.get("/advisories")
def list_advisories() -> list[dict]:
    return [workflow.public_view(a) for a in workflow.list_all()]


@router.get("/advisories/{adv_id}")
def get_advisory(adv_id: str) -> dict:
    return _wf(workflow.get, adv_id)


@router.patch("/advisories/{adv_id}")
def edit_advisory(adv_id: str, req: EditRequest) -> dict:
    return workflow.public_view(_wf(workflow.edit, adv_id, req.actor, {"headline": req.headline, "situation": req.situation,
                                                                       "uncertainty": req.uncertainty, "actions": [a.model_dump() for a in req.actions]}))


@router.post("/advisories/{adv_id}/submit")
def submit(adv_id: str, req: ActorRequest) -> dict:
    return workflow.public_view(_wf(workflow.submit, adv_id, req.actor))


@router.post("/advisories/{adv_id}/approve")
def approve(adv_id: str, req: ActorRequest) -> dict:
    return workflow.public_view(_wf(workflow.approve, adv_id, req.actor))


@router.post("/advisories/{adv_id}/reject")
def reject(adv_id: str, req: ActorRequest) -> dict:
    return workflow.public_view(_wf(workflow.reject, adv_id, req.actor, req.reason))


@router.post("/advisories/{adv_id}/dispatch")
def dispatch(adv_id: str, req: ActorRequest, request: Request) -> dict:
    rec = _wf(workflow.get, adv_id)
    sim = engine.get_sim(rec["sim_id"]) or _rebuild_sim_meta(rec)
    default_hook = str(request.base_url).rstrip("/") + "/api/mock-deoc"
    return workflow.public_view(_wf(workflow.dispatch, adv_id, req.actor, sim, default_hook))


@router.post("/advisories/{adv_id}/ack")
def ack(adv_id: str, req: ActorRequest) -> dict:
    return workflow.public_view(_wf(workflow.acknowledge, adv_id, req.actor, "ui"))


@router.post("/advisories/{adv_id}/cancel")
def cancel(adv_id: str, req: ActorRequest) -> dict:
    rec = _wf(workflow.get, adv_id)
    sim = engine.get_sim(rec["sim_id"]) or _rebuild_sim_meta(rec)
    return workflow.public_view(_wf(workflow.cancel, adv_id, req.actor, sim))


@router.get("/advisories/{adv_id}/cap.xml")
def cap_xml(adv_id: str):
    from fastapi.responses import Response
    rec = _wf(workflow.get, adv_id)
    xml = rec.get("cap_xml")
    if not xml:
        sim = engine.get_sim(rec["sim_id"]) or _rebuild_sim_meta(rec)
        xml = cap.build_cap(rec, sim)                 # preview of what would be dispatched
    return Response(xml, media_type="application/xml")


def _rebuild_sim_meta(rec: dict) -> dict:
    """If the cached simulation was evicted, CAP only needs the tenant, t0 and storm labels stored with the advisory."""
    m = rec["sim_meta"]
    return {"tenant": {"id": m["tenant"]["id"], "name": m["tenant"]["name"]}, "t0": m["t0"], "storm": m["storm"]}


# ---------------- Telegram + mock DEOC receiver ----------------
def handle_telegram_update(update: dict) -> None:
    cb = update.get("callback_query")
    if not cb:
        return
    data = cb.get("data", "")
    who = cb.get("from", {})
    if data.startswith("ack:"):
        adv_id = data.split(":", 1)[1]
        actor = "telegram:" + (who.get("username") or str(who.get("id")))
        try:
            workflow.acknowledge(adv_id, actor, via="telegram")
            channels.answer_callback(cb["id"], "Receipt acknowledged and logged.")
            log.info("telegram acknowledgement recorded for %s by %s", adv_id, actor)
        except Exception as exc:  # noqa: BLE001
            # never lose a button press silently: log it, tell the user in Telegram, and leave an audit entry
            log.warning("telegram acknowledgement for %s failed: %s", adv_id, exc)
            audit.append(actor, "telegram_ack_failed", adv_id, {"error": str(exc)[:200]})
            channels.answer_callback(cb["id"], f"Could not acknowledge: {exc}"[:150])


@router.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(request: Request) -> dict:
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != settings().telegram_webhook_secret:
        raise HTTPException(403, "bad secret token")
    handle_telegram_update(await request.json())
    return {"ok": True}


class WebhookSetup(BaseModel):
    public_url: str


@router.post("/telegram/setup")
def telegram_setup(req: WebhookSetup) -> dict:
    if not channels.telegram_configured():
        raise HTTPException(409, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured")
    return channels.set_webhook(req.public_url)


@router.get("/telegram/status")
def telegram_status() -> dict:
    return {"configured": channels.telegram_configured(), "polling": _POLLING["on"],
            "note": "Real delivery needs a bot token and chat id; otherwise dispatch is simulated and labelled."}


@router.post("/mock-deoc")
async def mock_deoc(request: Request) -> dict:
    """Demo receiver standing in for a District Emergency Operations Centre endpoint."""
    body = await request.json()
    problems = cap.check_cap(body.get("cap_xml", "<x/>")) if body.get("cap_xml") else ["no cap_xml"]
    audit.append("mock-DEOC", "cap_received", body.get("advisory_id"), {"problems": problems, "tier": body.get("tier")})
    return {"received": True, "cap_valid": not problems, "problems": problems}


_POLLING = {"on": False}


def start_telegram_polling() -> None:
    """Local/dev mode: long-poll for Acknowledge button presses when no public webhook is set."""
    import os
    if not channels.telegram_configured() or os.getenv("TELEGRAM_POLLING", "false").lower() != "true" or _POLLING["on"]:
        return
    _POLLING["on"] = True

    def loop() -> None:
        offset = None
        while True:
            try:
                updates, offset = channels.poll_updates(offset)
                for u in updates:
                    handle_telegram_update(u)
            except Exception:  # noqa: BLE001
                log.exception("telegram polling error")
            time.sleep(2)
    threading.Thread(target=loop, daemon=True).start()


# ---------------- audit / trace ----------------
@router.get("/audit")
def audit_log(limit: int = 50) -> dict:
    return {"entries": audit.recent(limit), "verify": audit.verify()}


@router.get("/audit/verify")
def audit_verify() -> dict:
    return audit.verify()


@router.get("/ai-cache")
def ai_cache_stats() -> dict:
    from .ai import aicache
    return aicache.stats()


@router.get("/trace")
def ai_trace(n: int = 40) -> list[dict]:
    return trace.recent(n)


# ---------------- Earth Engine (fails soft) ----------------
@router.get("/gee/status")
def gee_status() -> dict:
    from .hazard import gee
    return gee.status(wait=True)


@router.get("/gee/summary/{sim_id}")
def gee_summary(sim_id: str) -> dict:
    """Live GFS rain + people/buildings in the modelled flood zone, from Earth Engine. Returns available=false with the reason if EE is not connected."""
    from .config import get_tenant
    from .hazard import gee
    sim = _sim(sim_id)
    t = get_tenant(sim["tenant"]["id"])
    st = gee.status(wait=True)
    if not st["available"]:
        return {"available": False, **st}
    out: dict = {"available": True, "project": st["project"]}
    try:
        out["rain"] = gee.live_rain(t)
    except Exception as exc:  # noqa: BLE001
        out["rain_error"] = str(exc)[:200]
    try:
        ctx = engine.get_context(t.id)
        depth = engine.depth_grid_for(sim_id)
        out["exposure"] = gee.flood_exposure(t, ctx.dem, depth, sim_id) if depth is not None else {"people": 0, "buildings": 0, "note": "No flooded area in this scenario."}
    except Exception as exc:  # noqa: BLE001
        out["exposure_error"] = str(exc)[:200]
    return out


@router.get("/gee/tiles/{tenant_id}")
def gee_tiles(tenant_id: str) -> dict:
    from .config import get_tenant
    from .hazard import gee
    st = gee.status(wait=True)
    if not st["available"]:
        return {"available": False, **st}
    try:
        return {"available": True, "layers": gee.tile_layers(get_tenant(tenant_id))}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc)[:200]}


# ---------------- severity (rule-based tier for a lead time) ----------------
@router.get("/severity/{sim_id}")
def severity_at(sim_id: str, lead_h: float = 24) -> dict:
    from .ai.facts import severity
    return severity(_sim(sim_id), lead_h)


# ---------------- finance ----------------
@router.get("/finance/{sim_id}")
def finance_eval(sim_id: str, lead_h: float = 24, pool_crore: float = 10.0) -> dict:
    return finance.evaluate(_sim(sim_id), lead_h, pool_crore)


class FinanceApproval(BaseModel):
    actor: str = "Approver A"
    lead_h: float = 24
    pool_crore: float = 10.0


@router.post("/finance/{sim_id}/approve")
def finance_approve(sim_id: str, req: FinanceApproval) -> dict:
    r = finance.evaluate(_sim(sim_id), req.lead_h, req.pool_crore)
    e = audit.append(req.actor, "finance_memo_approved", None, {"memo_sha256": r["memo_sha256"], "tier": r["tier_reached"],
                                                                "release_pct": r["recommended_release_pct"], "pool_crore": req.pool_crore})
    return {"approved": True, "audit_entry": e, "note": "Recorded as a recommendation. No funds are moved by this software."}


# ---------------- copilot ----------------
class CopilotRequest(BaseModel):
    sim_id: str
    lead_h: float = 24
    question: str = Field(min_length=2, max_length=800)
    history: list[dict] = Field(default_factory=list)
    refresh: bool = False


@router.post("/copilot")
def copilot(req: CopilotRequest) -> dict:
    return _gemini(copilot_mod.ask, _sim(req.sim_id), req.lead_h, req.question, req.history, req.refresh)


# ---------------- bulletin ingestion ----------------
@router.post("/bulletin/extract")
async def bulletin_extract(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "file too large (max 15 MB)")
    mime = file.content_type or "application/pdf"
    if mime not in ("application/pdf", "image/png", "image/jpeg", "image/webp", "text/plain"):
        raise HTTPException(415, "upload a PDF, PNG, JPEG or text file")
    if mime == "text/plain":
        return _gemini(bulletin_mod.extract, None, None, data.decode("utf-8", "replace"), file.filename or "")
    return _gemini(bulletin_mod.extract, data, mime, None, file.filename or "")


class BulletinText(BaseModel):
    text: str = Field(min_length=20, max_length=60000)


@router.post("/bulletin/extract-text")
def bulletin_extract_text(req: BulletinText) -> dict:
    return _gemini(bulletin_mod.extract, None, None, req.text, "pasted text")


@router.get("/roles")
def roles() -> list[dict]:
    return [{"role": k, "audience": v} for k, v in advisory_mod.ROLE_GUIDE.items()]
