"""Prime the persistent AI cache with REAL Gemini outputs for the demo scenarios.

    python scripts/prime_ai_cache.py            # default set
    python scripts/prime_ai_cache.py --quick    # a handful of calls
    python scripts/prime_ai_cache.py --dry      # show the plan, call nothing

Why: quota or credits can run out while someone evaluates the prototype. Every output this script stores was produced by Gemini for a
specific facts packet (SHA-256 keyed) and is re-validated before it is served; the UI labels it "(cached)" and offers "Regenerate live".
Calls are paced to respect free-tier rate limits and the script stops cleanly when the model is unavailable.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import engine  # noqa: E402
from app.ai import advisory as adv  # noqa: E402
from app.ai import aicache  # noqa: E402
from app.ai import copilot  # noqa: E402
from app.ai import gemini_client as gc  # noqa: E402

PACE_S = 6.0
ROLES = ["district_collector", "hospital", "power", "roads", "shelter", "fisheries"]
SUGGESTED_QUESTIONS = [
    "Which hospitals are most at risk and when does it start?",
    "Can people evacuate safely? Which places are stranded?",
    "What is the storm surge range and how sure are we?",
    "Which roads will be cut first?",
    "How does the surge model work and what are its limits?",
]

# (tenant, storm, lead hours, roles, extra languages)
PLAN = [
    ("IN-AP", "hudhud-2014", 24, ROLES, ["Telugu", "Hindi"]),
    ("IN-AP", "hudhud-2014", 48, ["district_collector", "hospital", "power"], ["Telugu"]),
    ("IN-AP", "hudhud-2014", 12, ["district_collector", "shelter"], ["Telugu"]),
    ("IN-AP", "hudhud-2014", 72, ["district_collector"], []),
    ("IN-AP", "montha-2025", 24, ["district_collector"], ["Telugu"]),
    ("IN-OR", "fani-2019", 24, ["district_collector", "hospital", "fisheries"], ["Odia", "Hindi"]),
    ("VN", "yagi-2024", 24, ["district_collector"], ["Vietnamese"]),
]
QUICK = [PLAN[0][:3] + (["district_collector", "hospital"], ["Telugu"]), PLAN[4], PLAN[5][:3] + (["district_collector"], ["Odia"])]


def main() -> None:
    dry, quick = "--dry" in sys.argv, "--quick" in sys.argv
    plan = QUICK if quick else PLAN
    if not dry and not gc.available():
        sys.exit("GEMINI_API_KEY is not configured")
    done = failed = 0
    t_start = time.time()
    for tenant, storm, lead, roles, langs in plan:
        sim = engine.simulate(tenant, storm, ensemble=True)
        for role in roles:
            for lang in ["English", *langs]:
                label = f"{tenant} {storm} T-{lead}h {role} {lang}"
                if dry:
                    print("plan:", label)
                    continue
                try:
                    a = adv.draft_advisory(sim, lead, role, lang, refresh=True)
                except gc.GeminiUnavailable as exc:
                    print(f"STOP: Gemini unavailable ({str(exc)[:160]})")
                    print(f"cached so far: {aicache.stats()}")
                    return
                ok = a["source"] != "template"
                done += ok
                failed += (not ok)
                print(f"{'ok ' if ok else 'TEMPLATE'} {label}: {a['source']}" + ("" if ok else f" - {a['notes'][-1][:110]}"))
                if not ok:
                    print("The model returned no usable draft; stopping so we do not burn quota on a dead model.")
                    print(f"cached so far: {aicache.stats()}")
                    return
                time.sleep(PACE_S)
    if not dry and plan is PLAN or (not dry and plan is QUICK):
        # copilot answers for the main demo scenario
        sim = engine.simulate("IN-AP", "hudhud-2014", ensemble=True)
        for q in (SUGGESTED_QUESTIONS[:2] if quick else SUGGESTED_QUESTIONS):
            try:
                r = copilot.ask(sim, 24, q, refresh=True)
                print(f"copilot ok verified={r['numbers_verified']} model={r['model']}: {q}")
                done += 1
            except gc.GeminiUnavailable as exc:
                print(f"STOP: copilot unavailable ({str(exc)[:120]})")
                break
            time.sleep(PACE_S)
    print(f"finished: {done} generated, {failed} template fallbacks in {time.time() - t_start:.0f}s; cache: {aicache.stats()}")


if __name__ == "__main__":
    main()
