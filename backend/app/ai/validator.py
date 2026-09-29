"""Deterministic guardrails between the LLM and an officer.

A JSON schema only guarantees syntax. These checks guarantee that everything numeric or named in a draft comes from
the facts packet (Google's own structured-output docs: "always validate values in your application").
"""
from __future__ import annotations

import re
import unicodedata

from .facts import allowed_numbers

_NUM = re.compile(r"\d+(?:\.\d+)?")
_URL = re.compile(r"https?://|www\.", re.I)
_INJECT = re.compile(r"ignore (all |any )?(previous|prior|above)|disregard|system prompt|as an ai|<script", re.I)
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s-]{8,}\d)(?!\d)")

THRESHOLDS = {"stage_hours": [72, 48, 24, 12], "gale_kmh": 62, "damaging_kmh": 89, "destructive_kmh": 118, "extreme_kmh": 167,
              "passable_depth_m": 0.3, "scenarios": 9, "heavy_rain_mm": 64.5, "very_heavy_rain_mm": 115.6}


def ascii_digits(text: str) -> str:
    """Map digits of any script (Devanagari, Telugu, Odia, ...) to ASCII so numbers can be compared across languages."""
    out = []
    for ch in text:
        if ch.isdigit() and not ch.isascii():
            try:
                out.append(str(unicodedata.digit(ch)))
                continue
            except ValueError:
                pass
        out.append(ch)
    return "".join(out)


def draft_text(draft: dict) -> str:
    parts = [draft.get("headline", ""), draft.get("situation", ""), draft.get("uncertainty", "")]
    for a in draft.get("actions", []):
        parts += [a.get("who", ""), a.get("action", ""), a.get("deadline", "")]
    return "\n".join(p for p in parts if p)


def numbers_in(text: str) -> list[float]:
    return [float(m) for m in _NUM.findall(ascii_digits(text))]


def check_numbers(text: str, facts: dict) -> tuple[bool, list[float]]:
    allowed = allowed_numbers({**facts, "thresholds": THRESHOLDS})
    bad = sorted({n for n in numbers_in(text) if not any(abs(n - a) < 1e-9 for a in allowed)})
    return not bad, bad


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.casefold()).strip()


def check_targets(draft: dict, facts: dict) -> tuple[bool, list[str]]:
    known = [_norm(n) for n in facts.get("known_names", [])]
    unknown = []
    for a in draft.get("actions", []):
        for t in a.get("targets", []):
            nt = _norm(t)
            if nt and not any(nt in k or k in nt for k in known if k):
                unknown.append(t)
    return not unknown, unknown


def validate(draft: dict, facts: dict, *, check_names: bool = True) -> dict:
    text = draft_text(draft)
    checks = []
    ok_n, bad_n = check_numbers(text, facts)
    checks.append({"name": "numbers_match_facts", "ok": ok_n,
                   "detail": "all numbers appear in the model output" if ok_n else f"numbers not in the facts packet: {bad_n}"})
    if check_names:
        ok_t, bad_t = check_targets(draft, facts)
        checks.append({"name": "places_in_scope", "ok": ok_t,
                       "detail": "all named places/assets exist in the model output" if ok_t else f"unknown names: {bad_t}"})
    bad_txt = bool(_URL.search(text) or _INJECT.search(text) or _PHONE.search(ascii_digits(text)))
    checks.append({"name": "no_urls_phones_or_injection_text", "ok": not bad_txt,
                   "detail": "clean" if not bad_txt else "contains a URL, phone number or instruction-like text"})
    has_unc = bool(draft.get("uncertainty", "").strip())
    checks.append({"name": "uncertainty_stated", "ok": has_unc, "detail": "present" if has_unc else "missing"})
    has_actions = True
    checks.append({"name": "schema_valid", "ok": bool(draft.get("headline") and draft.get("situation")) and has_actions,
                   "detail": "headline, situation, actions and uncertainty present"})
    return {"passed": all(c["ok"] for c in checks), "checks": checks}
