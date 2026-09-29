"""Gemini-backed advisory generation with a dependable offline fallback."""
from __future__ import annotations

import os
import logging
import json
from urllib import error, request
from typing import Any

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("cycloneshield.gemini")

_LANGUAGES = {
    "Assamese": "as-IN", "Bengali": "bn-IN", "Bodo": "brx-IN", "Dogri": "doi-IN",
    "Gujarati": "gu-IN", "Hindi": "hi-IN", "Kannada": "kn-IN", "Kashmiri": "ks-IN",
    "Konkani": "kok-IN", "Maithili": "mai-IN", "Malayalam": "ml-IN", "Manipuri": "mni-IN",
    "Marathi": "mr-IN", "Nepali": "ne-NP", "Odia": "or-IN", "Punjabi": "pa-IN",
    "Sanskrit": "sa-IN", "Santhali": "sat-IN", "Sindhi": "sd-IN", "Tamil": "ta-IN",
    "Telugu": "te-IN", "Urdu": "ur-IN", "English": "en-IN",
}


def _fallback(ward_name: str, risk_level: str, blocked_roads: list[str], assigned_shelter: str | None, language: str) -> str:
    road_text = ", ".join(blocked_roads) if blocked_roads else "No monitored road closures"
    shelter_text = assigned_shelter or "the nearest designated cyclone shelter"
    templates = {
        "English": f"Municipal Control Room: {ward_name} is at {risk_level} cyclone risk. Residents should avoid {road_text} and move early to {shelter_text}. Keep medicines, documents, and a charged phone ready; follow official updates only.",
        "Telugu": f"మున్సిపల్ కంట్రోల్ రూమ్: {ward_name}కు {risk_level} తుఫాను ప్రమాదం ఉంది. {road_text}ను తప్పించి, ముందుగానే {shelter_text}కు వెళ్లండి. మందులు, పత్రాలు, చార్జ్ చేసిన ఫోన్ సిద్ధంగా ఉంచి అధికారిక సూచనలనే పాటించండి.",
        "Odia": f"ପୌର ନିୟନ୍ତ୍ରଣ କକ୍ଷ: {ward_name}ରେ {risk_level} ବାତ୍ୟା ବିପଦ ରହିଛି। {road_text} ଏଡ଼ାଇ ଶୀଘ୍ର {shelter_text}କୁ ଯାଆନ୍ତୁ। ଔଷଧ, କାଗଜପତ୍ର ଓ ଚାର୍ଜ ଫୋନ ପ୍ରସ୍ତୁତ ରଖନ୍ତୁ ଏବଂ କେବଳ ସରକାରୀ ସୂଚନା ମାନନ୍ତୁ।",
        "Hindi": f"नगर नियंत्रण कक्ष: {ward_name} में {risk_level} चक्रवात जोखिम है। {road_text} से बचें और समय रहते {shelter_text} पहुंचें। दवाइयाँ, दस्तावेज़ और चार्ज फोन तैयार रखें तथा केवल आधिकारिक सूचना मानें।",
    }
    if language in templates:
        return templates[language]
    return (f"Municipal Control Room: {ward_name} is at {risk_level} cyclone risk. "
            f"Avoid {road_text} and move early to {shelter_text}. "
            "Keep medicines, documents, and a charged phone ready; follow official updates only.")


def generate_advisory(ward_name: str, risk_level: str, blocked_roads: list[str], assigned_shelter: str | None, language: str) -> dict[str, Any]:
    """Generate exactly three sentences, returning a local-language fallback on any failure."""
    language = language if language in _LANGUAGES else "English"
    fallback = _fallback(ward_name, risk_level, blocked_roads, assigned_shelter, language)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"advisory": fallback, "language": language, "locale": _LANGUAGES[language], "source": "local-fallback"}
    prompt = (f"Write exactly three short sentences in {language} for a municipal cyclone emergency advisory. "
              f"Ward: {ward_name}; risk: {risk_level}; blocked roads: {', '.join(blocked_roads) or 'none'}; "
              f"assigned shelter: {assigned_shelter or 'nearest designated cyclone shelter'}. "
              "Sentence 1 is an executive briefing, sentence 2 is a resident action, sentence 3 is a safety reminder. No heading or bullets.")
    models = ("gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite")
    last_error: Exception | None = None
    for model in models:
        try:
            payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
            api_request = request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                data=payload,
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                method="POST",
            )
            with request.urlopen(api_request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
            parts = body.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            advisory = "".join(part.get("text", "") for part in parts).strip()
            if sum(advisory.count(mark) for mark in ".!?।") < 2:
                raise ValueError("Gemini response did not contain three sentences")
            return {"advisory": advisory, "language": language, "locale": _LANGUAGES[language], "source": model}
        except (error.HTTPError, error.URLError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            detail = exc.read().decode("utf-8", errors="replace") if isinstance(exc, error.HTTPError) else str(exc)
            logger.warning("Gemini model %s was unavailable: %s", model, detail)
    logger.error("All Gemini advisory models failed: %s", last_error)
    return {"advisory": fallback, "language": language, "locale": _LANGUAGES[language], "source": "local-fallback"}
