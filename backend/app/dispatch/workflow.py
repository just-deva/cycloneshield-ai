"""Advisory lifecycle with maker-checker approval.

DRAFT -> PENDING_APPROVAL -> APPROVED -> DISPATCHED -> (ACKED) ; any pre-dispatch state -> REJECTED ; DISPATCHED -> CANCELLED
One approver for tiers below orange; TWO distinct approvers (neither the maker) for orange/red (level >= 3), mirroring how
official alert originators work. Gemini can only DRAFT: the dispatch tool is code behind this state machine.
Every transition is written to the hash-chained audit log.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from ..ai.validator import validate
from ..config import settings
from . import audit, cap, channels

_LOCK = threading.Lock()
_ADV: dict[str, dict] = {}
_LOADED = False
DISPATCH_TIER_APPROVALS = 2   # orange / red


class WorkflowError(ValueError):
    pass


def _file():
    p = settings().state_dir
    p.mkdir(parents=True, exist_ok=True)
    return p / "advisories.json"


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    f = _file()
    if f.exists():
        try:
            _ADV.update(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    _LOADED = True


def _save() -> None:
    _file().write_text(json.dumps(_ADV, default=str), encoding="utf-8")


def sim_meta(sim: dict) -> dict:
    return {"tenant": {"id": sim["tenant"]["id"], "name": sim["tenant"]["name"]}, "t0": sim["t0"],
            "storm": {"name": sim["storm"]["name"], "source": sim["storm"]["source"]}}


def required_approvals(adv: dict) -> int:
    return DISPATCH_TIER_APPROVALS if adv["tier"]["level"] >= 3 else 1


def register(adv: dict, sim: dict, actor: str) -> dict:
    with _LOCK:
        _load()
        rec = {**adv, "status": "DRAFT", "maker": actor, "approvals": [], "history": [], "dispatch": None, "sim_meta": sim_meta(sim),
               "required_approvals": required_approvals(adv)}
        _ADV[rec["id"]] = rec
        _log(rec, actor, "draft_created", {"facts_sha256": rec["facts_sha256"], "source": rec["source"], "validation": rec["validation"]})
        _save()
        return rec


def _log(rec: dict, actor: str, action: str, payload=None) -> None:
    e = audit.append(actor, action, rec["id"], payload)
    rec["history"].append({"ts": e["ts"], "actor": actor, "action": action, "entry_hash": e["entry_hash"]})


def get(adv_id: str) -> dict:
    _load()
    if adv_id not in _ADV:
        raise KeyError(f"unknown advisory {adv_id}")
    return _ADV[adv_id]


def list_all() -> list[dict]:
    _load()
    return sorted(_ADV.values(), key=lambda a: a["created_utc"], reverse=True)


def edit(adv_id: str, actor: str, english: dict) -> dict:
    with _LOCK:
        rec = get(adv_id)
        if rec["status"] not in ("DRAFT", "PENDING_APPROVAL"):
            raise WorkflowError("only drafts can be edited")
        v = validate(english, {**rec["facts"], "known_names": []}, check_names=False)
        rec["english"] = english
        rec["validation"] = {**v, "human_edited": True}
        rec["localized"] = None if rec["language"] != "English" else rec.get("localized")
        rec["approvals"] = []
        rec["status"] = "DRAFT"
        _log(rec, actor, "edited_by_officer", {"validation_passed": v["passed"], "english": english})
        _save()
        return rec


def submit(adv_id: str, actor: str) -> dict:
    with _LOCK:
        rec = get(adv_id)
        if rec["status"] != "DRAFT":
            raise WorkflowError(f"cannot submit from {rec['status']}")
        if not rec["validation"]["passed"]:
            raise WorkflowError("validator did not pass: fix the draft before submitting")
        rec["status"] = "PENDING_APPROVAL"
        rec["maker"] = actor
        _log(rec, actor, "submitted_for_approval")
        _save()
        return rec


def approve(adv_id: str, actor: str) -> dict:
    with _LOCK:
        rec = get(adv_id)
        if rec["status"] != "PENDING_APPROVAL":
            raise WorkflowError(f"cannot approve from {rec['status']}")
        if actor == rec["maker"]:
            raise WorkflowError("maker-checker: the approver must be a different person from the maker")
        if actor in [a["actor"] for a in rec["approvals"]]:
            raise WorkflowError("this officer has already approved")
        rec["approvals"].append({"actor": actor, "ts": datetime.now(timezone.utc).isoformat()})
        _log(rec, actor, "approved", {"n": len(rec["approvals"]), "required": rec["required_approvals"]})
        if len(rec["approvals"]) >= rec["required_approvals"]:
            rec["status"] = "APPROVED"
        _save()
        return rec


def reject(adv_id: str, actor: str, reason: str = "") -> dict:
    with _LOCK:
        rec = get(adv_id)
        if rec["status"] in ("DISPATCHED", "ACKED", "CANCELLED"):
            raise WorkflowError("already dispatched")
        rec["status"] = "REJECTED"
        _log(rec, actor, "rejected", {"reason": reason})
        _save()
        return rec


def dispatch(adv_id: str, actor: str, sim: dict, default_webhook: str | None = None) -> dict:
    with _LOCK:
        rec = get(adv_id)
        if rec["status"] != "APPROVED":
            raise WorkflowError(f"cannot dispatch from {rec['status']}: approval required first")
        xml = cap.build_cap(rec, sim)
        problems = cap.check_cap(xml)
        if problems:
            raise WorkflowError("CAP safety check failed: " + "; ".join(problems))
        results = [channels.send_telegram(rec, rec["sim_meta"], xml), channels.send_webhook(rec, rec["sim_meta"], xml, default_webhook),
                   *channels.SIMULATED]
        delivered = [r for r in results if r["status"] in ("sent",)]
        rec["dispatch"] = {"ts": datetime.now(timezone.utc).isoformat(), "actor": actor, "results": results,
                           "cap_sha256": audit.payload_hash(xml), "any_real_delivery": bool(delivered)}
        rec["cap_xml"] = xml
        rec["status"] = "DISPATCHED"
        _log(rec, actor, "dispatched", {"results": [(r["channel"], r["status"]) for r in results], "cap_sha256": rec["dispatch"]["cap_sha256"]})
        _save()
        return rec


def acknowledge(adv_id: str, actor: str, via: str = "ui") -> dict:
    with _LOCK:
        rec = get(adv_id)
        if rec["status"] not in ("DISPATCHED", "ACKED"):
            raise WorkflowError("nothing to acknowledge yet")
        rec.setdefault("acks", []).append({"actor": actor, "via": via, "ts": datetime.now(timezone.utc).isoformat()})
        rec["status"] = "ACKED"
        _log(rec, actor, "acknowledged", {"via": via})
        _save()
        return rec


def cancel(adv_id: str, actor: str, sim: dict) -> dict:
    with _LOCK:
        rec = get(adv_id)
        if rec["status"] not in ("DISPATCHED", "ACKED"):
            raise WorkflowError("only dispatched advisories can be cancelled")
        xml = cap.build_cap(rec, sim, msg_type="Cancel", references=f"{cap.SENDER},CS-{rec['id']},{rec['dispatch']['ts']}")
        rec["cap_cancel_xml"] = xml
        rec["status"] = "CANCELLED"
        _log(rec, actor, "cancelled", {"cap_sha256": audit.payload_hash(xml)})
        _save()
        return rec


def public_view(rec: dict) -> dict:
    """Advisory without the bulky facts/cap payloads (list views)."""
    return {k: v for k, v in rec.items() if k not in ("facts", "cap_xml", "cap_cancel_xml")}
