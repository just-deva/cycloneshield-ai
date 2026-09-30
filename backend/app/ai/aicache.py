"""Persistent cache of REAL Gemini outputs, keyed by the exact facts they were written from.

Why: Gemini quota/credits can run out (free tier, prepaid credits) or a model can be overloaded exactly when someone evaluates the
prototype. Outputs that Gemini really produced for a given facts packet are stored and can be served again. This is honest because:

* the key contains the SHA-256 of the facts packet, so an entry is only ever served for IDENTICAL facts;
* every served entry is re-validated against the current facts (numbers / places / injection checks) before use;
* the UI labels it "(cached)" with the model and the date it was generated, and a button regenerates it live;
* a live Gemini call is never faked: if there is no cached entry and no working model, the labelled template is used.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ..config import DATA_DIR

DIR = DATA_DIR / "ai_cache"
PROMPT_VERSION = "v1"     # bump when prompts/schemas change so stale entries are ignored


def _path(kind: str, *parts: str) -> Path:
    h = hashlib.sha256("|".join([PROMPT_VERSION, kind, *parts]).encode()).hexdigest()[:24]
    return DIR / f"{kind}-{h}.json"


def get(kind: str, *parts: str) -> dict | None:
    p = _path(kind, *parts)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def put(kind: str, *parts: str, value: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    rec = {**value, "cached_utc": datetime.now(timezone.utc).isoformat(), "prompt_version": PROMPT_VERSION, "key_parts": list(parts)}
    _path(kind, *parts).write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")


def stats() -> dict:
    files = list(DIR.glob("*.json")) if DIR.exists() else []
    by = {}
    for f in files:
        k = f.name.split("-", 1)[0]
        by[k] = by.get(k, 0) + 1
    return {"entries": len(files), "by_kind": by}
