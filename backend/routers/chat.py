"""
WeatherGPT conversational API.

Safety Architecture:
User Question
      ↓
Query Classification (Deterministic keyword routing)
      ↓
Location Enforcement (Requires canonical location or GPS coordinates)
      ↓
Live Weather / Alert / Advisory Retrieval (IMD + Open-Meteo & local KB)
      ↓
Python Threshold, Temporal & Mathematical Evaluation
      ↓
Grounded Context Injection
      ↓
Ollama (qwen3:4b) OR Deterministic Python Fallback
      ↓
Natural Language Answer (Strictly sanitized, no <think> tags, no raw JSON)

The LLM is NEVER the source of weather facts. Every numeric weather value
displayed in the UI originates from authoritative weather providers.
"""

import logging
import re
import time
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services import (
    weather_service,
    rag_service,
    llm_service,
    language_service,
    advisory_service,
    query_engine,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    location: str | dict[str, Any] | None = None
    language: str = "en"
    latitude: float | None = None
    longitude: float | None = None
    history: list[dict[str, Any]] | None = None
    crop: str | None = None
    conversation_id: str | None = None


@router.post("/chat")
async def chat(req: ChatRequest):
    start_time = time.time()
    query = req.query.strip()
    if not query:
        raise HTTPException(
            status_code=400,
            detail="Please enter a question.",
        )

    # 1. Enforce global language state (req.language from UI)
    # The UI language selection is authoritative so that English UI receives English answers,
    # and Hindi UI receives Hindi answers.
    target_lang = (req.language or "en").lower().split("-")[0]
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

    # 2. Understand intent and temporal window with multi-turn history resolution
    intent_info = query_engine.understand_query(query, req.history)
    domain = intent_info.get("domain", intent_info["intent"])
    temporal_target = intent_info["temporal_target"]

    # 1. First-Stage Filter: Unsupported / Out-of-Domain queries exit immediately
    # ZERO weather API calls, ZERO RAG calls, ZERO Ollama calls (< 2ms execution time)
    if intent_info.get("is_unsupported") or domain == "unsupported" or intent_info.get("is_unrelated"):
        cat = intent_info.get("unsupported_category")
        if cat == "coding":
            unsupported_text = {
                "hi": "मैं वेदरजीपीटी (WeatherGPT) हूँ, जो केवल मौसम पूर्वानुमान, मौसम अलर्ट और कृषि सलाह के लिए बनाया गया है। मैं कंप्यूटर कोडिंग या प्रोग्रामिंग में सहायता नहीं कर सकता।",
                "hi-Latn": "Main WeatherGPT hoon, jo keval mausam, alerts aur kheti ki salah ke liye banaya gaya hai. Main programming ya coding me madad nahi kar sakta.",
                "mr": "मी वेदरजीपीटी (WeatherGPT) आहे, फक्त हवामान, इशारे आणि शेती सल्ला यासाठी. मी कॉम्प्युटर कोडिंग किंवा प्रोग्रामिंग करू शकत नाही.",
                "kok": "हांव वेदरजीपीटी (WeatherGPT), फक्त हवामान, शिटकावण्यो आनी शेतकाम म्हायती खातीर. हांव कोडिंग करूंक शकना.",
                "en": "I am WeatherGPT, specialized in weather forecasting, alerts, and agricultural advisory. I cannot assist with computer programming or writing code.",
            }.get(detected_lang, "I am WeatherGPT, specialized in weather forecasting, alerts, and agricultural advisory. I cannot assist with computer programming or writing code.")
        else:
            unsupported_text = {
                "hi": "मैं वेदरजीपीटी (WeatherGPT) हूँ। मैं केवल आपके क्षेत्र के मौसम, मौसम चेतावनी, खेती के निर्णयों और मौसम-संबंधी योजना में सहायता कर सकता हूँ।",
                "hi-Latn": "Main WeatherGPT hoon. Main keval aapke area ke mausam, weather alerts, kheti ke faislon aur weather planning me madad kar sakta hoon.",
                "mr": "मी वेदरजीपीटी (WeatherGPT) आहे. मी फक्त आपल्या परिसरातील हवामान, हवामान इशारे, शेतीचे निर्णय आणि हवामानाच्या नियोजनात मदत करू शकतो.",
                "kok": "हांव वेदरजीपीटी (WeatherGPT). हांव फक्त हवामान, इशारे आनी शेती कामां विशीं मदत करूंक शकता.",
                "en": "I am WeatherGPT. I can help with weather, weather warnings, farming decisions, and weather-related planning for your location.",
            }.get(detected_lang, "I am WeatherGPT. I can help with weather, weather warnings, farming decisions, and weather-related planning for your location.")

        return {
            "answer": unsupported_text,
            "intent": "unsupported",
            "domain": "unsupported",
            "location": None,
            "language": detected_lang,
            "sources": [],
            "temporal_target": temporal_target,
            "detected_language": detected_lang,
            "weather_used": False,
            "location_required": False,
            "weather": None,
            "alerts": [],
            "advisories": [],
        }

    # 2. First-Stage Filter: Conversational Smalltalk / Greetings
    if domain == "smalltalk" or intent_info.get("intent") == "smalltalk":
        smalltalk_map = {
            "hi": "नमस्ते! मैं वेदरजीपीटी (WeatherGPT) हूँ, आपका मौसम और कृषि सहायक। आज मैं आपके क्षेत्र के मौसम या खेती से जुड़े कार्यों में कैसे सहायता कर सकता हूँ?",
            "hi-Latn": "Namaste! Main WeatherGPT hoon, aapka weather aur farming sahayak. Aaj main aapke area ke mausam ya kheti me kaise madad kar sakta hoon?",
            "mr": "नमस्कार! मी वेदरजीपीटी (WeatherGPT) आहे, आपला हवामान व शेती सहाय्यक. मी आज आपल्याला कशी मदत करू शकतो?",
            "kok": "नमस्कार! हांव वेदरजीपीटी (WeatherGPT), तुमचो हवामान आनी शेती सांगाती. आयज हांव तुमकां कशी मदत करूंक शकता?",
            "en": "Hello! I am WeatherGPT, your conversational weather and agricultural intelligence assistant. How can I help you with weather forecasts or farming decisions today?",
        }
        return {
            "answer": smalltalk_map.get(detected_lang, smalltalk_map["en"]),
            "intent": "smalltalk",
            "domain": "smalltalk",
            "location": None,
            "language": detected_lang,
            "sources": [],
            "temporal_target": temporal_target,
            "detected_language": detected_lang,
            "weather_used": False,
            "location_required": False,
            "weather": None,
            "alerts": [],
            "advisories": [],
        }

    # 3. First-Stage Filter: Ambiguous queries without prior context
    if intent_info.get("is_ambiguous") or domain == "ambiguous":
        clarification_text = intent_info.get("clarification_prompt") or {
            "hi": "कृपया स्पष्ट करें कि आप किस गतिविधि या मौसम की जानकारी के बारे में पूछ रहे हैं? जैसे कि क्या आप बाहर जाने, मछली पकड़ने, खेती के काम की योजना बना रहे हैं या बारिश व तापमान जानना चाहते हैं?",
            "hi-Latn": "Kripya batayein ki aap kis cheez ke baare me pooch rahe hain? Jaise fishing, travel, kheti, ya fir rain aur temperature?",
            "mr": "कृपया स्पष्ट करा की आपण कोणत्या कामासाठी किंवा हवामानाच्या घटकाबाबत विचारत आहात? जसे की प्रवास, मासेमारी, शेतीची कामे किंवा पाऊस आणि तापमान?",
            "kok": "उपकार करून स्पश्ट करात की तुमी खंयच्या कामा खातीर वा हवामाना विशीं विचारतात? जशें की भोंवडी, मासेमारी, शेतकाम वा पावस आनी तापमान?",
            "en": "Could you please specify what activity or weather detail you would like to know about? For example, are you planning travel, fishing, outdoor work, or checking for rain or temperature?",
        }.get(detected_lang, "Could you please specify what activity or weather detail you would like to know about? For example, are you planning travel, fishing, outdoor work, or checking for rain or temperature?")
        return {
            "answer": clarification_text,
            "intent": "ambiguous",
            "domain": "ambiguous",
            "location": None,
            "language": detected_lang,
            "sources": [],
            "temporal_target": temporal_target,
            "detected_language": detected_lang,
            "weather_used": False,
            "location_required": False,
            "weather": None,
            "alerts": [],
            "advisories": [],
        }

    # -------------------------------------------------------------
    # SECTION 11 & SECTION 8: LOCATION RESOLUTION PIPELINE
    # -------------------------------------------------------------
    # 1. Parse application location from request payload
    app_loc_name: str | None = None
    app_lat: float | None = req.latitude
    app_lon: float | None = req.longitude

    if isinstance(req.location, dict):
        app_loc_name = req.location.get("displayName") or req.location.get("name")
        if req.location.get("latitude") is not None:
            try:
                app_lat = float(req.location["latitude"])
            except (ValueError, TypeError):
                pass
        if req.location.get("longitude") is not None:
            try:
                app_lon = float(req.location["longitude"])
            except (ValueError, TypeError):
                pass
    elif isinstance(req.location, str) and req.location.strip():
        app_loc_name = req.location.strip()

    # 2. Extract explicit query location
    raw_query_location = intent_info.get("location_query")
    location_source = "application"
    weather_lat: float | None = None
    weather_lon: float | None = None
    resolved_location: str = ""

    # Priority 1: Explicit location in CURRENT query
    if raw_query_location:
        try:
            q_lat, q_lon, q_name = await weather_service.geocode(raw_query_location)
            weather_lat = q_lat
            weather_lon = q_lon
            resolved_location = q_name
            location_source = "query"
        except Exception as geo_err:
            logger.warning("Failed to geocode query location '%s': %s", raw_query_location, geo_err)
            if app_loc_name:
                resolved_location = app_loc_name
                weather_lat = app_lat
                weather_lon = app_lon
                location_source = "application"
            elif app_lat is not None and app_lon is not None:
                weather_lat = app_lat
                weather_lon = app_lon
                resolved_location = f"Lat {app_lat:.2f}, Lon {app_lon:.2f}"
                location_source = "application"
            else:
                raise HTTPException(status_code=404, detail=f"Could not find location '{raw_query_location}'.")
    # Priority 2: Selected application location
    elif app_loc_name or (app_lat is not None and app_lon is not None):
        location_source = "application"
        resolved_location = app_loc_name or f"Lat {app_lat:.2f}, Lon {app_lon:.2f}"
        weather_lat = app_lat
        weather_lon = app_lon
    # Priority 3: Neither exists -> Ask user to choose a location
    else:
        location_prompt_map = {
            "hi": "कृपया पहले अपना स्थान चुनें ताकि मैं आपको सटीक स्थानीय मौसम जानकारी दे सकूँ।",
            "hi-Latn": "Kripya pehle apna location select karein taaki main aapko sahi mausam ki jaankari de sakun.",
            "mr": "कृपया प्रथम आपले स्थान निवडा जेणेकरून मी आपल्याला अचूक स्थानिक हवामान माहिती देऊ शकेन.",
            "kok": "उपकार करून पयलीं तुमची सुवात निवडा, जेणेंकरून हांव अचूक हवामान म्हायती दिवंक शकेन.",
            "gu": "કૃપા કરીને પહેલાં તમારું સ્થાન પસંદ કરો જેથી હું તમને સચોટ સ્થાનિક હવામાન માહિતી આપી શકું.",
            "bn": "সঠিক স্থানীয় আবহাওয়া তথ্য পেতে অনুগ্রহ করে প্রথমে আপনার অবস্থান নির্বাচন করুন।",
            "ta": "துல்லியமான உள்ளூர் வானிலை தகவலைப் பெற முதலில் உங்கள் இருப்பிடத்தைத் தேர்ந்தெடுக்கவும்.",
            "te": "ఖచ్చితమైన స్థానిక వాతావరణ సమాచారాన్ని అందించడానికి దयచేసి ముందుగా మీ స్థానాన్ని ఎంచుకోండి.",
            "kn": "ನಿಖರವಾದ ಸ್ಥಳೀಯ ಹವಾಮಾನ ಮಾಹಿತಿಯನ್ನು ಪಡೆಯಲು ದಯವಿಟ್ಟು ಮೊದಲು ನಿಮ್ಮ ಸ್ಥಳವನ್ನು ಆಯ್ಕೆಮಾಡಿ.",
            "en": "Please choose a location first so I can give you accurate local weather information.",
        }
        return {
            "answer": location_prompt_map.get(detected_lang, location_prompt_map["en"]),
            "intent": domain,
            "location": None,
            "language": detected_lang,
            "sources": [],
            "domain": domain,
            "temporal_target": temporal_target,
            "detected_language": detected_lang,
            "weather_used": False,
            "location_required": True,
            "weather": None,
            "alerts": [],
            "advisories": [],
        }

    # 3. Retrieve live weather data with coordinate and identity validation
    try:
        weather = await weather_service.get_current_and_forecast(
            location=resolved_location,
            latitude=weather_lat,
            longitude=weather_lon,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Weather data service temporarily unavailable: {exc}",
        )

    # 4. Validate Section 15 Location Identity
    retrieved_loc_name = weather.get("location", resolved_location)
    req_loc_meta = {"name": resolved_location, "latitude": weather_lat, "longitude": weather_lon}
    ret_loc_meta = {"name": retrieved_loc_name, "latitude": weather.get("latitude"), "longitude": weather.get("longitude")}
    loc_val_pass, loc_val_reason = query_engine.validate_location_identity(req_loc_meta, ret_loc_meta)
    loc_val_status = "PASS" if loc_val_pass else f"FAIL ({loc_val_reason})"

    # If location validation fails (e.g. unexpected foreign data returned), re-fetch using canonical coordinates
    if not loc_val_pass:
        logger.warning("Location validation failed (%s). Re-fetching for '%s'", loc_val_reason, resolved_location)
        try:
            canon_lat, canon_lon, canon_name = await weather_service.geocode(resolved_location)
            weather = await weather_service.get_current_and_forecast(
                location=canon_name,
                latitude=canon_lat,
                longitude=canon_lon,
            )
            retrieved_loc_name = weather.get("location", canon_name)
            loc_val_status = "PASS"
        except Exception as e:
            logger.error("Failed to recover via geocoding for '%s': %s", resolved_location, e)

    weather_coords_str = f"{weather.get('latitude', weather_lat)}, {weather.get('longitude', weather_lon)}"

    # 4. Retrieve domain-specific data selectively
    # FORECAST questions must NOT retrieve or return warning data
    is_warning_query = (
        getattr(intent_info, "requires_alerts", False)
        or getattr(intent_info, "requires_warning", False)
        or domain in ["alerts", "warning", "cyclone"]
        or intent_info.intent in ["official_warning", "cyclone_warning", "alerts"]
        or (("warning" in query.lower() or "alert" in query.lower() or "चेतावनी" in query)
            and not any(ws in query.lower() for ws in ["weather", "forecast", "mausam", "temperature", "rain"]))
    )

    alerts_data = []
    if is_warning_query:
        alerts_data = rag_service.get_official_warnings(resolved_location)

    evaluated_advisories = []
    ag_operations = None
    requires_ag = getattr(intent_info, "requires_agriculture", False) or domain in ["agriculture", "spraying", "irrigation", "harvesting"]
    if requires_ag:
        search_query = f"{query} {req.crop}" if req.crop else query
        raw_advisories = rag_service.retrieve_advisory(query=search_query)
        evaluated_advisories = rag_service.evaluate_triggers(raw_advisories, weather)
        ag_operations = {
            "spray": advisory_service.evaluate_spray_safety(weather),
            "irrigation": advisory_service.evaluate_irrigation_safety(weather),
            "harvest": advisory_service.evaluate_harvest_safety(weather),
            "sowing": advisory_service.evaluate_sowing_safety(weather, crop=req.crop),
        }

    # Retrieve authoritative RAG meteorological context ONLY for alerts or agriculture
    rag_docs = []
    if is_warning_query or requires_ag:
        rag_docs = rag_service.retrieve_meteorological_context(
            query=query,
            location=resolved_location,
            intent=domain,
            crop=req.crop,
            target_date=temporal_target,
        )

    # 5. Build compact structured "verified context" (Golden Rule: LLM only receives verified facts)
    verified_context = query_engine.build_verified_context(
        query=query,
        intent_info=intent_info,
        weather_data=weather,
        advisory_data=evaluated_advisories,
        alerts_data=alerts_data,
        language=detected_lang,
        rag_documents=rag_docs,
    )

    # 6. Attempt grounded LLM synthesis via Ollama with verified context
    answer = await llm_service.generate_grounded_answer(
        query=query,
        domain=domain,
        weather_data=weather,
        advisory_data=evaluated_advisories,
        alerts_data=alerts_data,
        language=detected_lang,
        verified_context=verified_context,
    )

    # 7. Validate LLM response (numeric safety, no code blocks, zero leaked English in Hindi, location safety)
    is_valid = False
    validation_status = "LLM_OFFLINE_OR_EMPTY"
    if answer:
        valid_struct, reason = query_engine.validate_llm_answer(answer, verified_context, detected_lang)
        if valid_struct:
            is_valid = llm_service.validate_numeric_safety(
                llm_answer=answer,
                weather_data=weather,
                advisory_data=evaluated_advisories,
                alerts_data=alerts_data,
            )
            validation_status = "PASSED" if is_valid else "FAILED_NUMERIC_SAFETY"
        else:
            validation_status = f"REJECTED_{reason}"

    # 8. If Ollama is offline or produced invalid output, use deterministic human sentence generator
    raw_llm_answer = answer
    if not answer or not is_valid:
        answer = query_engine.generate_human_deterministic_answer(
            verified_context=verified_context,
            language=detected_lang,
        )

    # Determine accurate data source provenance
    if is_warning_query:
        sources = ["IMD — Official Warning"]
        source_details = {
            "forecast": "Open-Meteo (Numerical Forecast Model)",
            "warnings": "IMD (Authoritative Warnings & Bulletins)",
        }
    elif requires_ag:
        sources = ["Open-Meteo — Forecast", "IMD — Agromet Advisory"]
        source_details = {
            "forecast": "Open-Meteo (Numerical Forecast Model)",
            "advisory": "IMD (Agromet Advisory Bulletins)",
        }
    else:
        sources = ["Open-Meteo — Forecast"]
        source_details = {
            "forecast": "Open-Meteo (Numerical Forecast Model)",
        }

    duration_ms = round((time.time() - start_time) * 1000, 2)

    # Section 29 Debug Logging
    sec29_log = (
        "\n========================================\n"
        "NEW CHAT QUERY\n"
        "========================================\n\n"
        f"Raw query:\n{query}\n\n"
        f"App location:\n{app_loc_name or 'null'}\n\n"
        f"Query location:\n{raw_query_location or 'null'}\n\n"
        f"Location source:\n{location_source}\n\n"
        f"Resolved location:\n{resolved_location}\n\n"
        f"Intent:\n{intent_info.get('intent')}\n\n"
        f"Date:\n{verified_context.get('date_intent', 'today')}\n\n"
        f"Previous context inherited:\n{str(intent_info.get('inherit_context', False)).lower()}\n\n"
        f"Weather coordinates:\n{weather_coords_str}\n\n"
        f"Retrieved location:\n{retrieved_loc_name}\n\n"
        f"Location validation:\n{loc_val_status}\n\n"
        "========================================\n"
    )
    print(sec29_log)
    logger.info(sec29_log)

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
        "inherit_context": intent_info.get("inherit_context", False),
        "language": detected_lang,
        "sources": sources,
        "source_details": source_details,
        "rag_count": len(rag_docs),
        "response_time_ms": duration_ms,
        "detected_language": detected_lang,
        "weather_used": True,
        "location_required": False,
        "weather": {
            "source": weather.get("source"),
            "location": weather.get("location"),
            "current": weather.get("current"),
            "forecast": weather.get("forecast"),
        },
        "alerts": alerts_data,
        "advisories": evaluated_advisories,
        "operations": ag_operations,
    }
