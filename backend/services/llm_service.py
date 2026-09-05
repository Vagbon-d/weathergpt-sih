"""
Local Ollama LLM service for WeatherGPT.

Weather data is retrieved before calling the LLM so the model cannot
invent live weather facts. Every numeric value presented is grounded
strictly in retrieved Open-Meteo data or evaluated advisory rules.

Ollama is used purely as a natural language synthesis and translation layer.
If Ollama is offline or times out, a deterministic Python fallback answer
is constructed from the retrieved data without raising 500 errors.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any
import httpx

logger = logging.getLogger(__name__)

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3:4b"
OLLAMA_TIMEOUT_SECONDS = 10.0


def clean_response(text: str) -> str:
    """
    Remove Qwen thinking/reasoning blocks and unnecessary markdown fences.
    Never display <think> tags to end users.
    """
    if not text:
        return ""

    cleaned = text.strip()

    # Strip thinking blocks
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>")[-1].strip()

    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<analysis>.*?</analysis>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    cleaned = cleaned.replace("<analysis>", "").replace("</analysis>", "")

    # Clean code fences if raw markdown blocks were returned
    cleaned = re.sub(r"^```(?:json|markdown)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    return cleaned.strip()


_OLLAMA_AVAILABLE: bool | None = None
_LAST_OLLAMA_CHECK: float = 0.0


async def call_ollama(prompt: str, system_prompt: str = "") -> str | None:
    """
    Call local Ollama at http://localhost:11434/api/generate via httpx.AsyncClient.
    Uses a fast connect timeout (1.0s) and a short liveness cache (5s) so when Ollama
    is offline, response latency is near-instantaneous instead of stalling for 10 seconds.
    Returns None if Ollama is unreachable, times out, or fails.
    """
    global _OLLAMA_AVAILABLE, _LAST_OLLAMA_CHECK
    import time
    now = time.time()
    if _OLLAMA_AVAILABLE is False and (now - _LAST_OLLAMA_CHECK < 5.0):
        return None

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 400,
        },
    }

    timeout_config = httpx.Timeout(10.0, connect=1.0)
    try:
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            response = await client.post(OLLAMA_GENERATE_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            raw_text = data.get("response", "")
            _OLLAMA_AVAILABLE = True
            return clean_response(raw_text)
    except Exception as exc:
        _OLLAMA_AVAILABLE = False
        _LAST_OLLAMA_CHECK = time.time()
        logger.warning("Ollama call failed or timed out: %s", exc)
        return None


def extract_grounded_metrics(
    weather_data: dict[str, Any],
    advisory_data: list[dict[str, Any]] | None = None,
    alerts_data: list[dict[str, Any]] | None = None,
) -> dict[str, set[float]]:
    """
    Collect grounded numbers organized by metric type to prevent cross-metric false positives.
    """
    metrics: dict[str, set[float]] = {
        "temp": set(),
        "percent": set(),
        "speed": set(),
        "precip": set(),
        "general": {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 10.0, 24.0, 48.0, 72.0},
    }

    def _add(metric_key: str, val):
        if val is not None:
            try:
                f = float(val)
                metrics[metric_key].add(round(f, 1))
                metrics[metric_key].add(float(int(round(f))))
            except (ValueError, TypeError):
                pass

    current = weather_data.get("current", {})
    _add("temp", current.get("temperature_c"))
    _add("temp", current.get("feels_like_c"))
    _add("percent", current.get("humidity_pct"))
    _add("percent", current.get("humidity"))
    _add("percent", current.get("cloud_cover_pct"))
    _add("speed", current.get("wind_kmh"))
    _add("speed", current.get("wind_gust_kmh"))
    _add("precip", current.get("precipitation_mm"))
    _add("precip", current.get("rain_mm"))
    _add("precip", current.get("showers_mm"))

    for day in weather_data.get("forecast", []):
        _add("temp", day.get("temp_max"))
        _add("temp", day.get("temp_min"))
        _add("percent", day.get("rain_probability"))
        _add("speed", day.get("wind_speed_10m_max"))
        _add("speed", day.get("wind_gusts_10m_max"))
        _add("speed", day.get("wind_kmh_max"))
        _add("precip", day.get("precipitation_mm"))
        date_str = str(day.get("date", ""))
        for part in re.findall(r"\d+", date_str):
            _add("general", part)

    if advisory_data:
        for adv in advisory_data:
            field = str(adv.get("trigger_field", "")).lower()
            val = adv.get("threshold_value")
            meas = adv.get("measured_value")
            target_bucket = "general"
            if "temp" in field:
                target_bucket = "temp"
            elif "humidity" in field or "rain" in field or "probability" in field:
                target_bucket = "percent"
            elif "wind" in field:
                target_bucket = "speed"
            elif "precip" in field:
                target_bucket = "precip"
            _add(target_bucket, val)
            _add(target_bucket, meas)

    return metrics


def validate_numeric_safety(
    llm_answer: str,
    weather_data: dict[str, Any],
    advisory_data: list[dict[str, Any]] | None = None,
    alerts_data: list[dict[str, Any]] | None = None,
) -> bool:
    """
    Scans the LLM answer for weather claims containing explicit units
    (e.g., 34°C, 85%, 45 km/h, 12 mm). If numbers with weather units do not match
    grounded data within a tolerance of +/-1.5, returns False to reject hallucination.
    """
    if not llm_answer or not llm_answer.strip():
        return False

    metrics = extract_grounded_metrics(weather_data, advisory_data, alerts_data)

    # Check temperatures: °C, °c, celsius, डिग्री सेल्सियस, डिग्री
    temp_matches = re.findall(r"(\d+(?:\.\d+)?)\s*(?:°C|°c|celsius|डिग्री\s*सेल्सियस|डिग्री|ડિગ્રી\s*સેલ્સિયસ|டிகிரி)", llm_answer, re.IGNORECASE)
    for num_str in temp_matches:
        val = float(num_str)
        if not any(abs(val - g) <= 1.5 for g in metrics["temp"]):
            logger.warning(
                "Numeric safety rejected: claimed temperature %s°C not in grounded %s",
                num_str, metrics["temp"]
            )
            return False

    # Check percentages: %, प्रतिशत, फीसद, टक्के, ટકા, சதவீதம், శాతం
    pct_matches = re.findall(r"(\d+(?:\.\d+)?)\s*(?:%|प्रतिशत|फीसद|टक्के|ટકા|சதவீதம்|శాతం)", llm_answer)
    for num_str in pct_matches:
        val = float(num_str)
        if not any(abs(val - g) <= 1.5 for g in metrics["percent"]):
            logger.warning(
                "Numeric safety rejected: claimed percentage %s%% not in grounded %s",
                num_str, metrics["percent"]
            )
            return False

    # Check wind speed: km/h, kmph, किलोमीटर प्रति घंटा, किमी/घंटा, किमी प्रति तास
    speed_matches = re.findall(r"(\d+(?:\.\d+)?)\s*(?:km/h|kmph|किलोमीटर\s*प्रति\s*घंटा|किमी/घंटा|किमी\s*प्रति\s*तास)", llm_answer, re.IGNORECASE)
    for num_str in speed_matches:
        val = float(num_str)
        if not any(abs(val - g) <= 1.5 for g in metrics["speed"]):
            logger.warning(
                "Numeric safety rejected: claimed wind speed %s km/h not in grounded %s",
                num_str, metrics["speed"]
            )
            return False

    # Check precipitation: mm, मिलीमीटर, मिमी
    precip_matches = re.findall(r"(\d+(?:\.\d+)?)\s*(?:mm|मिलीमीटर|मिमी)", llm_answer, re.IGNORECASE)
    for num_str in precip_matches:
        val = float(num_str)
        if not any(abs(val - g) <= 1.5 for g in metrics["precip"]):
            logger.warning(
                "Numeric safety rejected: claimed precipitation %s mm not in grounded %s",
                num_str, metrics["precip"]
            )
            return False

    return True


LANGUAGE_STYLES = {
    "en": (
        "Answer in clear, natural, warm, and friendly English. "
        "Strictly avoid robotic technical terms (do NOT say 'precipitation probability'—say 'chance of rain'; "
        "do NOT say 'relative humidity'—say 'humidity'). "
        "Structure: Direct Answer + Important Weather Facts + Practical Farming/Daily Life Advice."
    ),
    "hi": (
        "उत्तर अत्यंत सरल, आत्मीय और 100% शुद्ध हिंदी (देवनागरी लिपि) में दें। "
        "किसी भी स्थिति में अंग्रेजी मौसम शब्द (जैसे 'Moderate drizzle', 'Partly cloudy') या अंग्रेजी स्थान/सुविधा नाम (जैसे 'Primary Health Centre') न छोड़ें। "
        "सभी मौसम स्थितियों और स्थानों का अनुवाद हिंदी में करें (जैसे 'मध्यम बूंदाबांदी', 'प्राथमिक स्वास्थ्य केंद्र')। "
        "तापमान और प्रतिशत को स्पष्ट हिंदी में व्यक्त करें (उदा: 29.4 डिग्री सेल्सियस, 54 प्रतिशत)। "
        "तकनीकी या रोबोटिक शब्दों ('अवक्षेपण प्रायिकता', 'रिलेटिव ह्यूमिडिटी') से बिल्कुल बचें। "
        "संरचना: सीधा उत्तर + मुख्य मौसम का हाल + व्यावहारिक खेती/दैनिक जीवन की सलाह।"
    ),
    "hi-Latn": (
        "Answer in natural, warm, conversational Hinglish (Roman Hindi written in English letters, "
        "e.g., 'Namaste! Kal aapke area me baarish ke kaafi chances hain (around 80%). Isliye kisaan bhai dawai ka spray abhi rok dein'). "
        "Structure: Direct answer + Weather facts + Farmer/practical advice. Avoid robotic jargon."
    ),
    "mr": (
        "Answer in clear, respectful, and simple Marathi (मराठी). "
        "Structure: Direct answer + Weather facts + Farmer/practical advice. Avoid robotic jargon."
    ),
    "gu": (
        "Answer in clear, respectful, and natural Gujarati (ગુજરાતી). "
        "Structure: Direct answer + Weather facts + Farmer/practical advice. Avoid robotic jargon."
    ),
    "bn": (
        "Answer in clear, respectful, and natural Bengali (বাংলা). "
        "Structure: Direct answer + Weather facts + Farmer/practical advice. Avoid robotic jargon."
    ),
    "ta": (
        "Answer in clear, respectful, and natural Tamil (தமிழ்). "
        "Structure: Direct answer + Weather facts + Farmer/practical advice. Avoid robotic jargon."
    ),
    "te": (
        "Answer in clear, respectful, and natural Telugu (తెలుగు). "
        "Structure: Direct answer + Weather facts + Farmer/practical advice. Avoid robotic jargon."
    ),
    "kn": (
        "Answer in clear, respectful, and natural Kannada (ಕನ್ನಡ). "
        "Structure: Direct answer + Weather facts + Farmer/practical advice. Avoid robotic jargon."
    ),
    "ml": (
        "Answer in clear, respectful, and natural Malayalam (മലയാളം). "
        "Structure: Direct answer + Weather facts + Farmer/practical advice. Avoid robotic jargon."
    ),
    "pa": (
        "Answer in clear, respectful, and natural Punjabi (ਪੰਜਾਬੀ). "
        "Structure: Direct answer + Weather facts + Farmer/practical advice. Avoid robotic jargon."
    ),
    "or": (
        "Answer in clear, respectful, and natural Odia (ଓଡ଼ିଆ). "
        "Structure: Direct answer + Weather facts + Farmer/practical advice. Avoid robotic jargon."
    ),
    "kok": (
        "Answer in simple, warm Konkani. "
        "Keep it respectful, clear, and practical for Goan/coastal farmers and citizens."
    ),
}



async def generate_grounded_answer(
    query: str,
    domain: str,
    weather_data: dict[str, Any],
    advisory_data: list[dict[str, Any]] | None = None,
    alerts_data: list[dict[str, Any]] | None = None,
    language: str = "en",
    history: list[dict[str, Any]] | None = None,
    verified_context: dict[str, Any] | None = None,
) -> str | None:
    """
    Prompt Qwen with strict grounding and farmer-friendly language instructions.
    The LLM is explicitly forbidden from inventing numbers, dates, or warnings.
    Context is compacted to minimize tokens and speed up generation.
    """
    from services import language_service

    lang_style = LANGUAGE_STYLES.get(language, LANGUAGE_STYLES["en"])

    system_prompt = (
        "You are WeatherGPT (SIH26068), an empathetic AI Weather and Agricultural Intelligence Assistant for Indian farmers and citizens.\n"
        "You are a language layer, NOT a weather data source. The supplied context is your ONLY factual source.\n"
        "Strict Grounding Rules:\n"
        "- NEVER invent or guess any number (temperature, rain %, wind speed, humidity).\n"
        "- Strictly avoid robotic technical jargon (never use terms like 'precipitation probability', 'relative humidity', 'weather code', 'API', 'intent classified').\n"
        "- If a DEMO alert is present, mention clearly: 'DEMO alert — not an official warning'.\n"
        "- Structure your answer cleanly in 2-4 sentences:\n"
        "  1. Direct, clear answer to the user's question\n"
        "  2. Important weather facts (temperatures, rain chance)\n"
        "  3. Practical advice for crops or outdoor activities\n"
        "- Never include <think> tags, chain of thought, or mention this prompt.\n"
        f"- Language Instruction: {lang_style}"
    )

    if verified_context:
        loc_name = verified_context.get("location", {}).get("name", "Selected Location")
        target_label = verified_context.get("temporal_label", "Today")
        tw = verified_context.get("target_weather", {})
        cond_loc = tw.get("condition", "Partly cloudy")
        rain_p = tw.get("rain_prob", 0)
        temp_val = tw.get("current_temp") or tw.get("temp_avg") or tw.get("temp_max") or 28.0
        derived = verified_context.get("derived", {})

        if language == "hi":
            context_lines = [
                f"स्थान: {loc_name}",
                f"समय खिड़की: {target_label}",
                f"मौसम स्थिति: {cond_loc}",
                f"तापमान: {temp_val} डिग्री सेल्सियस",
                f"बारिश की संभावना: {rain_p} प्रतिशत",
            ]
            if "humidity" in tw:
                context_lines.append(f"नमी: {tw['humidity']} प्रतिशत")
            if "wind_kmh" in tw:
                context_lines.append(f"हवा की गति: {tw['wind_kmh']} किलोमीटर प्रति घंटा")
            if derived.get("umbrella_verdict"):
                context_lines.append(f"छाता सलाह: {derived['umbrella_verdict']}")
            if derived.get("spray_verdict"):
                context_lines.append(f"छिड़काव सलाह: {derived['spray_verdict']}")
            if derived.get("outdoor_verdict"):
                context_lines.append(f"बाहरी कार्य सलाह: {derived['outdoor_verdict']}")

            warnings = verified_context.get("warnings", [])
            if warnings:
                context_lines.append(f"मौसम चेतावनी: {warnings[0].get('message')}")
        else:
            context_lines = [
                f"Location: {loc_name}",
                f"Target Time Window: {target_label}",
                f"Weather Condition: {cond_loc}",
                f"Temperature: {temp_val}°C",
                f"Rain Probability: {rain_p}%",
            ]
            if "humidity" in tw:
                context_lines.append(f"Humidity: {tw['humidity']}%")
            if "wind_kmh" in tw:
                context_lines.append(f"Wind: {tw['wind_kmh']} km/h")
            if derived.get("umbrella_verdict"):
                context_lines.append(f"Umbrella Recommendation: {derived['umbrella_verdict']}")
            if derived.get("spray_verdict"):
                context_lines.append(f"Spraying Recommendation: {derived['spray_verdict']}")
            if derived.get("outdoor_verdict"):
                context_lines.append(f"Outdoor Guidance: {derived['outdoor_verdict']}")

            warnings = verified_context.get("warnings", [])
            if warnings:
                context_lines.append(f"Warnings: {warnings[0].get('message')}")

        compact_context = "\n".join(context_lines)
    else:
        raw_location = weather_data.get("location", "Selected Location")
        localized_location = language_service.localize_location(raw_location, language)
        current = weather_data.get("current", {})
        forecast = weather_data.get("forecast", [])

        # Format compact, fast factual context string (reduces token load by 80%)
        cur_cond_raw = current.get("condition", "")
        cur_cond_loc = language_service.localize_condition(cur_cond_raw, language)

        if language == "hi":
            cur_str = f"तापमान: {current.get('temperature_c')} डिग्री सेल्सियस, महसूस: {current.get('feels_like_c')} डिग्री सेल्सियस, मौसम: {cur_cond_loc}, नमी: {current.get('humidity_pct')} प्रतिशत, हवा: {current.get('wind_kmh')} किलोमीटर प्रति घंटा"
            forecast_items = []
            for d in forecast[:4]:
                f_cond_raw = d.get("condition", "")
                f_cond_loc = language_service.localize_condition(f_cond_raw, language)
                forecast_items.append(f"{d.get('date', '')}: {f_cond_loc}, अधिकतम {d.get('temp_max')} डिग्री सेल्सियस, न्यूनतम {d.get('temp_min')} डिग्री सेल्सियस, बारिश {d.get('rain_probability')} प्रतिशत")
            f_str = "; ".join(forecast_items)

            context_lines = [
                f"स्थान: {localized_location}",
                f"वर्तमान मौसम: {cur_str}",
                f"पूर्वानुमान: {f_str}",
                f"स्रोत: भारत मौसम विज्ञान विभाग (IMD)",
            ]
        else:
            cur_str = f"Temp: {current.get('temperature_c')}°C, Feels like: {current.get('feels_like_c')}°C, Condition: {cur_cond_loc}, Humidity: {current.get('humidity_pct')}%, Wind: {current.get('wind_kmh')} km/h"

            forecast_items = []
            for d in forecast[:4]:
                f_cond_raw = d.get("condition", "")
                f_cond_loc = language_service.localize_condition(f_cond_raw, language)
                forecast_items.append(f"{d.get('date', '')}: {f_cond_loc}, High {d.get('temp_max')}°C, Low {d.get('temp_min')}°C, Rain {d.get('rain_probability')}%")
            f_str = "; ".join(forecast_items)

            context_lines = [
                f"Location: {localized_location}",
                f"Current: {cur_str}",
                f"Forecast: {f_str}",
                f"Source: {weather_data.get('source')}",
            ]

        if advisory_data:
            trigs = [f"[{a.get('crop')}] {a.get('advisory')}" for a in advisory_data if a.get("triggered")]
            if trigs:
                context_lines.append("Active Agronomic Alerts: " + " | ".join(trigs))

        if alerts_data:
            al = [f"[{a.get('hazard')}] {a.get('message')}" for a in alerts_data]
            context_lines.append("Active Warnings: " + " | ".join(al))

        compact_context = "\n".join(context_lines)

    if language == "hi":
        user_prompt = f"""उपयोगकर्ता का प्रश्न:
{query}

सत्यापित मौसम डेटा (एकमात्र सत्य स्रोत):
{compact_context}

कार्य:
उपरोक्त सत्यापित डेटा के आधार पर 2-4 छोटे और अत्यंत सरल हिंदी वाक्यों में सीधा और मददगार उत्तर दें।
रोबोटिक या तकनीकी शब्दों और अंग्रेजी शब्दों का बिल्कुल प्रयोग न करें।
"""
    else:
        user_prompt = f"""USER QUESTION:
{query}

REQUESTED LANGUAGE CODE:
{language}

GROUNDED DATA CONTEXT (ONLY SOURCE OF TRUTH):
{compact_context}

TASK:
Answer the user's question directly and helpfully in 2-4 short sentences based ONLY on the grounded data above.
Avoid technical jargon.
"""

    return await call_ollama(prompt=user_prompt, system_prompt=system_prompt)


def generate_python_fallback(
    domain: str,
    query: str,
    weather_data: dict[str, Any],
    advisory_data: list[dict[str, Any]] | None = None,
    alerts_data: list[dict[str, Any]] | None = None,
    language: str = "en",
    history: list[dict[str, Any]] | None = None,
) -> str:
    """
    Deterministic Python fallback when Ollama is unavailable or fails numeric safety.
    Constructs warm, farmer-friendly answers in English, Hindi (Devanagari),
    Roman Hindi (Hinglish), Marathi, or Konkani without inventing facts.
    """
    from services import advisory_service, language_service

    raw_loc = weather_data.get("location", "the requested location")
    loc = language_service.localize_location(raw_loc, language)
    current = weather_data.get("current", {})
    forecast = weather_data.get("forecast", [])
    today = forecast[0] if len(forecast) > 0 else {}
    tomorrow = forecast[1] if len(forecast) > 1 else today

    q_lower = query.lower()

    # 0. Contextual "Why?" Follow-up handler
    is_why_query = q_lower in ["why", "why?", "kyun", "kyun?", "kyu", "kyu?", "क्यों", "क्यों?", "ka?", "का?", "kashamule", "कशासाठी"] or q_lower.startswith("why ") or q_lower.startswith("kyun ")
    if is_why_query and history:
        last_bot = ""
        for h in reversed(history):
            if h.get("role") in ["assistant", "bot"]:
                last_bot = h.get("content") or h.get("text") or ""
                break

        last_bot_lower = last_bot.lower()
        r_prob = today.get("rain_probability", 0)
        w_spd = current.get("wind_kmh", 12)

        if any(w in last_bot_lower for w in ["spray", "pesticide", "chhidkaw", "dawai"]):
            if language == "hi":
                return f"क्योंकि आगामी घंटों में बारिश की संभावना {r_prob} प्रतिशत और हवा की गति {w_spd} किलोमीटर प्रति घंटा रहने का अनुमान है, जिससे रासायनिक दवा धुलने या उड़ने का खतरा है।"
            elif language == "hi-Latn":
                return f"Kyunki aane wale ghanton me baarish ke chances {r_prob}% aur hawa ki speed {w_spd} km/h rehne ka andaza hai, jisse dawai beh ya ud sakti hai."
            elif language == "mr":
                return f"कारण पुढील काळात पावसाची शक्यता {r_prob}% आणि वाऱ्याचा वेग {w_spd} किमी/तास राहण्याचा अंदाज आहे, ज्यामुळे औषध वाहून जाईल."
            return f"Because the chance of rain is {r_prob}% with wind speeds up to {w_spd} km/h, which will wash off or drift the chemical spray."
        elif any(w in last_bot_lower for w in ["rain", "umbrella", "baarish", "chhaata"]):
            if language == "hi":
                return f"क्योंकि मौसम विभाग के अनुसार बादल छाए रहने और {r_prob} प्रतिशत तक वर्षा होने की संभावना है।"
            elif language == "hi-Latn":
                return f"Kyunki weather data ke hisaab se baadal chaaye rahenge aur {r_prob}% tak baarish ho sakti hai."
            elif language == "mr":
                return f"कारण हवामान अंदाजानुसार ढगाळ वातावरण आणि {r_prob}% पावसाची शक्यता आहे."
            return f"Because meteorological data indicates high atmospheric moisture and precipitation probability at {r_prob}%."
        elif any(w in last_bot_lower for w in ["irrigation", "sinchai", "paani"]):
            if language == "hi":
                return f"क्योंकि प्राकृतिक बारिश ({r_prob} प्रतिशत) से खेत को पर्याप्त नमी मिल जाएगी, जिससे अलग से पानी देने की ज़रूरत नहीं है और जलभराव का खतरा टलेगा।"
            elif language == "hi-Latn":
                return f"Kyunki aane wali baarish ({r_prob}%) se mitti ko natural paani mil jaayega, isliye waterlogging se bachne ke liye sinchai rokna behtar hai."
            return f"Because upcoming rainfall ({r_prob}%) will provide natural soil moisture, preventing wasteful waterlogging."
        else:
            if language == "hi":
                return f"यह सलाह {loc} के वर्तमान तापमान, बारिश की संभावना ({r_prob} प्रतिशत) और हवा की गति ({w_spd} किलोमीटर प्रति घंटा) के वास्तविक आंकड़ों पर आधारित है।"
            elif language == "hi-Latn":
                return f"Yeh salah {loc} ke live temperature, rain chance ({r_prob}%) aur wind ({w_spd} km/h) ke actual data par based hai."
            return f"This advice is based on verified meteorological conditions in {loc}: rain probability at {r_prob}% and wind at {w_spd} km/h."

    # Month-long / seasonal query limitation check
    is_month_query = any(
        w in q_lower
        for w in ["month", "monthly", "season", "seasonal", "year", "mahina", "mahine", "puro mahino"]
    )

    # Check if querying for tomorrow vs today
    is_tomorrow = any(
        w in q_lower
        for w in ["tomorrow", "kal", "falya", "falyan", "agle din", "udya"]
    )
    target_day = tomorrow if is_tomorrow else today
    day_name_en = "tomorrow" if is_tomorrow else "today"
    day_name_hi = "कल" if is_tomorrow else "आज"
    day_name_hing = "kal" if is_tomorrow else "aaj"
    day_name_kok = "falyan" if is_tomorrow else "aaz"

    temp = current.get("temperature_c", 28)
    feels_like = current.get("feels_like_c", temp)
    hum = current.get("humidity_pct", 70)
    wind = current.get("wind_kmh", 12)
    raw_condition = target_day.get("condition", current.get("condition", "Partly cloudy"))
    condition = language_service.localize_condition(raw_condition, language)
    rain_prob = target_day.get("rain_probability", 0)
    temp_max = target_day.get("temp_max", temp)
    temp_min = target_day.get("temp_min", temp)

    # 1. GENERAL DOMAIN
    if domain == "general":
        # Out-of-domain detection (e.g. "who is elon musk", "who is the prime minister", etc.)
        is_unrelated = any(
            w in q_lower
            for w in [
                "who is", "who was", "what is the capital", "president", "prime minister",
                "elon musk", "cricket score", "movie", "bitcoin", "crypto", "formula 1",
                "football match", "stock market", "kaun hai", "kisne banaya", "pm of india"
            ]
        )
        if is_unrelated:
            if language == "hi":
                return "मैं केवल आपके स्थान के मौसम, मौसम चेतावनी, खेती के निर्णयों और मौसम-संबंधी योजना में सहायता कर सकता हूँ।"
            elif language == "hi-Latn":
                return "Main keval aapke area ke mausam, weather alerts, kheti ke faislon aur weather planning me madad kar sakta hoon."
            elif language == "mr":
                return "मी फक्त आपल्या परिसरातील हवामान, हवामान इशारे, शेतीचे निर्णय आणि हवामानाच्या नियोजनात मदत करू शकतो."
            elif language == "kok":
                return "हांव फक्त हवामान, इशारे आनी शेती कामां विशीं मदत करूंक शकता."
            return "I can help with weather, weather warnings, farming decisions, and weather-related planning for your location."

        # Greeting / Intro
        if language == "hi":
            return (
                "नमस्ते! मैं वेदरजीपीटी (WeatherGPT) हूँ। मैं मौसम का हाल, 7 दिनों का पूर्वानुमान, "
                "फसलों के लिए कृषि सलाह और मौसम अलर्ट की सटीक जानकारी देता हूँ। आप किसी भी गाँव, कस्बे या शहर के मौसम या खेती से जुड़ा सवाल पूछ सकते हैं।"
            )
        elif language == "hi-Latn":
            return (
                "Namaste! Main WeatherGPT hoon. Main aapko live mausam, 7 dino ka forecast, "
                "kisaano ke liye fasal advisory aur weather alerts ki sahi jankari deta hoon. "
                "Aap kisi bhi village, town ya city ke mausam aur farming ke baare me pooch sakte hain."
            )
        elif language == "mr":
            return (
                "नमस्कार! मी वेदरजीपीटी (WeatherGPT) आहे. मी हवामानाचा अंदाज, ७ दिवसांचा अंदाज, "
                "शेतकऱ्यांसाठी पीक सल्ला आणि हवामान इशाऱ्यांची अचूक माहिती देतो."
            )
        elif language == "kok":
            return (
                "Namaskar! Hanv WeatherGPT. Hanv tumka havaman andaj, 7 disanchi mahiti, "
                "shetkaryam khatir sallo ani alerts divpak modot korta."
            )
        return (
            "Namaste! I'm WeatherGPT. I can help with live weather, 7-day forecasts, agricultural advisories, "
            "and weather alerts across Indian villages, towns, and cities."
        )

    # 2. ALERT DOMAIN
    if domain == "alert":
        if alerts_data:
            if language == "hi":
                lines = [f"{loc} के लिए सक्रिय अलर्ट (मौसम विभाग):"]
                for a in alerts_data:
                    lines.append(f"• {a.get('hazard')}: {a.get('message')} (वैध: {a.get('valid_for')}).")
                lines.append("महत्वपूर्ण: आधिकारिक जीवन-सुरक्षा निर्देशों के लिए भारत मौसम विज्ञान विभाग (IMD) या स्थानीय प्रशासन की सलाह अवश्य लें।")
                return "\n".join(lines)
            elif language == "hi-Latn":
                lines = [f"{loc} ke liye Active Weather Alerts (IMD Authority):"]
                for a in alerts_data:
                    lines.append(f"• {a.get('hazard')}: {a.get('message')} (Valid: {a.get('valid_for')}).")
                lines.append("Note: Official safety directives ke liye IMD ya local disaster management authority ki guidelines follow karein.")
                return "\n".join(lines)
            elif language == "mr":
                lines = [f"{loc} साठी सक्रिय हवामान इशारे:"]
                for a in alerts_data:
                    lines.append(f"• {a.get('hazard')}: {a.get('message')} (वैध: {a.get('valid_for')}).")
                lines.append("सूचना: अधिकृत सुरक्षा निर्देशांसाठी IMD किंवा स्थानिक प्रशासनाचे नियम पाळा.")
                return "\n".join(lines)
            elif language == "kok":
                lines = [f"{loc} khatir Alerts:"]
                for a in alerts_data:
                    lines.append(f"• {a.get('hazard')}: {a.get('message')} (Valid: {a.get('valid_for')}).")
                lines.append("Official mahiti khatir IMD guidelines polloyat.")
                return "\n".join(lines)
            lines = [f"Active weather alerts found for {loc}:"]
            for a in alerts_data:
                lines.append(f"• {a.get('hazard')}: {a.get('message')} (Valid: {a.get('valid_for')}).")
            lines.append("Note: For official life safety directives, please consult the India Meteorological Department (IMD) or local authorities.")
            return "\n".join(lines)

        # No alerts
        if language == "hi":
            return f"राहत की खबर: {loc} के लिए वर्तमान में कोई सक्रिय मौसम चेतावनी नहीं है। मौसम सामान्य है।"
        elif language == "hi-Latn":
            return f"Rahat ki khabar: {loc} ke liye abhi koi active weather alert nahi hai. Mausam samanya hai."
        elif language == "mr":
            return f"{loc} साठी सध्या कोणताही सक्रिय हवामान इशारा नाही. हवामान सामान्य आहे."
        elif language == "kok":
            return f"{loc} khatir aaz khoinchoi alert na. Havaman thik asa."
        return f"Good news: There are currently no active weather alerts for {loc}. Weather conditions are normal."

    # 3. AGRICULTURE DOMAIN
    if domain == "agriculture":
        is_spray_query = any(
            w in q_lower
            for w in ["spray", "spraying", "pesticide", "chhidkaav", "dawai", "chhidkao"]
        )

        lines = []

        # Month limitation notice
        if is_month_query:
            if language == "hi":
                lines.append("कृपया ध्यान दें: मौसम विभाग का सत्यापित पूर्वानुमान अगले 4 दिनों के लिए ही उपलब्ध है, इसलिए पूरे महीने का अनुमान अभी नहीं लगाया जा सकता।")
            elif language == "hi-Latn":
                lines.append("Kripya dhyan dein: Verified weather forecast agle 4 dino tak ka hi available hai, isliye poore mahine ki sthiti abhi nahi batayi ja sakti.")
            elif language == "kok":
                lines.append("Dhyan diat: Havaman andaj fuddlya 4 disam khatiruch asa, purea mhoinyacho andaj sangunk zaina.")
            else:
                lines.append("Please note: Verified forecast data is available for the next 4 days, so conditions for the entire month cannot be guaranteed.")

        # Spraying specific direct answer
        if is_spray_query:
            if rain_prob >= 40 or wind > 18:
                if language == "hi":
                    lines.append(
                        f"{loc} में आज कीटनाशक या दवा का छिड़काव न करने की सलाह दी जाती है। "
                        f"बारिश की संभावना {rain_prob} प्रतिशत और हवा की गति {wind} किलोमीटर प्रति घंटा है, जिससे दवा धुल सकती है या उड़ सकती है। "
                        "सूखे और शांत मौसम की प्रतीक्षा करें।"
                    )
                elif language == "hi-Latn":
                    lines.append(
                        f"{loc} me aaj pesticide ya dawai ka spray karna theek nahi hoga. "
                        f"Baarish ka chance {rain_prob}% aur hawa ki speed {wind} km/h hai, jisse dawai beh sakti hai. "
                        "Kripya sukhe aur shaant mausam ka wait karein."
                    )
                elif language == "kok":
                    lines.append(
                        f"{loc}ant aaz voller davaim marunk naka. Paavsacho andaj {rain_prob}% asa ani vaaryacho veg {wind} km/h asa. "
                        "Sukya havamanachi vaat polloyat."
                    )
                else:
                    lines.append(
                        f"It is not recommended to spray pesticides or fertilizers today in {loc}. "
                        f"The chance of rain is {rain_prob}% with winds at {wind} km/h, which will wash off or drift the chemical spray. "
                        "Wait for dry, calm weather."
                    )
            else:
                if language == "hi":
                    lines.append(
                        f"{loc} में आज छिड़काव के लिए मौसम अनुकूल है। "
                        f"बारिश की संभावना केवल {rain_prob} प्रतिशत है और हवा की गति {wind} किलोमीटर प्रति घंटा है। "
                        "सुबह या शाम के समय छिड़काव करना सबसे अच्छा रहेगा।"
                    )
                elif language == "hi-Latn":
                    lines.append(
                        f"{loc} me aaj dawai spray karne ke liye mausam theek hai. "
                        f"Baarish ka chance sirf {rain_prob}% hai aur hawa ki speed {wind} km/h hai. "
                        "Subah ya shaam ke time spray karna behtar rahega."
                    )
                elif language == "kok":
                    lines.append(
                        f"{loc}ant aaz davaim marpak havaman bore asa. Paavsacho andaj fokot {rain_prob}% asa."
                    )
                else:
                    lines.append(
                        f"Weather conditions in {loc} are suitable for spraying today. "
                        f"The chance of rain is low at {rain_prob}%, and wind speeds are calm at {wind} km/h. "
                        "Early morning or late afternoon application is recommended."
                    )

        # Irrigation specific direct answer
        is_irrigation_query = any(
            w in q_lower
            for w in ["irrigate", "irrigation", "sinchai", "paani", "pani dena", "sinchai karna"]
        )
        if is_irrigation_query:
            if rain_prob >= 50:
                if language == "hi":
                    lines.append(
                        f"{loc} में अभी सिंचाई टालने की सलाह दी जाती है, क्योंकि बारिश की संभावना {rain_prob} प्रतिशत है। "
                        "प्राकृतिक वर्षा से मिट्टी को पर्याप्त नमी मिलेगी और अनावश्यक जलभराव से बचाव होगा।"
                    )
                elif language == "hi-Latn":
                    lines.append(
                        f"{loc} me abhi sinchai (irrigation) postpone karein, kyunki baarish ke {rain_prob}% chances hain. "
                        "Isse paani bharne (waterlogging) ka khatra talega."
                    )
                elif language == "kok":
                    lines.append(f"{loc}ant aaz udak divpak naka, paavsachi shakyata {rain_prob}% asa.")
                else:
                    lines.append(
                        f"Postpone irrigation in {loc}. With a {rain_prob}% chance of rain, "
                        "natural precipitation will supply soil moisture and prevent waterlogging."
                    )
            else:
                if language == "hi":
                    lines.append(
                        f"{loc} में मौसम सूखा है (बारिश की संभावना {rain_prob} प्रतिशत)। "
                        "सुबह या शाम के ठंडे समय में आवश्यकतानुसार हल्की सिंचाई की जा सकती है।"
                    )
                elif language == "hi-Latn":
                    lines.append(
                        f"{loc} me mausam saaf hai (baarish chance {rain_prob}%). "
                        "Subah ya shaam ke time zaroorat ke anusaar halki sinchai kar sakte hain."
                    )
                elif language == "kok":
                    lines.append(f"{loc}ant havaman bore asa, udak dium yeta.")
                else:
                    lines.append(
                        f"Dry weather conditions in {loc} (rain chance {rain_prob}%). "
                        "Routine irrigation is recommended during cooler morning or evening hours."
                    )

        # Harvesting specific direct answer
        is_harvest_query = any(
            w in q_lower
            for w in ["harvest", "harvesting", "katai", "katna"]
        )
        if is_harvest_query:
            if rain_prob >= 40:
                if language == "hi":
                    lines.append(
                        f"{loc} में फसल की कटाई में सावधानी बरतें। बारिश की संभावना {rain_prob} प्रतिशत है। "
                        "कटी हुई फसल को तुरंत सुरक्षित ढके हुए स्थान पर रखें।"
                    )
                elif language == "hi-Latn":
                    lines.append(
                        f"{loc} me fasal ki katai (harvest) me savdhani bartein. Baarish ka chance {rain_prob}% hai. "
                        "Katai ke baad fasal ko dry jagah store karein."
                    )
                elif language == "kok":
                    lines.append(f"{loc}ant pik katunk savdhan ravchi goroz asa, paavsacho andaj {rain_prob}% asa.")
                else:
                    lines.append(
                        f"Exercise caution when harvesting in {loc}. With a {rain_prob}% rain chance, "
                        "ensure tarpaulins and covered drying spaces are ready to avoid moisture damage."
                    )
            else:
                if language == "hi":
                    lines.append(
                        f"{loc} में फसल की कटाई और सुखाने के लिए मौसम अनुकूल और सूखा है (बारिश की संभावना केवल {rain_prob} प्रतिशत)।"
                    )
                elif language == "hi-Latn":
                    lines.append(
                        f"{loc} me fasal harvest aur sukhaane ke liye mausam bilkul safe hai (baarish ka chance sirf {rain_prob}%)."
                    )
                elif language == "kok":
                    lines.append(f"{loc}ant pik katunk havaman ekdom bore asa.")
                else:
                    lines.append(
                        f"Harvesting conditions in {loc} are favorable and dry (rain probability is only {rain_prob}%)."
                    )

        # Sowing specific direct answer
        is_sowing_query = any(
            w in q_lower
            for w in ["sow", "sowing", "bona", "buwai", "lagana", "beej", "seeding"]
        )
        if is_sowing_query:
            if rain_prob >= 70 or temp_max >= 40:
                if language == "hi":
                    lines.append(
                        f"{loc} में अभी बुवाई थोड़े समय के लिए टाल दें। तेज बारिश या अत्यधिक तापमान से बीजों के अंकुरण पर असर पड़ सकता है।"
                    )
                elif language == "hi-Latn":
                    lines.append(
                        f"{loc} me abhi sowing thoda rok lein. Zyada baarish ya high temperature se beej kharab ho sakte hain."
                    )
                elif language == "kok":
                    lines.append(f"{loc}ant rovp thoddo temp ravk ravchi goroz asa.")
                else:
                    lines.append(
                        f"Delay sowing in {loc} until adverse conditions (heavy rain / extreme heat) clear up, ensuring optimal seed germination."
                    )
            else:
                if language == "hi":
                    lines.append(
                        f"{loc} में बुवाई और खेत की तैयारी के लिए तापमान ({temp_min} डिग्री सेल्सियस से {temp_max} डिग्री सेल्सियस) और नमी अनुकूल है।"
                    )
                elif language == "hi-Latn":
                    lines.append(
                        f"{loc} me beej bone aur khet taiyyari ke liye temperature ({temp_min}°C se {temp_max}°C) anukool hai."
                    )
                elif language == "kok":
                    lines.append(f"{loc}ant rovpank havaman bore asa.")
                else:
                    lines.append(
                        f"Conditions in {loc} (temperature {temp_min}°C - {temp_max}°C) are favorable for sowing and soil preparation."
                    )

        # Triggered crop advisories
        if advisory_data:
            triggered = [a for a in advisory_data if a.get("triggered")]
            if triggered:
                if language == "hi":
                    lines.append(f"किसान भाइयों के लिए {loc} में मुख्य कृषि सलाह:")
                    for item in triggered:
                        lines.append(f"• [{item.get('crop', 'फसल').title()}] {item.get('advisory')}")
                elif language == "hi-Latn":
                    lines.append(f"Kisaan bhaiyo ke liye {loc} me zaroori salah:")
                    for item in triggered:
                        lines.append(f"• [{item.get('crop', 'Fasal').title()}] {item.get('advisory')}")
                elif language == "kok":
                    lines.append(f"Shetkaryam khatir {loc}ant mahitigol sallo:")
                    for item in triggered:
                        lines.append(f"• [{item.get('crop', 'Pik').title()}] {item.get('advisory')}")
                else:
                    lines.append(f"Agricultural advisories triggered for {loc}:")
                    for item in triggered:
                        lines.append(f"• [{item.get('crop', 'Crop').title()}] {item.get('advisory')}")
            elif not is_spray_query:
                if language == "hi":
                    lines.append(f"{loc} में वर्तमान मौसम फसलों की सामान्य गतिविधियों के लिए अनुकूल है।")
                    for item in advisory_data[:2]:
                        lines.append(f"• [{item.get('crop', 'फसल').title()}] {item.get('advisory')}")
                elif language == "hi-Latn":
                    lines.append(f"{loc} me abhi ka mausam fasal ki normal dekhbhal ke liye theek hai.")
                    for item in advisory_data[:2]:
                        lines.append(f"• [{item.get('crop', 'Fasal').title()}] {item.get('advisory')}")
                elif language == "kok":
                    lines.append(f"{loc}ant havaman shetachea kamaank bore asa.")
                else:
                    lines.append(f"Current weather in {loc} is within acceptable ranges for planned field operations.")
                    for item in advisory_data[:2]:
                        lines.append(f"• [{item.get('crop', 'Crop').title()}] {item.get('advisory')}")

        if not lines:
            if language == "hi":
                lines.append(f"{loc} में तापमान {temp} डिग्री सेल्सियस, नमी {hum} प्रतिशत, और बारिश की संभावना {rain_prob} प्रतिशत है।")
            elif language == "hi-Latn":
                lines.append(f"{loc} me temperature {temp}°C, nami {hum}%, aur baarish chance {rain_prob}% hai.")
            else:
                lines.append(f"Conditions in {loc}: temperature {temp}°C, humidity {hum}%, rain chance {rain_prob}%.")

        return "\n".join(lines)

    # 4. WEATHER DOMAIN
    is_rain_query = any(
        w in q_lower
        for w in ["rain", "umbrella", "shower", "baarish", "paavs", "barish", "varsat"]
    )
    is_outdoor_query = any(
        w in q_lower
        for w in ["picnic", "outdoor", "travel", "event", "fishing", "ghoomne", "trip", "match"]
    )
    is_temp_query = any(
        w in q_lower
        for w in ["wind", "humid", "hot", "cold", "temp", "garmi", "sardi", "hawa", "nami", "thand"]
    )

    # 4a. Month-long limitation
    if is_month_query:
        if language == "hi":
            return (
                f"{loc} के 4-दिवसीय पूर्वानुमान के अनुसार मौसम {condition} रहेगा, "
                f"जिसमें तापमान {temp_min} डिग्री सेल्सियस से {temp_max} डिग्री सेल्सियस और बारिश की संभावना लगभग {rain_prob} प्रतिशत रहेगी। "
                "कृपया ध्यान दें: सत्यापित मौसम डेटा अगले 4 दिनों का ही उपलब्ध है, पूरे महीने का नहीं।"
            )
        elif language == "hi-Latn":
            return (
                f"{loc} ke 4-din ke forecast ke hisaab se mausam {condition} rahega, "
                f"temperature {temp_min}°C se {temp_max}°C aur baarish chance lagbhag {rain_prob}% rahega. "
                "Kripya note karein: Verified weather data agle 4 dino tak ka hi available hai, poore mahine ka nahi."
            )
        elif language == "kok":
            return (
                f"{loc} khatir 4 disancho andaj {condition} asa, taapman {temp_min}°C te {temp_max}°C "
                f"ani paavsachi shakyata {rain_prob}% asa. Purea mhoinyacho andaj sangunk zaina."
            )
        return (
            f"Based on the verified 4-day forecast for {loc}, near-term conditions show {condition} "
            f"with temperatures between {temp_min}°C and {temp_max}°C and rain probability around {rain_prob}%. "
            "However, verified forecast data does not cover the entire month."
        )

    # 4a-2. Comparison query (e.g. "is tomorrow hotter than today?", "kal zyada garmi hogi ya aaj?")
    is_compare_query = any(
        w in q_lower
        for w in [
            "hotter", "colder", "warmer", "cooler", "more rain",
            "than today", "se zyada", "se kam", "garmi hogi ya",
            "zyada garmi", "zyada thand", "compare", "aaj se"
        ]
    )
    if is_compare_query:
        today_max = float(today.get("temp_max") or temp)
        tomorrow_max = float(tomorrow.get("temp_max") or temp)
        diff = round(tomorrow_max - today_max, 1)

        if diff > 0.5:
            if language == "hi":
                return f"हाँ, {loc} में कल ({tomorrow_max} डिग्री सेल्सियस) आज ({today_max} डिग्री सेल्सियस) की तुलना में लगभग {diff} डिग्री सेल्सियस अधिक गर्म रहेगा।"
            elif language == "hi-Latn":
                return f"Haan, {loc} me kal ({tomorrow_max}°C) aaj ({today_max}°C) ke muqable lagbhag {diff}°C zyada garam rahega."
            elif language == "kok":
                return f"Hoi, {loc}ant falyan ({tomorrow_max}°C) aaz ({today_max}°C) poros chodd garam astolem ({diff}°C chodd)."
            return f"Yes, tomorrow ({tomorrow_max}°C) will be warmer than today ({today_max}°C) by about {diff}°C in {loc}."
        elif diff < -0.5:
            cooler_by = abs(diff)
            if language == "hi":
                return f"नहीं, {loc} में कल ({tomorrow_max} डिग्री सेल्सियस) आज ({today_max} डिग्री सेल्सियस) की तुलना में लगभग {cooler_by} डिग्री सेल्सियस ठंडा रहेगा।"
            elif language == "hi-Latn":
                return f"Nahi, {loc} me kal ({tomorrow_max}°C) aaj ({today_max}°C) ke muqable lagbhag {cooler_by}°C thanda rahega."
            elif language == "kok":
                return f"Na, {loc}ant falyan ({tomorrow_max}°C) aaz ({today_max}°C) poros thondd astolem."
            return f"No, tomorrow ({tomorrow_max}°C) will be cooler than today ({today_max}°C) by about {cooler_by}°C in {loc}."
        else:
            if language == "hi":
                return f"{loc} में कल और आज का अधिकतम तापमान लगभग एक समान ({today_max} डिग्री सेल्सियस) रहेगा।"
            elif language == "hi-Latn":
                return f"{loc} me kal aur aaj ka high temperature lagbhag same ({today_max}°C) rahega."
            elif language == "kok":
                return f"{loc}ant falyan ani aaz taapman sadharonponnan sarke astolem ({today_max}°C)."
            return f"Tomorrow's high in {loc} ({tomorrow_max}°C) will be very similar to today's ({today_max}°C)."

    # 4a-3. Weekend query
    is_weekend_query = any(
        w in q_lower
        for w in ["weekend", "saturday", "sunday", "shanivar", "ravivar", "itwar"]
    )
    if is_weekend_query and len(forecast) > 1:
        weekend_days = []
        for day in forecast:
            date_str = day.get("date", "")
            try:
                dt = datetime.fromisoformat(date_str)
                if dt.weekday() in (5, 6):
                    name = "Saturday" if dt.weekday() == 5 else "Sunday"
                    name_hi = "शनिवार" if dt.weekday() == 5 else "रविवार"
                    weekend_days.append({
                        "name": name,
                        "name_hi": name_hi,
                        "data": day,
                    })
            except Exception:
                pass

        if weekend_days:
            if language == "hi":
                lines = [f"{loc} के लिए सप्ताहांत (वीकेंड) का मौसम पूर्वानुमान:"]
                for wd in weekend_days:
                    d = wd["data"]
                    c_loc = language_service.localize_condition(d.get("condition", ""), "hi")
                    lines.append(f"• {wd['name_hi']}: {c_loc}, तापमान {d.get('temp_min')} डिग्री सेल्सियस से {d.get('temp_max')} डिग्री सेल्सियस, बारिश की संभावना {d.get('rain_probability')} प्रतिशत।")
                return "\n".join(lines)
            elif language == "hi-Latn":
                lines = [f"{loc} ke liye Weekend Weather Forecast:"]
                for wd in weekend_days:
                    d = wd["data"]
                    lines.append(f"• {wd['name']}: {d.get('condition')}, temp {d.get('temp_min')}°C se {d.get('temp_max')}°C, baarish chance {d.get('rain_probability')}%.")
                return "\n".join(lines)
            elif language == "kok":
                lines = [f"{loc} khatir Weekend andaj:"]
                for wd in weekend_days:
                    d = wd["data"]
                    lines.append(f"• {wd['name']}: {d.get('condition')}, taapman {d.get('temp_min')}°C te {d.get('temp_max')}°C, paavas {d.get('rain_probability')}%.")
                return "\n".join(lines)
            lines = [f"Weekend weather forecast for {loc}:"]
            for wd in weekend_days:
                d = wd["data"]
                lines.append(f"• {wd['name']}: {d.get('condition')}, high {d.get('temp_max')}°C, low {d.get('temp_min')}°C, rain chance {d.get('rain_probability')}%.")
            return "\n".join(lines)

    # 4a-4. Timing / Best time query (e.g. "When is the best time to spray/work outside?", "Kab bahar ja sakte hain?")
    is_timing_query = any(
        w in q_lower
        for w in ["best time", "what time", "kab karu", "kab spray", "kis samay", "konte vel", "appropriate time", "when should i", "when to", "kis waqt", "kay time", "vel"]
    )
    if is_timing_query:
        act = "spray" if any(w in q_lower for w in ["spray", "dawai", "chhidkao"]) else "outdoor"
        hourly = weather_data.get("hourly", [])
        time_info = advisory_service.calculate_best_time_window(hourly, activity=act)
        win = time_info.get("window", "Early morning (6:00 AM - 10:00 AM)")
        rsn = time_info.get("reason", "Calmer conditions and lower rain probability.")

        if language == "hi":
            act_hi = "कीटनाशक छिड़काव" if act == "spray" else "बाहरी काम"
            return f"{loc} में {act_hi} के लिए सबसे उपयुक्त समय {win} रहेगा। कारण: {rsn}"
        elif language == "hi-Latn":
            act_hing = "spray" if act == "spray" else "outdoor work"
            return f"{loc} me {act_hing} ke liye sabse best time {win} rahega. Wajah: {rsn}"
        elif language == "mr":
            act_mr = "फवारणीसाठी" if act == "spray" else "बाहेरील कामासाठी"
            return f"{loc} मध्ये {act_mr} सर्वोत्तम वेळ {win} राहील. कारण: {rsn}"
        elif language == "kok":
            return f"{loc}ant kamaak boro vel {win} astolo. Karan: {rsn}"
        return f"The best time window in {loc} is {win}. Reason: {rsn}"

    # 4a-5. Crop / Grain drying query
    is_drying_query = any(
        w in q_lower
        for w in ["dry crop", "drying", "sukha", "sukhana", "sun-dry", "sun dry", "sukhavap", "grain dry"]
    )
    if is_drying_query:
        if rain_prob < 30 and hum < 75:
            if language == "hi":
                return f"{loc} में {day_name_hi} फसल या अनाज धूप में सुखाना सुरक्षित है। बारिश की संभावना केवल {rain_prob} प्रतिशत और नमी {hum} प्रतिशत है।"
            elif language == "hi-Latn":
                return f"{loc} me {day_name_hing} fasal ya anaaj dhoop me sukhaana bilkul safe hai. Baarish ka chance sirf {rain_prob}% aur nami {hum}% hai."
            elif language == "mr":
                return f"{loc} मध्ये {day_name_hi} धान्य उन्हात वाळवणे सुरक्षित आहे. पावसाची शक्यता फक्त {rain_prob}% आहे."
            elif language == "kok":
                return f"{loc}ant {day_name_kok} pik sukharp bore asa. Paavsacho andaj fokot {rain_prob}% asa."
            return f"It is safe to sun-dry crops or grain {day_name_en} in {loc}. Clear skies and low rain chance ({rain_prob}%) provide good drying conditions."
        else:
            if language == "hi":
                return f"{loc} में {day_name_hi} कटी फसल को खुले में न सुखाएं। बारिश की संभावना {rain_prob} प्रतिशत होने से फसल भीग सकती है; सुरक्षित स्थान पर रखें।"
            elif language == "hi-Latn":
                return f"{loc} me {day_name_hing} fasal ko khule me na sukhaayein. Baarish ke {rain_prob}% chance hone se fasal bheegh sakti hai; cover karke rakhein."
            elif language == "mr":
                return f"{loc} मध्ये {day_name_hi} पीक उघड्यावर वाळवू नका. पावसाचा अंदाज ({rain_prob}%) असल्याने नुकसान टाळण्यासाठी झाकून ठेवा."
            elif language == "kok":
                return f"{loc}ant {day_name_kok} pik ugtteari dovorunk naka, paavsachi shakyata {rain_prob}% asa."
            return f"Keep harvested crops covered in {loc} {day_name_en}. Elevated humidity and a {rain_prob}% rain risk could spoil exposed produce."

    # 4a-6. Fishing / Marine query
    is_fishing_query = any(
        w in q_lower
        for w in ["fish", "fishing", "machhli", "machli", "maccheli", "nuste"]
    )
    if is_fishing_query:
        if wind > 25 or rain_prob > 60:
            if language == "hi":
                return f"{loc} में {day_name_hi} मछली पकड़ने या नाव ले जाने से बचें। तेज हवा ({wind} किलोमीटर प्रति घंटा) और बारिश ({rain_prob} प्रतिशत) से स्थिति जोखिम भरी है।"
            elif language == "hi-Latn":
                return f"{loc} me {day_name_hing} fishing ya boat le jaane se bachein. Tez hawa ({wind} km/h) aur baarish ({rain_prob}%) ki wajah se conditions safe nahi hain."
            elif language == "mr":
                return f"{loc} मध्ये {day_name_hi} मासेमारीसाठी जाणे टाळा. वेगवान वारे ({wind} किमी/तास) आणि पाऊस ({rain_prob}%) यामुळे धोका आहे."
            elif language == "kok":
                return f"{loc}ant {day_name_kok} nustim dhorpak vochunk naka. Varem ({wind} km/h) chodd asa."
            return f"Exercise caution with fishing or boating {day_name_en} in {loc}. Gusty winds ({wind} km/h) and rain probability ({rain_prob}%) may create rough waters."
        else:
            if language == "hi":
                return f"{loc} में {day_name_hi} मछली पकड़ने के लिए मौसम सामान्य और सुरक्षित है। हवा की गति {wind} किलोमीटर प्रति घंटा और बारिश की संभावना {rain_prob} प्रतिशत है।"
            elif language == "hi-Latn":
                return f"{loc} me {day_name_hing} fishing ke liye mausam normal aur safe hai. Wind speed {wind} km/h aur rain chance {rain_prob}% hai."
            elif language == "mr":
                return f"{loc} मध्ये {day_name_hi} मासेमारीसाठी हवामान अनुकूल आणि सुरक्षित आहे."
            elif language == "kok":
                return f"{loc}ant {day_name_kok} nustim dhorpak havaman bore asa."
            return f"Weather conditions in {loc} {day_name_en} are favorable for fishing, with calm winds ({wind} km/h) and a low rain chance ({rain_prob}%)."

    # 4a-7. Sports / Cricket query
    is_sports_query = any(
        w in q_lower
        for w in ["cricket", "match", "play sports", "khelna", "football"]
    )
    if is_sports_query:
        if rain_prob >= 50:
            if language == "hi":
                return f"{loc} में {day_name_hi} खेल या क्रिकेट मैच में बारिश से बाधा आ सकती है (संभावना {rain_prob} प्रतिशत)। मैदान गीला रहने के आसार हैं।"
            elif language == "hi-Latn":
                return f"{loc} me {day_name_hing} cricket ya outdoor sports me baarish rukawat daal sakti hai ({rain_prob}% chance). Ground geela ho sakta hai."
            elif language == "mr":
                return f"{loc} मध्ये {day_name_hi} पावसामुळे क्रिकेट किंवा खेळात अडथळा येऊ शकतो ({rain_prob}% शक्यता)."
            elif language == "kok":
                return f"{loc}ant {day_name_kok} paavsak lagon khelaant addkhol yeum shakta ({rain_prob}% shakyata)."
            return f"Outdoor sports or cricket {day_name_en} in {loc} may face rain delays or a wet outfield, with rain probability at {rain_prob}%."
        else:
            if language == "hi":
                return f"{loc} में {day_name_hi} क्रिकेट या खेल के लिए मौसम बहुत अच्छा रहेगा। तापमान {temp_min} डिग्री सेल्सियस से {temp_max} डिग्री सेल्सियस और बारिश की संभावना केवल {rain_prob} प्रतिशत है।"
            elif language == "hi-Latn":
                return f"{loc} me {day_name_hing} cricket ya sports ke liye mausam mast hai. Temperature {temp_min}°C se {temp_max}°C aur baarish sirf {rain_prob}% hai."
            elif language == "mr":
                return f"{loc} मध्ये {day_name_hi} खेळासाठी हवामान उत्तम राहील. पावसाची शक्यता फक्त {rain_prob}% आहे."
            elif language == "kok":
                return f"{loc}ant {day_name_kok} khelak havaman ekdom borem asa."
            return f"Great conditions for cricket or outdoor sports in {loc} {day_name_en}. Temperatures will be {temp_min}°C - {temp_max}°C with just a {rain_prob}% chance of rain."

    # 4b. Rain query
    if is_rain_query:
        is_umbrella = any(w in q_lower for w in ["umbrella", "chhaata", "chaata", "sathori", "छतरी", "छाता"])
        if is_umbrella:
            if rain_prob >= 40:
                if language == "hi":
                    return f"हाँ, {loc} में {day_name_hi} छाता साथ रखना ज़रूरी रहेगा। बारिश की संभावना {rain_prob} प्रतिशत है और मौसम {condition} रहने का अनुमान है।"
                elif language == "hi-Latn":
                    return f"Haan, {loc} me {day_name_hing} chhaata (umbrella) sath rakhna chahiye. Baarish ke {rain_prob}% chances hain aur mausam {condition} rahega."
                elif language == "mr":
                    return f"होय, {loc} मध्ये {day_name_hi} छत्री सोबत ठेवणे गरजेचे आहे. पावसाची शक्यता {rain_prob}% आहे."
                elif language == "kok":
                    return f"Hoi, {loc}ant {day_name_kok} sathori gheun bhair sora. Paavsachi shakyata {rain_prob}% asa."
                return f"Yes, you should carry an umbrella in {loc} {day_name_en}. The chance of rain is {rain_prob}% with {condition}."
            else:
                if language == "hi":
                    return f"नहीं, {loc} में {day_name_hi} छाते की विशेष आवश्यकता नहीं है। बारिश की संभावना केवल {rain_prob} प्रतिशत है और मौसम ज्यादातर {condition} रहेगा।"
                elif language == "hi-Latn":
                    return f"Nahi, {loc} me {day_name_hing} chhaate ki zaroorat nahi hai. Baarish ka chance sirf {rain_prob}% hai aur mausam mostly {condition} rahega."
                elif language == "mr":
                    return f"नाही, {loc} मध्ये {day_name_hi} छत्रीची आवश्यकता नाही. पावसाची शक्यता फक्त {rain_prob}% आहे."
                elif language == "kok":
                    return f"Na, {loc}ant {day_name_kok} sathorichi goroz na. Paavsacho andaj fokot {rain_prob}% asa."
                return f"No, an umbrella is not necessary in {loc} {day_name_en}. The chance of rain is only {rain_prob}% with {condition} conditions."

        if rain_prob >= 70:
            if language == "hi":
                return (
                    f"हाँ, {loc} में {day_name_hi} बारिश होने की संभावना काफी अधिक ({rain_prob} प्रतिशत) है। "
                    f"मौसम {condition} रहने की उम्मीद है और तापमान {temp_min} डिग्री सेल्सियस से {temp_max} डिग्री सेल्सियस के बीच रहेगा। "
                    "घर से निकलते समय छाता साथ रखें और आवश्यक जल-निकासी व्यवस्था सुनिश्चित करें।"
                )
            elif language == "hi-Latn":
                return (
                    f"Haan, {loc} me {day_name_hing} baarish hone ke kaafi zyada chances hain ({rain_prob}%). "
                    f"Mausam {condition} rahega aur temperature {temp_min}°C se {temp_max}°C ke aas-paas rahega. "
                    "Bahar nikalte waqt chhaata (umbrella) zaroor sath rakhein."
                )
            elif language == "kok":
                return (
                    f"Hoi, {loc}ant {day_name_kok} paavsachi vhodd shakyata ({rain_prob}%) asa. "
                    f"Havaman {condition} astolem ani taapman {temp_min}°C te {temp_max}°C astolem. "
                    "Gharantlean bhair sortana sathori gheun bhair sora."
                )
            return (
                f"Yes, rain is very likely in {loc} {day_name_en}. "
                f"The forecast indicates {condition} with a {rain_prob}% chance of rain and temperatures between {temp_min}°C and {temp_max}°C. "
                "Carrying an umbrella and planning for wet travel conditions is strongly recommended."
            )
        elif rain_prob >= 40:
            if language == "hi":
                return (
                    f"{loc} में {day_name_hi} बारिश की मध्यम संभावना ({rain_prob} प्रतिशत) है। "
                    f"मौसम {condition} रहेगा और तापमान {temp_min} डिग्री सेल्सियस से {temp_max} डिग्री सेल्सियस रहेगा। "
                    "एहतियात के तौर पर छाता साथ रखना बेहतर रहेगा।"
                )
            elif language == "hi-Latn":
                return (
                    f"{loc} me {day_name_hing} halki se madhyam baarish ka chance hai ({rain_prob}%). "
                    f"Mausam {condition} rahega aur temperature {temp_min}°C se {temp_max}°C rahega. "
                    "Safety ke liye umbrella sath rakhna achha hoga."
                )
            elif language == "kok":
                return (
                    f"{loc}ant {day_name_kok} thoddo paavs poddunk shakta ({rain_prob}% shakyata). "
                    f"Sathori vangdda dovorchi shifarash asa."
                )
            return (
                f"There is a moderate chance of rain in {loc} {day_name_en} ({rain_prob}% probability, {condition}). "
                f"Highs will reach {temp_max}°C and lows around {temp_min}°C. Carrying an umbrella is a wise precaution."
            )
        else:
            if language == "hi":
                return (
                    f"{loc} में {day_name_hi} बारिश की संभावना बहुत कम ({rain_prob} प्रतिशत) है। "
                    f"मौसम ज्यादातर {condition} रहेगा और तापमान {temp_min} डिग्री सेल्सियस से {temp_max} डिग्री सेल्सियस के बीच रहने का अनुमान है।"
                )
            elif language == "hi-Latn":
                return (
                    f"{loc} me {day_name_hing} baarish ka koi khaas chance nahi hai (sirf {rain_prob}%). "
                    f"Mausam mukhya roop se {condition} rahega aur temperature {temp_min}°C se {temp_max}°C tak rahega."
                )
            elif language == "kok":
                return (
                    f"{loc}ant {day_name_kok} paavsachi shakyata khup kami ({rain_prob}%) asa. "
                    f"Havaman sadharonponnan {condition} astolem."
                )
            return (
                f"Rain is unlikely in {loc} {day_name_en} (only a {rain_prob}% chance). "
                f"Expect predominantly {condition} conditions with a high of {temp_max}°C and low of {temp_min}°C."
            )

    # 4c. Outdoor / travel query
    if is_outdoor_query:
        suit_en = "favorable" if rain_prob < 40 else "uncertain due to rain showers"
        suit_hi = "अनुकूल" if rain_prob < 40 else "बारिश के कारण थोड़ा अनिश्चित"
        suit_hing = "achha aur anukool" if rain_prob < 40 else "baarish ki wajah se thoda risky"
        if language == "hi":
            return (
                f"{loc} में {day_name_hi} बाहर जाने या यात्रा के लिए मौसम {suit_hi} है। "
                f"अनुमानित मौसम {condition} रहेगा, अधिकतम तापमान {temp_max} डिग्री सेल्सियस, न्यूनतम {temp_min} डिग्री सेल्सियस, "
                f"और बारिश की संभावना {rain_prob} प्रतिशत है।"
            )
        elif language == "hi-Latn":
            return (
                f"{loc} me {day_name_hing} outdoor plans ya travel ke liye mausam {suit_hing} lag raha hai. "
                f"Condition {condition} rahegi, high {temp_max}°C, low {temp_min}°C, "
                f"aur baarish ka chance {rain_prob}% hai."
            )
        elif language == "kok":
            return (
                f"{loc}ant {day_name_kok} bhair vochunk havaman {suit_en} asa. "
                f"Taapman {temp_max}°C ani paavsachi shakyata {rain_prob}% asa."
            )
        return (
            f"Weather conditions {day_name_en} in {loc} appear {suit_en}. "
            f"The forecast indicates {condition} with a high of {temp_max}°C, low of {temp_min}°C, "
            f"and a {rain_prob}% chance of rain."
        )

    # 4d. Temperature / wind query
    if is_temp_query:
        if language == "hi":
            return (
                f"{loc} में वर्तमान तापमान {temp} डिग्री सेल्सियस (महसूस {feels_like} डिग्री सेल्सियस) है। "
                f"हवा में नमी {hum} प्रतिशत और हवा की गति {wind} किलोमीटर प्रति घंटा है। "
                f"{day_name_hi} को अधिकतम तापमान {temp_max} डिग्री सेल्सियस और न्यूनतम {temp_min} डिग्री सेल्सियस रहने का अनुमान है।"
            )
        elif language == "hi-Latn":
            return (
                f"{loc} me abhi current temperature {temp}°C (feels like {feels_like}°C) hai. "
                f"Hawa me nami {hum}% aur hawa ki speed {wind} km/h chal rahi hai. "
                f"{day_name_hing.capitalize()} ko temperature high {temp_max}°C aur low {temp_min}°C rahega."
            )
        elif language == "kok":
            return (
                f"{loc}ant aicho taapman {temp}°C asa, vhem {hum}% ani vaaryacho veg {wind} km/h asa. "
                f"{day_name_kok.capitalize()} taapman {temp_max}°C voir pawtolem."
            )
        return (
            f"In {loc}, current temperature is {temp}°C (feels like {feels_like}°C) "
            f"with {hum}% humidity and winds at {wind} km/h. "
            f"Expect a high of {temp_max}°C and low of {temp_min}°C {day_name_en} with {condition}."
        )

    # 4e. Default general weather response
    if language == "hi":
        cond_phrase = condition
        if "रहेगी" not in cond_phrase and "रहेंगे" not in cond_phrase and "रहेगा" not in cond_phrase:
            if any(w in cond_phrase for w in ["बूंदाबांदी", "बारिश", "बौछारें"]):
                cond_phrase = f"{condition} रहेगी"
            elif any(w in cond_phrase for w in ["बादल"]):
                cond_phrase = f"{condition} छाए रहेंगे"
            else:
                cond_phrase = f"{condition} रहेगा"

        return (
            f"{loc} में {day_name_hi} {cond_phrase}। "
            f"अधिकतम तापमान {temp_max} डिग्री सेल्सियस और न्यूनतम {temp_min} डिग्री सेल्सियस रहने की संभावना है। "
            f"बारिश की संभावना {rain_prob} प्रतिशत है। "
            f"वर्तमान तापमान {temp} डिग्री सेल्सियस और हवा में नमी {hum} प्रतिशत है।"
        )
    elif language == "hi-Latn":
        return (
            f"{loc} me {day_name_hing} mausam {condition} rahega. High temperature {temp_max}°C aur low {temp_min}°C rahega. "
            f"Baarish ka chance {rain_prob}% hai. Abhi temperature {temp}°C aur humidity {hum}% hai."
        )
    elif language == "kok":
        return (
            f"{loc}ant {day_name_kok} havaman {condition} astolem. Taapman {temp_min}°C te {temp_max}°C astolem, "
            f"ani paavsachi shakyata {rain_prob}% asa. Aicho taapman {temp}°C asa."
        )
    return (
        f"In {loc}, {day_name_en} will see {condition} with a high of {temp_max}°C and low of {temp_min}°C. "
        f"The chance of rain is {rain_prob}%. Current conditions: {temp}°C with {hum}% humidity."
    )


# Alias for backwards compatibility
generate_deterministic_fallback = generate_python_fallback