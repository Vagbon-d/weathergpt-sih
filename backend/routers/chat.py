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

import re
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

router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    location: str | None = None
    language: str = "en"
    latitude: float | None = None
    longitude: float | None = None
    history: list[dict[str, Any]] | None = None
    crop: str | None = None


@router.post("/chat")
async def chat(req: ChatRequest):
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
    domain = intent_info["intent"]
    temporal_target = intent_info["temporal_target"]

    # Handle out-of-domain general knowledge questions politely without requiring location
    if intent_info.get("is_unrelated"):
        unrelated_map = {
            "hi": "मैं केवल आपके क्षेत्र के मौसम, मौसम चेतावनी, खेती के निर्णयों और मौसम-संबंधी योजना में सहायता कर सकता हूँ।",
            "hi-Latn": "Main keval aapke area ke mausam, weather alerts, kheti ke faislon aur weather planning me madad kar sakta hoon.",
            "mr": "मी फक्त आपल्या परिसरातील हवामान, हवामान इशारे, शेतीचे निर्णय आणि हवामानाच्या नियोजनात मदत करू शकतो.",
            "kok": "हांव फक्त हवामान, इशारे आनी शेती कामां विशीं मदत करूंक शकता.",
            "en": "I can help with weather, weather warnings, farming decisions, and weather-related planning for your location.",
        }
        return {
            "answer": unrelated_map.get(detected_lang, unrelated_map["en"]),
            "intent": "general",
            "location": None,
            "language": detected_lang,
            "sources": [],
            "domain": "general",
            "temporal_target": temporal_target,
            "detected_language": detected_lang,
            "weather_used": False,
            "location_required": False,
            "weather": None,
            "alerts": [],
            "advisories": [],
        }

    # Critical requirement: Weather/Alert/Ag queries require an explicit location
    has_coords = req.latitude is not None and req.longitude is not None
    has_named_location = bool(req.location and req.location.strip())

    if not has_coords and not has_named_location:
        location_prompt_map = {
            "hi": "कृपया पहले अपना स्थान चुनें ताकि मैं आपको सटीक स्थानीय मौसम जानकारी दे सकूँ।",
            "hi-Latn": "Kripya pehle apna location select karein taaki main aapko sahi mausam ki jaankari de sakun.",
            "mr": "कृपया प्रथम आपले स्थान निवडा जेणेकरून मी आपल्याला अचूक स्थानिक हवामान माहिती देऊ शकेन.",
            "kok": "उपकार करून पयलीं तुमची सुवात निवडा, जेणेंकरून हांव अचूक हवामान म्हायती दिवंक शकेन.",
            "gu": "કૃપા કરીને પહેલાં તમારું સ્થાન પસંદ કરો જેથી હું તમને સચોટ સ્થાનિક હવામાન માહિતી આપી શકું.",
            "bn": "সঠিক স্থানীয় আবহাওয়া তথ্য পেতে অনুগ্রহ করে প্রথমে আপনার অবস্থান নির্বাচন করুন।",
            "ta": "துல்லியமான உள்ளூர் வானிலை தகவலைப் பெற முதலில் உங்கள் இருப்பிடத்தைத் தேர்ந்தெடுக்கவும்.",
            "te": "ఖచ్చితమైన స్థానిక వాతావరణ సమాచారాన్ని అందించడానికి దయచేసి ముందుగా మీ స్థానాన్ని ఎంచుకోండి.",
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

    # 3. Retrieve live weather data (via coordinates or location name)
    try:
        if has_coords:
            weather = await weather_service.get_current_and_forecast(
                latitude=req.latitude, longitude=req.longitude
            )
        else:
            weather = await weather_service.get_current_and_forecast(location=req.location)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Weather data service temporarily unavailable: {exc}",
        )

    resolved_location = weather.get("location", req.location or "Selected Location")

    # 4. Retrieve domain-specific data selectively
    alerts_data = []
    if domain in ["warning", "cyclone", "alert"] or "warn" in query.lower() or "चेतावनी" in query:
        alerts_data = rag_service.get_alerts(resolved_location)

    evaluated_advisories = []
    ag_operations = None
    if domain in ["agriculture", "spraying", "irrigation", "harvesting"]:
        search_query = f"{query} {req.crop}" if req.crop else query
        raw_advisories = rag_service.retrieve_advisory(query=search_query)
        evaluated_advisories = rag_service.evaluate_triggers(raw_advisories, weather)
        ag_operations = {
            "spray": advisory_service.evaluate_spray_safety(weather),
            "irrigation": advisory_service.evaluate_irrigation_safety(weather),
            "harvest": advisory_service.evaluate_harvest_safety(weather),
            "sowing": advisory_service.evaluate_sowing_safety(weather, crop=req.crop),
        }

    # 5. Build compact structured "verified context" (Golden Rule: LLM only receives verified facts)
    verified_context = query_engine.build_verified_context(
        query=query,
        intent_info=intent_info,
        weather_data=weather,
        advisory_data=evaluated_advisories,
        alerts_data=alerts_data,
        language=detected_lang,
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

    # 7. Validate LLM response (numeric safety, no code blocks, zero leaked English in Hindi)
    is_valid = False
    if answer:
        valid_struct, reason = query_engine.validate_llm_answer(answer, verified_context, detected_lang)
        if valid_struct:
            is_valid = llm_service.validate_numeric_safety(
                llm_answer=answer,
                weather_data=weather,
                advisory_data=evaluated_advisories,
                alerts_data=alerts_data,
            )

    # 8. If Ollama is offline or produced invalid output, use deterministic human sentence generator
    if not answer or not is_valid:
        answer = query_engine.generate_human_deterministic_answer(
            verified_context=verified_context,
            language=detected_lang,
        )

    return {
        "answer": answer,
        "intent": domain,
        "temporal_target": temporal_target,
        "location": resolved_location,
        "language": detected_lang,
        "sources": ["Open-Meteo", "IMD"],
        "domain": domain,
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
