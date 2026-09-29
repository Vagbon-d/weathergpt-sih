"""
WeatherGPT Shared Grounded Advisory Pipeline (SIH26068).

This module exposes generate_grounded_advisory() — a single, reusable entry-point
for the ENTIRE zero-hallucination advisory pipeline, callable from:
  - routers/chat.py (web app channel)
  - routers/webhook.py (SMS / IVR / proactive-push channel)

ZERO-HALLUCINATION ARCHITECTURE GUARANTEE:
  The LLM is NEVER the source of weather facts, IMD warnings, or agricultural verdicts.
  All numeric values, warning flags, and agronomic decisions come from:
    1. Open-Meteo (numerical forecast)
    2. IMD crawled bulletins (via rag_service.get_official_warnings)
    3. Python deterministic rules engine (advisory_service.evaluate_*)
  The LLM only humanises / translates the pre-verified context.

channel parameter controls output format:
  "app"   -> full JSON response dict (existing web behaviour)
  "sms"   -> same pipeline; answer capped at ≤160 chars with source attribution
  "voice" -> same pipeline; answer returned as plain text for TTS synthesis
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from services import (
    weather_service,
    rag_service,
    llm_service,
    language_service,
    advisory_service,
    query_engine,
)

logger = logging.getLogger(__name__)

# Hard SMS single-segment limit (GSM-7 encoding, 160 chars)
SMS_MAX_CHARS = 160
# Attribution appended to every SMS reply (counts toward 160 chars)
SMS_SOURCE_TAG = " [IMD/Open-Meteo]"
# Graceful degradation responses when data is unavailable
_STALE_FEED_MESSAGES = {
    "en": "Weather data feed is currently unavailable. Please try again shortly. [WeatherGPT]",
    "hi": "मौसम डेटा अभी उपलब्ध नहीं है। कृपया थोड़ी देर बाद पुनः प्रयास करें। [WeatherGPT]",
    "hi-Latn": "Mausam data abhi uplabdh nahi hai. Kripya thodi der baad try karein. [WeatherGPT]",
    "or": "ପାଣିପାଗ ତଥ୍ୟ ବର୍ତ୍ତମାନ ଉପଲବ୍ଧ ନୁହେଁ। ଦୟାକରି ଟିକିଏ ପରେ ପୁଣି ଚେଷ୍ଟା କରନ୍ତୁ। [WeatherGPT]",
    "bn": "আবহাওয়া তথ্য এখন পাওয়া যাচ্ছে না। অনুগ্রহ করে একটু পরে আবার চেষ্টা করুন। [WeatherGPT]",
    "mr": "हवामान डेटा सध्या उपलब्ध नाही. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा. [WeatherGPT]",
    "gu": "હવામાન ડેટા હાલ ઉપલબ્ધ નથી. કૃપા કરીને થોડી વાર પછી ફરી પ્રયાસ કરો. [WeatherGPT]",
    "ta": "வானிலை தரவு தற்போது கிடைக்கவில்லை. சிறிது நேரம் கழித்து மீண்டும் முயற்சிக்கவும். [WeatherGPT]",
    "te": "వాతావరణ డేటా ప్రస్తుతం అందుబాటులో లేదు. కొంత సేపు తర్వాత మళ్ళీ ప్రయత్నించండి. [WeatherGPT]",
    "kn": "ಹವಾಮಾನ ಡೇಟಾ ಈಗ ಲಭ್ಯವಿಲ್ಲ. ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ. [WeatherGPT]",
}
_LOCATION_REQUIRED_MESSAGES = {
    "en": "Please provide your location so I can give accurate weather advice. Reply with your village or district name. [WeatherGPT]",
    "hi": "कृपया अपना स्थान बताएं ताकि मैं सटीक मौसम सलाह दे सकूँ। अपने गाँव या जिले का नाम लिखें। [WeatherGPT]",
    "hi-Latn": "Kripya apna location batayein taaki main sahi mausam salah de sakun. Apne gaon ya jile ka naam likhein. [WeatherGPT]",
    "or": "ଦୟାକରି ଆପଣଙ୍କ ସ୍ଥାନ ଜଣାନ୍ତୁ ଯାହାଦ୍ୱାରା ମୁଁ ସଠିକ ପାଣିପାଗ ପରାମର୍ଶ ଦେଇ ପାରିବି। [WeatherGPT]",
    "bn": "আপনার সঠিক আবহাওয়া পরামর্শের জন্য আপনার অবস্থান জানান। [WeatherGPT]",
}


def _truncate_for_sms(text: str, language: str, sources: list[str]) -> str:
    """
    Truncate answer to fit within a single GSM-7 SMS segment (160 chars).
    Appends a short source attribution tag.

    Safety rule: If truncation would cut mid-word, backtrack to the nearest
    sentence or word boundary to avoid garbled safety-critical information.
    """
    source_tag = SMS_SOURCE_TAG
    if not text:
        return ("No data." + source_tag)[: SMS_MAX_CHARS]

    max_body = SMS_MAX_CHARS - len(source_tag)
    if len(text) <= max_body:
        return (text + source_tag)[: SMS_MAX_CHARS]

    # Prefer sentence-boundary truncation (. or । or ।)
    truncated = text[:max_body]
    for sep in [". ", "। ", "। ", "। ", "\n"]:
        last_boundary = truncated.rfind(sep)
        if last_boundary > max_body // 2:
            truncated = truncated[: last_boundary + len(sep)].rstrip()
            break
    else:
        # Fall back to word boundary
        last_space = truncated.rfind(" ")
        if last_space > 10:
            truncated = truncated[:last_space]

    return (truncated + source_tag)[: SMS_MAX_CHARS]


async def generate_grounded_advisory(
    query: str,
    location: str | dict[str, Any] | None = None,
    language: str = "en",
    latitude: float | None = None,
    longitude: float | None = None,
    crop: str | None = None,
    history: list[dict[str, Any]] | None = None,
    channel: str = "app",
) -> dict[str, Any]:
    """
    Full, zero-hallucination grounded advisory pipeline.

    Parameters
    ----------
    query     : User question in any Indian language or English.
    location  : Location dict (from web app) or plain string name.
    language  : BCP-47 language code from UI (authoritative for response language).
    latitude  : Optional GPS latitude.
    longitude : Optional GPS longitude.
    crop      : Optional crop name for agricultural context.
    history   : Recent conversation turns for multi-turn follow-up resolution.
    channel   : "app" (full JSON), "sms" (≤160 char text), or "voice" (plain text for TTS).

    Returns
    -------
    dict with keys:
      answer           – natural language response (truncated for SMS)
      domain           – classified intent domain
      intent           – fine-grained intent label
      location         – resolved location name
      language         – detected/response language code
      sources          – list of authoritative data sources used
      source_details   – per-source attribution dict
      weather          – weather snapshot dict (None if unavailable)
      alerts           – list of active IMD warnings
      advisories       – list of evaluated advisory KB entries
      operations       – dict of ag operation safety verdicts
      weather_used     – bool
      location_required– bool (True if location could not be resolved)
      stale_feed       – bool (True if the weather feed was unavailable)
      channel          – echoed channel parameter
      response_time_ms – latency in ms
      timestamp        – ISO-8601 UTC timestamp of response generation
    """
    from datetime import datetime, timezone

    start_time = time.time()
    query = (query or "").strip()
    timestamp = datetime.now(timezone.utc).isoformat()

    if not query:
        return _error_response(
            message="Empty query received.",
            language=language,
            channel=channel,
            timestamp=timestamp,
        )

    # ------------------------------------------------------------------
    # 1. Language detection (mirrors routers/chat.py exactly)
    # ------------------------------------------------------------------
    target_lang = (language or "en").lower().split("-")[0]
    has_indic_script = bool(re.search(r"[\u0900-\u0DFF]", query))
    if has_indic_script:
        detected_lang = language_service.detect_language(query, target_lang)
    elif target_lang in ["hi", "mr", "gu", "bn", "ta", "te", "kn", "ml", "pa", "or", "kok"]:
        if target_lang == "hi" and language_service.detect_language(query, "hi") == "hi-Latn":
            detected_lang = "hi-Latn"
        else:
            detected_lang = target_lang
    else:
        detected_lang = "en"

    # ------------------------------------------------------------------
    # 2. Intent classification & temporal resolution
    # ------------------------------------------------------------------
    intent_info = query_engine.understand_query(query, history)
    domain = intent_info.get("domain", intent_info["intent"])
    temporal_target = intent_info["temporal_target"]

    # ------------------------------------------------------------------
    # 3. First-stage filters: unsupported / smalltalk / ambiguous
    # ------------------------------------------------------------------
    if intent_info.get("is_unsupported") or domain == "unsupported" or intent_info.get("is_unrelated"):
        return _simple_response(
            answer=_unsupported_text(intent_info, detected_lang),
            intent="unsupported",
            domain="unsupported",
            language=detected_lang,
            temporal_target=temporal_target,
            channel=channel,
            timestamp=timestamp,
        )

    if domain == "smalltalk" or intent_info.get("intent") == "smalltalk":
        return _simple_response(
            answer=_smalltalk_text(detected_lang),
            intent="smalltalk",
            domain="smalltalk",
            language=detected_lang,
            temporal_target=temporal_target,
            channel=channel,
            timestamp=timestamp,
        )

    if intent_info.get("is_ambiguous") or domain == "ambiguous":
        return _simple_response(
            answer=intent_info.get("clarification_prompt") or _ambiguous_text(detected_lang),
            intent="ambiguous",
            domain="ambiguous",
            language=detected_lang,
            temporal_target=temporal_target,
            channel=channel,
            timestamp=timestamp,
        )

    # ------------------------------------------------------------------
    # 4. Location resolution (mirrors routers/chat.py Section 11 & 8)
    # ------------------------------------------------------------------
    app_loc_name: str | None = None
    app_admin_name: str | None = None
    app_lat: float | None = latitude
    app_lon: float | None = longitude

    if isinstance(location, dict):
        candidates = [
            location.get("label"),
            location.get("admin_label"),
            location.get("weather_location"),
            location.get("admin_name"),
            location.get("name"),
            location.get("displayName"),
        ]
        for cand in candidates:
            if cand and isinstance(cand, str) and not re.match(r"^\d{4,6}$", cand.strip()):
                app_loc_name = cand.strip()
                break
        app_admin_name = (
            location.get("weather_location")
            or location.get("admin_label")
            or app_loc_name
        )
        if app_loc_name:
            app_admin_name = query_engine.format_conversational_location(app_loc_name, detected_lang)
        if location.get("latitude") is not None:
            try:
                app_lat = float(location["latitude"])
            except (ValueError, TypeError):
                pass
        if location.get("longitude") is not None:
            try:
                app_lon = float(location["longitude"])
            except (ValueError, TypeError):
                pass
    elif isinstance(location, str) and location.strip():
        raw_str = location.strip()
        if not re.match(r"^\d{4,6}$", raw_str):
            app_loc_name = raw_str
            app_admin_name = query_engine.format_conversational_location(app_loc_name, detected_lang)

    raw_query_location = intent_info.get("query_location") or intent_info.get("location_query")
    if raw_query_location:
        raw_low = raw_query_location.strip().lower()
        if raw_low in query_engine.LOCATION_STOP_WORDS or any(
            w in raw_low for w in ["harvest", "spray", "irrigate", "sow", "pesticide"]
        ):
            raw_query_location = None

    location_source = "application"
    weather_lat: float | None = None
    weather_lon: float | None = None
    resolved_location: str = ""

    # If caller has exact GPS/profile coordinates and the query mentions their home region/state,
    # preserve the high-precision device coordinates instead of fuzzy geocoding across India
    if app_lat is not None and app_lon is not None and app_loc_name and raw_query_location:
        if raw_query_location.lower() in app_loc_name.lower() or app_loc_name.lower() in raw_query_location.lower():
            raw_query_location = None

    if raw_query_location:
        try:
            q_lat, q_lon, q_name = await weather_service.geocode(raw_query_location)
            q_name_low = q_name.lower()
            if any(
                term in q_name_low
                for term in ["rainwater harvesting", "harvesting", "health centre", "hospital"]
            ) and (app_lat is not None or app_loc_name):
                raw_query_location = None
            else:
                weather_lat, weather_lon = q_lat, q_lon
                resolved_location = q_name
                location_source = "query"
        except Exception as geo_err:
            logger.warning("Failed to geocode query location '%s': %s", raw_query_location, geo_err)
            raw_query_location = None

    if not raw_query_location:
        if app_loc_name or (app_lat is not None and app_lon is not None):
            location_source = "application"
            resolved_location = app_admin_name or app_loc_name or f"Lat {app_lat:.2f}, Lon {app_lon:.2f}"
            weather_lat = app_lat
            weather_lon = app_lon
        else:
            # CRITICAL: No location — degrade gracefully, do NOT fabricate
            stale_msg = _LOCATION_REQUIRED_MESSAGES.get(detected_lang, _LOCATION_REQUIRED_MESSAGES["en"])
            if channel == "sms":
                stale_msg = stale_msg[:SMS_MAX_CHARS]
            return {
                "answer": stale_msg,
                "intent": domain,
                "domain": domain,
                "location": None,
                "language": detected_lang,
                "sources": [],
                "source_details": {},
                "temporal_target": temporal_target,
                "detected_language": detected_lang,
                "weather_used": False,
                "location_required": True,
                "stale_feed": False,
                "weather": None,
                "alerts": [],
                "advisories": [],
                "operations": None,
                "channel": channel,
                "response_time_ms": round((time.time() - start_time) * 1000, 2),
                "timestamp": timestamp,
            }

    # ------------------------------------------------------------------
    # 5. Live weather retrieval with location-consistency validation
    # ------------------------------------------------------------------
    try:
        weather = await weather_service.get_current_and_forecast(
            location=resolved_location,
            latitude=weather_lat,
            longitude=weather_lon,
        )
    except ValueError as exc:
        logger.warning("Location not found: %s", exc)
        stale_msg = _LOCATION_REQUIRED_MESSAGES.get(detected_lang, _LOCATION_REQUIRED_MESSAGES["en"])
        if channel == "sms":
            stale_msg = stale_msg[:SMS_MAX_CHARS]
        return _stale_response(
            message=stale_msg,
            language=detected_lang,
            channel=channel,
            timestamp=timestamp,
        )
    except Exception as exc:
        logger.error("Weather service unavailable: %s", exc)
        stale_msg = _STALE_FEED_MESSAGES.get(detected_lang, _STALE_FEED_MESSAGES["en"])
        if channel == "sms":
            stale_msg = stale_msg[:SMS_MAX_CHARS]
        return _stale_response(
            message=stale_msg,
            language=detected_lang,
            channel=channel,
            timestamp=timestamp,
        )

    # Location identity validation (Section 15)
    retrieved_loc_name = weather.get("location", resolved_location)
    req_loc_meta = {"name": resolved_location, "latitude": weather_lat, "longitude": weather_lon}
    ret_loc_meta = {
        "name": retrieved_loc_name,
        "latitude": weather.get("latitude"),
        "longitude": weather.get("longitude"),
    }
    loc_val_pass, loc_val_reason = query_engine.validate_location_identity(req_loc_meta, ret_loc_meta)
    if not loc_val_pass:
        logger.warning("Location validation failed (%s). Re-fetching for '%s'", loc_val_reason, resolved_location)
        try:
            canon_lat, canon_lon, canon_name = await weather_service.geocode(resolved_location)
            weather = await weather_service.get_current_and_forecast(
                location=canon_name, latitude=canon_lat, longitude=canon_lon
            )
            retrieved_loc_name = weather.get("location", canon_name)
        except Exception as e:
            logger.error("Failed to recover via geocoding for '%s': %s", resolved_location, e)

    # ------------------------------------------------------------------
    # 6. Domain-selective data retrieval (alerts, advisories, RAG)
    # ------------------------------------------------------------------
    is_warning_query = (
        getattr(intent_info, "requires_alerts", False)
        or getattr(intent_info, "requires_warning", False)
        or domain in ["alerts", "warning", "cyclone"]
        or intent_info.get("intent") in ["official_warning", "cyclone_warning", "alerts"]
        or (
            ("warning" in query.lower() or "alert" in query.lower() or "चेतावनी" in query)
            and not any(
                ws in query.lower()
                for ws in ["weather", "forecast", "mausam", "temperature", "rain"]
            )
        )
    )

    alerts_data: list[dict[str, Any]] = []
    if is_warning_query or intent_info.get("activity") in ["fishing", "marine"]:
        target_dt = intent_info.get("resolved_date") or temporal_target
        alerts_data = rag_service.get_official_warnings(resolved_location, target_date=target_dt)

    evaluated_advisories: list[dict[str, Any]] = []
    ag_operations = None
    requires_ag = (
        getattr(intent_info, "requires_agriculture", False)
        or domain in ["agriculture", "spraying", "irrigation", "harvesting"]
    )
    if requires_ag:
        search_query = f"{query} {crop}" if crop else query
        raw_advisories = rag_service.retrieve_advisory(query=search_query)
        evaluated_advisories = rag_service.evaluate_triggers(raw_advisories, weather)
        ag_operations = {
            "spray": advisory_service.evaluate_spray_safety(weather),
            "irrigation": advisory_service.evaluate_irrigation_safety(weather),
            "harvest": advisory_service.evaluate_harvest_safety(weather),
            "sowing": advisory_service.evaluate_sowing_safety(weather, crop=crop),
        }

    rag_docs: list[dict[str, Any]] = []
    if is_warning_query or requires_ag:
        rag_docs = rag_service.retrieve_meteorological_context(
            query=query,
            location=resolved_location,
            intent=domain,
            crop=crop,
            target_date=temporal_target,
        )

    # ------------------------------------------------------------------
    # 7. Build verified context (Golden Rule: LLM sees ONLY verified facts)
    # ------------------------------------------------------------------
    verified_context = query_engine.build_verified_context(
        query=query,
        intent_info=intent_info,
        weather_data=weather,
        advisory_data=evaluated_advisories,
        alerts_data=alerts_data,
        language=detected_lang,
        rag_documents=rag_docs,
    )

    # ------------------------------------------------------------------
    # 8. LLM grounded synthesis (Ollama / Qwen3)
    # ------------------------------------------------------------------
    answer = await llm_service.generate_grounded_answer(
        query=query,
        domain=domain,
        weather_data=weather,
        advisory_data=evaluated_advisories,
        alerts_data=alerts_data,
        language=detected_lang,
        verified_context=verified_context,
    )

    # ------------------------------------------------------------------
    # 9. Numeric safety validation → deterministic fallback if invalid
    # ------------------------------------------------------------------
    is_valid = False
    if answer:
        valid_struct, _ = query_engine.validate_llm_answer(answer, verified_context, detected_lang)
        if valid_struct:
            is_valid = llm_service.validate_numeric_safety(
                llm_answer=answer,
                weather_data=weather,
                advisory_data=evaluated_advisories,
                alerts_data=alerts_data,
            )

    if not answer or not is_valid:
        answer = query_engine.generate_human_deterministic_answer(
            verified_context=verified_context,
            language=detected_lang,
        )

    # ------------------------------------------------------------------
    # 10. Source attribution
    # ------------------------------------------------------------------
    sources = ["Open-Meteo"]
    source_details = {"weather": "Open-Meteo (Numerical Forecast Model)"}

    if alerts_data and any("imd" in str(a.get("source", "")).lower() for a in alerts_data):
        sources.append("IMD")
        source_details["warnings"] = "IMD (Authoritative Warnings & Bulletins)"

    if requires_ag and evaluated_advisories:
        sources.append("ICAR / IMD Agromet")
        source_details["advisory"] = "ICAR / IMD Agromet Advisory Bulletins"

    if location_source == "query" or app_loc_name:
        sources.append("Photon")
        source_details["geocoding"] = "Photon (OpenStreetMap Geocoding)"

    # Timestamp string for attribution (IST)
    from datetime import timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    as_of = datetime.now(ist).strftime("%d %b %Y %H:%M IST")

    # ------------------------------------------------------------------
    # 11. Channel-specific answer shaping
    # ------------------------------------------------------------------
    if channel == "sms":
        answer = _truncate_for_sms(answer, detected_lang, sources)
    # "voice" and "app" use the full answer as-is

    duration_ms = round((time.time() - start_time) * 1000, 2)

    return {
        "answer": answer,
        "domain": domain,
        "intent": intent_info.get("intent", domain),
        "activity": intent_info.get("activity"),
        "activity_suitability": verified_context.get("activity_suitability"),
        "temporal_target": temporal_target,
        "date_intent": verified_context.get("date_intent", intent_info.get("date_intent", "today")),
        "resolved_date": verified_context.get("resolved_date", intent_info.get("resolved_date")),
        "date_match": verified_context.get("date_match", True),
        "retrieved_forecast_date": verified_context.get("retrieved_forecast_date"),
        "location": resolved_location,
        "location_source": location_source,
        "query_location": raw_query_location,
        "inherit_context": intent_info.get("inherit_context", False),
        "language": detected_lang,
        "sources": sources,
        "source_details": source_details,
        "rag_count": len(rag_docs),
        "response_time_ms": duration_ms,
        "detected_language": detected_lang,
        "weather_used": True,
        "location_required": False,
        "stale_feed": False,
        "as_of": as_of,
        "weather": {
            "source": weather.get("source"),
            "location": weather.get("location"),
            "current": weather.get("current"),
            "forecast": weather.get("forecast"),
            "latitude": weather.get("latitude"),
            "longitude": weather.get("longitude"),
        },
        "alerts": alerts_data,
        "advisories": evaluated_advisories,
        "operations": ag_operations,
        "channel": channel,
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _unsupported_text(intent_info: Any, detected_lang: str) -> str:
    cat = intent_info.get("unsupported_category")
    if cat == "coding":
        return {
            "hi": "मैं वेदरजीपीटी हूँ — केवल मौसम, चेतावनी और कृषि सलाह। कोडिंग में सहायता नहीं।",
            "hi-Latn": "Main WeatherGPT hoon — keval mausam, alerts aur kheti salah. Coding mein madad nahi.",
            "en": "I am WeatherGPT — weather, warnings, and farm advice only. I cannot help with programming.",
        }.get(detected_lang, "I am WeatherGPT — weather, warnings, and farm advice only.")
    return {
        "hi": "मैं वेदरजीपीटी हूँ। केवल मौसम, चेतावनी और कृषि सलाह।",
        "hi-Latn": "Main WeatherGPT hoon. Keval mausam, alerts aur kheti salah.",
        "en": "I am WeatherGPT. I can help with weather, warnings, and farming decisions only.",
    }.get(detected_lang, "I am WeatherGPT. I can help with weather, warnings, and farming decisions only.")


def _smalltalk_text(detected_lang: str) -> str:
    return {
        "hi": "नमस्ते! मैं वेदरजीपीटी हूँ। मौसम या खेती के बारे में पूछें।",
        "hi-Latn": "Namaste! Main WeatherGPT hoon. Mausam ya kheti ke baare mein poochein.",
        "en": "Hello! I am WeatherGPT. Ask me about weather, warnings, or farming decisions.",
    }.get(detected_lang, "Hello! I am WeatherGPT. Ask me about weather or farming.")


def _ambiguous_text(detected_lang: str) -> str:
    return {
        "hi": "कृपया स्पष्ट करें — क्या आप बारिश, छिड़काव, सिंचाई या अलर्ट के बारे में पूछना चाहते हैं?",
        "hi-Latn": "Kripya specify karein — kya aap baarish, chhidkaw, sinchai ya alerts ke baare mein pooch rahe hain?",
        "en": "Could you specify? Are you asking about rain, spraying, irrigation, or weather alerts?",
    }.get(detected_lang, "Could you specify? Are you asking about rain, spraying, irrigation, or weather alerts?")


def _simple_response(
    answer: str,
    intent: str,
    domain: str,
    language: str,
    temporal_target: str,
    channel: str,
    timestamp: str,
) -> dict[str, Any]:
    if channel == "sms" and len(answer) > SMS_MAX_CHARS:
        answer = answer[:SMS_MAX_CHARS]
    return {
        "answer": answer,
        "intent": intent,
        "domain": domain,
        "location": None,
        "language": language,
        "sources": [],
        "source_details": {},
        "temporal_target": temporal_target,
        "detected_language": language,
        "weather_used": False,
        "location_required": False,
        "stale_feed": False,
        "weather": None,
        "alerts": [],
        "advisories": [],
        "operations": None,
        "channel": channel,
        "response_time_ms": 0,
        "timestamp": timestamp,
    }


def _stale_response(
    message: str,
    language: str,
    channel: str,
    timestamp: str,
) -> dict[str, Any]:
    return {
        "answer": message,
        "intent": "error",
        "domain": "error",
        "location": None,
        "language": language,
        "sources": [],
        "source_details": {},
        "temporal_target": "today",
        "detected_language": language,
        "weather_used": False,
        "location_required": False,
        "stale_feed": True,
        "weather": None,
        "alerts": [],
        "advisories": [],
        "operations": None,
        "channel": channel,
        "response_time_ms": 0,
        "timestamp": timestamp,
    }


def _error_response(
    message: str,
    language: str,
    channel: str,
    timestamp: str,
) -> dict[str, Any]:
    return _stale_response(
        message=message,
        language=language,
        channel=channel,
        timestamp=timestamp,
    )
