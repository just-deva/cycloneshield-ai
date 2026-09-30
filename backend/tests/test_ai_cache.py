from __future__ import annotations

import json

import pytest

from app import engine
from app.ai import advisory as adv
from app.ai import aicache
from app.ai import gemini_client as gc


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(aicache, "DIR", tmp_path / "ai_cache")
    adv.clear_cache()
    yield
    adv.clear_cache()


@pytest.fixture(scope="module")
def hudhud():
    return engine.simulate("IN-AP", "hudhud-2014", ensemble=False)


class _Parsed:
    def __init__(self, d):
        self._d = d

    def model_dump(self):
        return self._d


def _live(monkeypatch, drafts):
    seq = iter(drafts)
    monkeypatch.setattr(gc, "available", lambda: True)
    monkeypatch.setattr(gc, "generate", lambda **kw: gc.GeminiResult(parsed=_Parsed(next(seq)), model="gemini-test", trace_id=0))


def _offline(monkeypatch):
    monkeypatch.setattr(gc, "available", lambda: False)


def _good(sim):
    w = int(round(sim["focus"]["peak_wind_kmh"]))
    return {"headline": f"Wind up to {w} km/h", "situation": "Prepare now.", "actions": [], "uncertainty": "Screening-level ranges, not official."}


def test_live_output_is_cached_and_served_when_gemini_is_unavailable(monkeypatch, hudhud):
    _live(monkeypatch, [_good(hudhud)])
    a = adv.draft_advisory(hudhud, 24, "hospital", "English")
    assert a["source"] == "gemini-test" and a["cached"] is None
    assert aicache.stats()["entries"] == 1
    adv.clear_cache()
    _offline(monkeypatch)                                   # quota gone / no key
    b = adv.draft_advisory(hudhud, 24, "hospital", "English")
    assert b["source"] == "gemini-test (cached)" and b["cached"]["model"] == "gemini-test"
    assert b["validation"]["passed"] and any("primed AI cache" in n for n in b["notes"])
    assert b["english"] == a["english"]


def test_refresh_bypasses_the_cache(monkeypatch, hudhud):
    _live(monkeypatch, [_good(hudhud), {**_good(hudhud), "headline": f"Second live draft {int(round(hudhud['focus']['peak_wind_kmh']))} km/h"}])
    adv.draft_advisory(hudhud, 24, "hospital", "English")
    adv.clear_cache()
    b = adv.draft_advisory(hudhud, 24, "hospital", "English", refresh=True)
    assert b["source"] == "gemini-test" and "Second live draft" in b["english"]["headline"]


def test_a_tampered_cache_entry_is_rejected_by_the_validator(monkeypatch, hudhud):
    _live(monkeypatch, [_good(hudhud)])
    adv.draft_advisory(hudhud, 24, "hospital", "English")
    (path,) = list(aicache.DIR.glob("advisory-*.json"))
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["english"]["headline"] = "Wind up to 999 km/h"       # somebody edits the cache file
    path.write_text(json.dumps(rec), encoding="utf-8")
    adv.clear_cache()
    _offline(monkeypatch)
    b = adv.draft_advisory(hudhud, 24, "hospital", "English")
    assert b["source"] == "template" and "999" not in json.dumps(b["english"])


def test_cache_is_keyed_by_the_exact_facts(monkeypatch, hudhud):
    _live(monkeypatch, [_good(hudhud)])
    adv.draft_advisory(hudhud, 24, "hospital", "English")
    adv.clear_cache()
    _offline(monkeypatch)
    other_lead = adv.draft_advisory(hudhud, 48, "hospital", "English")      # different facts (lead time) -> no hit
    other_role = adv.draft_advisory(hudhud, 24, "power", "English")         # different audience -> no hit
    assert other_lead["source"] == "template" and other_role["source"] == "template"


def test_translation_is_cached_too(monkeypatch, hudhud):
    good = _good(hudhud)
    tel = {**good, "headline": f"గాలి {int(round(hudhud['focus']['peak_wind_kmh']))} km/h"}
    _live(monkeypatch, [good, tel])
    a = adv.draft_advisory(hudhud, 24, "district_collector", "Telugu")
    assert a["localized"]["headline"].startswith("గ") and aicache.stats()["by_kind"]["translation"] == 1
    adv.clear_cache()
    _offline(monkeypatch)
    b = adv.draft_advisory(hudhud, 24, "district_collector", "Telugu")
    assert b["translation"]["model"].endswith("(cached)") and b["localized"] == a["localized"]
