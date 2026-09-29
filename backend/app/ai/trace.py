"""In-memory ring buffer of AI calls: the data behind the UI's "AI trace" panel.

Judges (and officers) can see exactly what Gemini was asked, which tools it called, how long it took and whether
the output passed validation. No API keys or raw prompts containing secrets are stored.
"""
from __future__ import annotations

import itertools
import threading
import time
from collections import deque

_LOCK = threading.Lock()
_ITEMS: deque[dict] = deque(maxlen=300)
_COUNTER = itertools.count(1)


def record(**entry) -> dict:
    with _LOCK:
        entry = {"id": next(_COUNTER), "ts": time.time(), **entry}
        _ITEMS.append(entry)
        return entry


def recent(n: int = 50, purpose: str | None = None) -> list[dict]:
    with _LOCK:
        items = [e for e in _ITEMS if purpose is None or e.get("purpose") == purpose]
    return items[-n:][::-1]


def update(entry_id: int, **fields) -> None:
    with _LOCK:
        for e in _ITEMS:
            if e["id"] == entry_id:
                e.update(fields)
                return
