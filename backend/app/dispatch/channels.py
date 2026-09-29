"""Delivery channels. Real where feasible (Telegram bot, webhook); everything else is explicitly SIMULATED.

Real:       Telegram Bot API (message + CAP file + inline "Acknowledge" button = a genuine delivery receipt), webhook POST.
Simulated:  bulk SMS (needs TRAI DLT-registered header/templates via an SDMA gateway), WhatsApp Business (approved templates),
            Cell Broadcast and SACHET publishing (government only - we output a CAP file and a recommended polygon).
"""
from __future__ import annotations

import html
import json
import os

import httpx

from ..config import settings
from ..dispatch import cap as capmod

EMOJI = {"green": "\U0001F7E2", "watch": "\U0001F535", "yellow": "\U0001F7E1", "orange": "\U0001F7E0", "red": "\U0001F534"}
API = "https://api.telegram.org/bot{token}/{method}"


def telegram_configured() -> bool:
    return bool(settings().telegram_bot_token and settings().telegram_chat_id)


def _chat_for(role: str) -> str | None:
    return os.getenv(f"TELEGRAM_CHAT_{role.upper()}") or settings().telegram_chat_id


def _tg(method: str, **payload) -> dict:
    url = API.format(token=settings().telegram_bot_token, method=method)
    with httpx.Client(timeout=20) as c:
        r = c.post(url, json=payload) if "document" not in payload else None
        if r is None:
            raise RuntimeError("use _tg_document for files")
        data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data.get('description')}")
    return data["result"]


def format_message(adv: dict, sim_meta: dict) -> str:
    text = adv["localized"] if adv.get("localized") and adv["localized"].get("headline") and adv["language"] != "English" else adv["english"]
    tier = adv["tier"]
    lines = [f"{EMOJI.get(tier['colour'], '')} <b>{html.escape(tier['name'])} - {html.escape(sim_meta['storm']['name'])}</b>",
             f"<i>{html.escape(adv['role'].replace('_', ' '))} - {html.escape(adv['language'])} - EXERCISE / decision support</i>", "",
             f"<b>{html.escape(text['headline'])}</b>"]
    if text.get("situation"):
        lines.append(html.escape(text["situation"]))
    if text.get("actions"):
        lines += ["", "<b>Actions</b>"] + [f"- {html.escape(a['who'])}: {html.escape(a['action'])} (by {html.escape(a['deadline'])})" for a in text["actions"]]
    if text.get("uncertainty"):
        lines += ["", f"<i>{html.escape(text['uncertainty'])}</i>"]
    lines += ["", "<i>Not an official warning. Follow IMD and your district administration.</i>"]
    return "\n".join(lines)[:4000]


def send_telegram(adv: dict, sim_meta: dict, cap_xml: str) -> dict:
    if not telegram_configured():
        return {"channel": "telegram", "status": "simulated", "detail": "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured - message shown as it would be sent"}
    chat = _chat_for(adv["role"])
    try:
        msg = _tg("sendMessage", chat_id=chat, text=format_message(adv, sim_meta), parse_mode="HTML",
                  reply_markup={"inline_keyboard": [[{"text": "Acknowledge receipt", "callback_data": f"ack:{adv['id']}"}]]})
        url = API.format(token=settings().telegram_bot_token, method="sendDocument")
        with httpx.Client(timeout=30) as c:
            c.post(url, data={"chat_id": chat, "caption": f"CAP 1.2 (Exercise/Restricted) - {adv['id']}"},
                   files={"document": (f"CS-{adv['id']}.cap.xml", cap_xml.encode(), "application/xml")})
        return {"channel": "telegram", "status": "sent", "detail": f"chat {chat}", "message_id": msg.get("message_id")}
    except Exception as exc:  # noqa: BLE001
        return {"channel": "telegram", "status": "failed", "detail": str(exc)[:200]}


def send_webhook(adv: dict, sim_meta: dict, cap_xml: str, default_url: str | None) -> dict:
    url = settings().dispatch_webhook_url or default_url
    if not url:
        return {"channel": "webhook", "status": "simulated", "detail": "no DISPATCH_WEBHOOK_URL"}
    body = {"advisory_id": adv["id"], "tier": adv["tier"]["name"], "role": adv["role"], "language": adv["language"],
            "storm": sim_meta["storm"]["name"], "cap_xml": cap_xml, "facts_sha256": adv["facts_sha256"]}
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(url, json=body)
        return {"channel": "webhook", "status": "sent" if r.status_code < 300 else "failed", "detail": f"POST {url} -> HTTP {r.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {"channel": "webhook", "status": "failed", "detail": str(exc)[:200]}


SIMULATED = [
    {"channel": "sms", "status": "simulated", "detail": "Bulk SMS in India needs TRAI DLT-registered sender header and content templates via an SDMA gateway - not possible in a prototype"},
    {"channel": "cell_broadcast", "status": "simulated", "detail": "Government-only (DoT/C-DOT via SACHET). We output a CAP file with a recommended polygon; an SDMA originator would publish it"},
]


def answer_callback(callback_id: str, text: str) -> None:
    if settings().telegram_bot_token:
        try:
            _tg("answerCallbackQuery", callback_query_id=callback_id, text=text)
        except Exception:  # noqa: BLE001
            pass


def set_webhook(public_url: str) -> dict:
    return _tg("setWebhook", url=public_url.rstrip("/") + "/api/telegram/webhook", secret_token=settings().telegram_webhook_secret,
               allowed_updates=["callback_query"])


def poll_updates(offset: int | None) -> tuple[list[dict], int | None]:
    params = {"timeout": 0, "allowed_updates": ["callback_query"]}
    if offset:
        params["offset"] = offset
    res = _tg("getUpdates", **params)
    nxt = (max(u["update_id"] for u in res) + 1) if res else offset
    return res, nxt


def cap_ok(xml: str) -> list[str]:
    return capmod.check_cap(xml)


__all__ = ["send_telegram", "send_webhook", "SIMULATED", "telegram_configured", "format_message", "json"]
