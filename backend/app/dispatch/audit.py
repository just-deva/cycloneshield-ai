"""Append-only, hash-chained audit log.

Each entry commits to the previous entry's hash, so editing or deleting any earlier entry breaks every later hash
and `verify()` reports where. This is *tamper-evident* only against edits that are not also re-chained: for
stronger guarantees anchor the chain head somewhere the writer cannot rewrite (e.g. a retention-locked GCS bucket)
and sign entries with Cloud KMS. We therefore call it an "append-only hash-chained audit log", never a blockchain
or "tamper-proof".
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings

GENESIS = "0" * 64
_LOCK = threading.Lock()


def _path() -> Path:
    p = settings().state_dir
    p.mkdir(parents=True, exist_ok=True)
    return p / "audit.jsonl"


def canonical(entry: dict) -> bytes:
    return json.dumps({k: v for k, v in entry.items() if k != "entry_hash"}, sort_keys=True, separators=(",", ":"), default=str).encode()


def payload_hash(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def read_all() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def append(actor: str, action: str, advisory_id: str | None = None, payload=None) -> dict:
    with _LOCK:
        entries = read_all()
        prev = entries[-1]["entry_hash"] if entries else GENESIS
        entry = {"seq": len(entries) + 1, "ts": datetime.now(timezone.utc).isoformat(), "actor": actor, "action": action,
                 "advisory_id": advisory_id, "payload_sha256": payload_hash(payload) if payload is not None else None, "prev_hash": prev}
        entry["entry_hash"] = hashlib.sha256(canonical(entry)).hexdigest()
        with _path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
        return entry


def verify() -> dict:
    entries = read_all()
    prev = GENESIS
    for e in entries:
        if e["prev_hash"] != prev:
            return {"ok": False, "entries": len(entries), "broken_at": e["seq"], "reason": "prev_hash does not match the previous entry"}
        if hashlib.sha256(canonical(e)).hexdigest() != e["entry_hash"]:
            return {"ok": False, "entries": len(entries), "broken_at": e["seq"], "reason": "entry content was modified"}
        prev = e["entry_hash"]
    return {"ok": True, "entries": len(entries), "head": prev, "broken_at": None}


def recent(limit: int = 50) -> list[dict]:
    return read_all()[-limit:][::-1]
