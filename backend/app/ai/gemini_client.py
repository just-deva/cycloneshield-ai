"""Thin, testable wrapper around the Gemini API (google-genai SDK).

* primary model from GEMINI_MODEL (default gemini-3.7-flash, the model the track mandates), with a fallback chain
* structured output via response_schema, tool use via automatic function calling
* thinking_level set explicitly ("low"/"medium"): Gemini 3 defaults to HIGH, which adds latency and cost
* temperature is left at the default (Gemini 3 guidance: lowering it can cause looping)
* every call is recorded in the AI trace
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from ..config import settings
from . import trace

try:  # the SDK is only needed when a key is configured
    from google import genai
    from google.genai import types
except Exception:  # noqa: BLE001
    genai = None
    types = None


class GeminiUnavailable(RuntimeError):
    pass


_COOL: dict[str, float] = {}      # model -> monotonic-ish wall time until which it is skipped


@dataclass
class GeminiResult:
    text: str = ""
    parsed: Any = None
    tool_calls: list[dict] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0
    usage: dict = field(default_factory=dict)
    trace_id: int | None = None


def available() -> bool:
    return bool(settings().gemini_api_key) and genai is not None


def _client():
    if not available():
        raise GeminiUnavailable("GEMINI_API_KEY is not configured")
    return genai.Client(api_key=settings().gemini_api_key, http_options=types.HttpOptions(timeout=45_000))


def _extract_tool_calls(resp) -> list[dict]:
    calls: list[dict] = []
    hist = getattr(resp, "automatic_function_calling_history", None) or []
    pending: dict[str, dict] = {}
    for content in hist:
        for part in getattr(content, "parts", None) or []:
            fc = getattr(part, "function_call", None)
            fr = getattr(part, "function_response", None)
            if fc is not None:
                rec = {"name": fc.name, "args": dict(fc.args or {})}
                calls.append(rec)
                pending[fc.name] = rec
            if fr is not None and fr.name in pending:
                out = fr.response
                pending[fr.name]["result_preview"] = (json.dumps(out, default=str)[:300] if out is not None else None)
    return calls


def _usage(resp) -> dict:
    u = getattr(resp, "usage_metadata", None)
    if not u:
        return {}
    return {"prompt_tokens": getattr(u, "prompt_token_count", None), "output_tokens": getattr(u, "candidates_token_count", None),
            "thinking_tokens": getattr(u, "thoughts_token_count", None)}


def generate(*, purpose: str, contents, system: str | None = None, schema: type[BaseModel] | None = None,
             tools: list | None = None, thinking: str = "low", max_tool_calls: int = 6,
             input_summary: str = "", media_high: bool = False) -> GeminiResult:
    """Call Gemini with model fallback. Raises GeminiUnavailable when no model could answer."""
    s = settings()
    client = _client()
    configured = [s.gemini_model, *[m for m in s.gemini_fallbacks if m != s.gemini_model]]
    # circuit breaker: a model that just failed with a quota/overload error is skipped for a while, so one bad minute on the
    # mandated model costs ONE slow request, not every request. If every model is cooling we try them all anyway.
    models = [m for m in configured if _COOL.get(m, 0) <= time.time()] or configured
    # gemini-3.7-flash rejects thinking_level MINIMAL (HTTP 400), so "minimal" is served as LOW
    level = {"minimal": "LOW", "low": "LOW", "medium": "MEDIUM", "high": "HIGH"}[thinking]
    last_err: Exception | None = None
    deadline = time.time() + 75          # hard overall budget per request: the UI must never hang for minutes
    entry = trace.record(purpose=purpose, status="running", input=input_summary[:400], model=None, tools=[t.__name__ for t in tools or []])
    for mi, model in enumerate(models):
        if time.time() > deadline:
            break
        cfg: dict[str, Any] = {"thinking_config": types.ThinkingConfig(thinking_level=getattr(types.ThinkingLevel, level))}
        if system:
            cfg["system_instruction"] = system
        if schema is not None:
            cfg["response_mime_type"] = "application/json"
            cfg["response_schema"] = schema
        if tools:
            cfg["tools"] = tools
            cfg["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(maximum_remote_calls=max_tool_calls)
        if media_high and hasattr(types, "MediaResolution"):
            cfg["media_resolution"] = types.MediaResolution.MEDIA_RESOLUTION_HIGH
        # The mandated model gets more patience (new models see demand spikes: 503 "high demand", 429 on free-tier quota)
        # before we fall back; fallback models get two tries.
        for attempt in range(3 if mi == 0 else 2):
            if time.time() > deadline:
                break
            t0 = time.time()
            try:
                resp = client.models.generate_content(model=model, contents=contents, config=types.GenerateContentConfig(**cfg))
                text = (resp.text or "") if hasattr(resp, "text") else ""
                parsed = getattr(resp, "parsed", None) if schema is not None else None
                if schema is not None and parsed is None and text:
                    parsed = schema.model_validate(json.loads(text))
                res = GeminiResult(text=text, parsed=parsed, tool_calls=_extract_tool_calls(resp), model=model,
                                   latency_ms=int((time.time() - t0) * 1000), usage=_usage(resp), trace_id=entry["id"])
                trace.update(entry["id"], status="ok", model=model, latency_ms=res.latency_ms, tool_calls=res.tool_calls,
                             usage=res.usage, output=(text or "")[:600], fallback_used=(model != configured[0]))
                return res
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                msg = str(exc)
                trace.update(entry["id"], last_error=msg[:300], model=model)
                if "400" in msg and "hinking" in msg and level != "LOW":
                    cfg["thinking_config"] = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)   # unsupported level: retry as LOW
                    level = "LOW"
                    continue
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    _COOL[model] = time.time() + 180          # quota does not recover in seconds: fall back now
                    break
                transient = any(k in msg for k in ("500", "502", "503", "504", "timed out", "Timeout", "UNAVAILABLE"))
                if not transient:
                    break                      # e.g. 404 model not found / other 400 -> try the next model
                if attempt == 1 or mi > 0:
                    _COOL[model] = time.time() + 60           # repeated overload: rest this model briefly
                    break
                time.sleep(2.0)
    trace.update(entry["id"], status="failed")
    raise GeminiUnavailable(f"all Gemini models failed: {last_err}")
