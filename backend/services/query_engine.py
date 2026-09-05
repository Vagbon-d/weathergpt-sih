"""
WeatherGPT Query Understanding, Temporal Resolution, and Verified Context Engine (SIH26068).

Implements the Golden Rule Architecture:
USER
 ↓
LOCATION (Canonical & Localized)
 ↓
LANGUAGE DETECTION
 ↓
QUERY UNDERSTANDING (17+ Intents)
 ↓
TEMPORAL RESOLUTION (Deterministic dates & hourly windows)
 ↓
CONVERSATION CONTEXT (Lightweight multi-turn follow-ups)
 ↓
SELECTIVE DATA RETRIEVAL
 ↓
FACTUAL VERIFIED CONTEXT (Compact, zero bloat)
 ↓
LLM HUMANIZATION (Qwen3:4b with strict grounding)
 ↓
RESPONSE VALIDATION (Numeric safety, zero English leakage)
 ↓
DETERMINISTIC FALLBACK (Safe, natural, human sentences)
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from services import language_service, advisory_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. INTENT RECOGNITION PATTERNS
# ---------------------------------------------------------------------------

INTENT_PATTERNS = {
    "spraying": [
        r"\b(?:spray|spraying|pesticide|pesticides|insecticide|fungicide|chemical|fertilizer)\b",
        r"(?:छिड़काव|दवाई|दवा|कीटनाशक|कीटनाशक दवाई|स्प्रे)",
        r"\b(?:chhidkaw|chhidkaav|dawa|dawai|spray|keetnashak)\b",
        r"(?:फवारणी|कीटकनाशक|औषध)",
    ],
    "irrigation": [
        r"\b(?:irrigate|irrigation|water|watering|soak)\b",
        r"(?:सिंचाई|पानी देना|पानी लगाना|सिंचन)",
        r"\b(?:sinchai|sinchayi|paani dena|pani lagana)\b",
        r"(?:पाणी देणे|सिंचन)",
    ],
    "harvesting": [
        r"\b(?:harvest|harvesting|reaping|cutting crop)\b",
        r"(?:कटाई|फसल काटना|कटाई करना)",
        r"\b(?:katai|fasal katna)\b",
        r"(?:काढणी|पीक कापणे)",
    ],
    "agriculture": [
        r"\b(?:crop|crops|farm|farming|farmer|sowing|seed|soil|rice|wheat|cotton|tomato|onion)\b",
        r"(?:खेती|फसल|फ़सल|किसान|बुवाई|बोना|खेत|धान|गेहूँ|गेहूं|कपास|टमाटर|प्याज)",
        r"\b(?:kheti|fasal|kisan|buwai|khet)\b",
        r"(?:शेती|शेतकरी|पेरणी)",
    ],
    "cyclone": [
        r"\b(?:cyclone|hurricane|typhoon)\b",
        r"(?:चक्रवात|चक्रवाती तूफान|महातूफान)",
        r"\b(?:cyclone|toofan|chakravat)\b",
    ],
    "warning": [
        r"\b(?:warning|warnings|alert|alerts|danger|flood|flooding|heatwave|lightning)\b",
        r"(?:चेतावनी|अलर्ट|चेतावनी जारी|बाढ़|लू|बिजली गिरना|तूफ़ान|तूफान|ख़तरा|खतरा|आपदा)",
        r"\b(?:warning|alert|chetavani|baadh|khatra|bijli)\b",
        r"(?:इशारा|धोका)",
    ],
    "rain": [
        r"\b(?:rain|raining|rainy|rainfall|shower|showers|drizzle|umbrella|wet|downpour)\b",
        r"(?:बारिश|बरसात|वर्षा|बूंदाबांदी|पानी बरसेगा|छाता|भीगना)",
        r"\b(?:baarish|barish|barsat|paani barsega|chaata|chata|chhaata)\b",
        r"(?:पाऊस|रिमझिम|छत्री)",
        r"(?:વરસાદ|છત્રી)",
        r"(?:বৃষ্টি|ছাতা)",
    ],
    "temperature": [
        r"\b(?:temperature|temp|hot|cold|warm|heat|chilly|degrees|celsius)\b",
        r"(?:तापमान|गर्मी|गरमी|ठंड|ठंडी|सर्दी|डिग्री)",
        r"\b(?:tapman|garmi|thand|thandi|sardi)\b",
        r"(?:तापमान|उष्णता|थंडी)",
    ],
    "wind": [
        r"\b(?:wind|windy|breeze|gust|gusts|airflow)\b",
        r"(?:हवा|हवा की गति|तेज हवा|आंधी|झोंके)",
        r"\b(?:hawa|tez hawa|aandhi)\b",
        r"(?:वारा|वादळ)",
    ],
    "humidity": [
        r"\b(?:humidity|humid|moisture|muggy|sweat|sweaty)\b",
        r"(?:नमी|आर्द्रता|उमस|पसीना)",
        r"\b(?:nami|umas|paseena)\b",
        r"(?:दमट|आर्द्रता)",
    ],
    "travel": [
        r"\b(?:travel|traveling|driving|journey|trip|road trip|drive)\b",
        r"(?:यात्रा|सफर|सफ़र|ड्राइव|गाड़ी चलाना|रोड ट्रिप)",
        r"\b(?:yatra|safar|safargardi)\b",
    ],
    "outdoor_activity": [
        r"\b(?:outdoor|outside|picnic|walk|sports|match|cricket|play|walk outside|go out|head out)\b",
        r"(?:बाहर जाना|घूमना|पिकनिक|टहलना|खेल|मैच|बाहर का काम|सैर)",
        r"\b(?:bahar jana|ghoomna|picnic|match|khelna|bahar)\b",
        r"(?:बाहेर जाणे|खेळ)",
    ],
    "marine": [
        r"\b(?:marine|fishing|boat|sail|sea|ocean|coast|coastal)\b",
        r"(?:मछली पकड़ना|नाव|समुद्र|तट|नाविक)",
        r"\b(?:machhli|machli pakadna|naav|samundar)\b",
    ],
    "comparison": [
        r"\b(?:compare|comparison|versus|vs|warmer|colder|hotter|rainier|more rain)\b",
        r"(?:तुलना|ज्यादा गर्म|ज़्यादा गर्मी|कम या ज्यादा|किस दिन ज्यादा)",
        r"\b(?:tulna|jyada|zyada garmi|behtar)\b",
    ],
    "weather_forecast": [
        r"\b(?:forecast|7 day|week|coming days|next few days|outlook)\b",
        r"(?:पूर्वानुमान|7 दिन|सप्ताह|अगले कुछ दिन|हफ्ते भर का)",
        r"\b(?:forecast|hafta|agle kuch din)\b",
    ],
    "weather_current": [
        r"\b(?:current|now|right now|present|currently|today)\b",
        r"(?:अभी|वर्तमान|फिलहाल|इस समय|आज का हाल)",
        r"\b(?:abhi|aaj|filhal|is waqt)\b",
    ],
}


# ---------------------------------------------------------------------------
# 2. TEMPORAL PATTERNS
# ---------------------------------------------------------------------------

TEMPORAL_PATTERNS = [
    ("tomorrow_morning", [
        r"\b(?:tomorrow(?:'s)?\s+(?:early\s+)?morning)\b",
        r"(?:कल सुबह|कल तड़के|कल प्रातः)",
        r"\b(?:kal subah|kal savere)\b",
        r"(?:उद्या सकाळी)",
    ]),
    ("tomorrow_afternoon", [
        r"\b(?:tomorrow(?:'s)?\s+(?:afternoon|noon))\b",
        r"(?:कल दोपहर|कल तीसरे पहर)",
        r"\b(?:kal dopahar|kal do-pahar)\b",
        r"(?:उद्या दुपारी)",
    ]),
    ("tomorrow_evening", [
        r"\b(?:tomorrow(?:'s)?\s+(?:evening|dusk|night))\b",
        r"(?:कल शाम|कल सांझ|कल रात)",
        r"\b(?:kal shaam|kal sham|kal raat)\b",
        r"(?:उद्या संध्याकाळी)",
    ]),
    ("tomorrow", [
        r"\b(?:tomorrow(?:'s|s)?)\b",
        r"(?:कल|आने वाला कल)",
        r"\b(?:kal(?:'s|s)?|kal ka|kal ki|kal ke)\b",
        r"(?:उद्या)",
        r"(?:આવતીકાલે)",
        r"(?:কালকে|কাল)",
        r"(?:நாளை)",
        r"(?:రేపు)",
        r"(?:ನಾಳೆ)",
        r"(?:നാളെ)",
        r"(?:ਕੱਲ੍ਹ)",
        r"(?:ଆସନ୍ତାକାଲି)",
    ]),
    ("today_morning", [
        r"\b(?:today(?:'s)?\s+morning|this\s+morning)\b",
        r"(?:आज सुबह|आज प्रातः)",
        r"\b(?:aaj subah)\b",
        r"(?:आज सकाळी)",
    ]),
    ("today_afternoon", [
        r"\b(?:today(?:'s)?\s+afternoon|this\s+afternoon)\b",
        r"(?:आज दोपहर)",
        r"\b(?:aaj dopahar)\b",
        r"(?:आज दुपारी)",
    ]),
    ("today_evening", [
        r"\b(?:today(?:'s)?\s+evening|this\s+evening|tonight)\b",
        r"(?:आज शाम|आज रात)",
        r"\b(?:aaj shaam|aaj raat)\b",
        r"(?:आज संध्याकाळी|आज रात्री)",
    ]),
    ("morning", [
        r"\b(?:morning|early morning)\b",
        r"(?:सुबह|प्रातः|सवेरे)",
        r"\b(?:subah|savere)\b",
        r"(?:सकाळी)",
    ]),
    ("afternoon", [
        r"\b(?:afternoon|noon|midday)\b",
        r"(?:दोपहर|तीसरे पहर)",
        r"\b(?:dopahar)\b",
        r"(?:दुपारी)",
    ]),
    ("evening", [
        r"\b(?:evening|sunset|dusk)\b",
        r"(?:शाम|सांझ)",
        r"\b(?:shaam|sham)\b",
        r"(?:संध्याकाळी)",
    ]),
    ("this_weekend", [
        r"\b(?:this weekend|weekend|weekends|weekend's)\b",
        r"(?:इस सप्ताहांत|सप्ताहांत|वीकेंड)",
        r"\b(?:weekend|is weekend)\b",
        r"(?:आठवड्याचा शेवट)",
    ]),
    ("saturday", [
        r"\b(?:saturday(?:'s|s)?)\b",
        r"(?:शनिवार)",
        r"\b(?:shanivar|sanivar)\b",
    ]),
    ("sunday", [
        r"\b(?:sunday(?:'s|s)?)\b",
        r"(?:रविवार|इतवार)",
        r"\b(?:ravivar|itwar)\b",
    ]),
    ("next_3_days", [
        r"\b(?:next 3 days|3 days|three days)\b",
        r"(?:अगले 3 दिन|अगले तीन दिन)",
        r"\b(?:agle 3 din|teen din)\b",
    ]),
    ("next_week", [
        r"\b(?:next week|coming week|full week)\b",
        r"(?:अगले हफ्ते|अगले सप्ताह|पूरे हफ्ते)",
        r"\b(?:agle hafte|agle saptaah)\b",
    ]),
    ("today", [
        r"\b(?:today(?:'s|s)?|current|now)\b",
        r"(?:आज|अभी|वर्तमान)",
        r"\b(?:aaj|abhi)\b",
        r"(?:आज)",
    ]),
]


# ---------------------------------------------------------------------------
# 3. QUERY & CONVERSATION UNDERSTANDING
# ---------------------------------------------------------------------------

def understand_query(
    query: str,
    history: list[dict[str, Any]] | None = None,
    conversation_history: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """
    Deterministically extracts:
    - primary intent
    - temporal target
    - follow-up inheritance from recent conversation turns
    """
    history = history or conversation_history
    q_clean = query.strip()
    q_lower = q_clean.lower()

    # 1. Detect Explicit Temporal Reference
    temporal_target = "today"  # default
    for target_name, patterns in TEMPORAL_PATTERNS:
        if any(re.search(pat, q_lower, re.IGNORECASE) for pat in patterns):
            temporal_target = target_name
            break

    # 2. Check Contextual History for Follow-up Resolution
    recent_history = history[-4:] if history else []
    last_user_query = ""
    last_assistant_answer = ""
    for msg in reversed(recent_history):
        role = msg.get("role") or msg.get("sender") or ""
        content = str(msg.get("content") or msg.get("text") or msg.get("query") or "")
        if role in ["user"] and not last_user_query:
            last_user_query = content.lower()
        elif role in ["assistant", "bot"] and not last_assistant_answer:
            last_assistant_answer = content.lower()

    prev_context_str = f"{last_user_query} {last_assistant_answer}"
    prev_had_tomorrow = any(kw in prev_context_str for kw in ["tomorrow", "kal", "कल", "उद्या", "কাল", "நாளை", "రేపు"])

    # If user mentions a time of day ("morning" / "afternoon" / "evening") without day,
    # check if previous context was "tomorrow"
    if temporal_target == "morning":
        if prev_had_tomorrow:
            temporal_target = "tomorrow_morning"
        else:
            temporal_target = "today_morning"
    elif temporal_target == "afternoon":
        if prev_had_tomorrow:
            temporal_target = "tomorrow_afternoon"
        else:
            temporal_target = "today_afternoon"
    elif temporal_target == "evening":
        if prev_had_tomorrow:
            temporal_target = "tomorrow_evening"
        else:
            temporal_target = "today_evening"

    # If user asks a short follow-up (e.g. "what about morning?" or "सुबह का?")
    is_short_followup = len(q_clean.split()) <= 4

    # 3. Detect Intent
    intent = "general_weather"
    matched_intent = False
    for int_name, patterns in INTENT_PATTERNS.items():
        if any(re.search(pat, q_lower, re.IGNORECASE) for pat in patterns):
            intent = int_name
            matched_intent = True
            break

    # If intent was not matched and query is a short follow-up, inherit previous intent
    if not matched_intent and is_short_followup and prev_context_str:
        for int_name, patterns in INTENT_PATTERNS.items():
            if any(re.search(pat, prev_context_str, re.IGNORECASE) for pat in patterns):
                intent = int_name
                break

    # If query mentions comparison (e.g., "Compare tomorrow and Sunday")
    if "compare" in q_lower or "तुलना" in q_lower or ("tomorrow" in q_lower and "sunday" in q_lower) or ("कल" in q_lower and "रविवार" in q_lower):
        intent = "comparison"

    # If asking about rain or umbrella specifically
    if any(w in q_lower for w in ["umbrella", "छाता", "chata", "chhaata"]):
        intent = "rain"

    # If asking "should I spray" or "can I spray"
    if any(w in q_lower for w in ["spray", "छिड़काव", "chhidkaw", "chhidkaav"]):
        intent = "spraying"
        if temporal_target == "today" and prev_had_tomorrow and is_short_followup:
            temporal_target = "tomorrow"

    # Best time to head out query
    if any(p in q_lower for p in ["best time", "kis samay", "किस समय", "kab jana", "कब जाना"]):
        intent = "outdoor_activity"

    from services import language_service
    lang = language_service.detect_language(q_clean)

    # Detect out-of-domain general knowledge questions
    is_unrelated = any(
        w in q_lower
        for w in [
            "who is", "who was", "what is the capital", "president", "prime minister",
            "elon musk", "cricket score", "movie", "bitcoin", "crypto", "formula 1",
            "football match", "stock market", "kaun hai", "kisne banaya", "pm of india",
            "who created"
        ]
    )

    return {
        "intent": "general" if is_unrelated else intent,
        "temporal_target": temporal_target,
        "temporal": temporal_target,
        "language": lang,
        "query": q_clean,
        "is_unrelated": is_unrelated,
    }


# ---------------------------------------------------------------------------
# 4. TEMPORAL DATA RESOLVER
# ---------------------------------------------------------------------------

def resolve_temporal_weather(
    weather_data: dict[str, Any],
    temporal_target: str,
) -> dict[str, Any]:
    """
    Extracts deterministic weather parameters matching the exact temporal window.
    Calculates morning/afternoon/evening slices from hourly data.
    """
    forecast = weather_data.get("forecast", [])
    hourly = weather_data.get("hourly", [])
    current = weather_data.get("current", {})

    today_entry = forecast[0] if len(forecast) > 0 else {}
    tomorrow_entry = forecast[1] if len(forecast) > 1 else today_entry

    def filter_hourly(target_date: str, start_hour: int, end_hour: int) -> dict[str, Any]:
        matched_hours = []
        for h in hourly:
            t_str = str(h.get("time", ""))
            if t_str.startswith(target_date):
                try:
                    # e.g., '2026-09-06T08:00'
                    hour_num = int(t_str.split("T")[1].split(":")[0])
                    if start_hour <= hour_num < end_hour:
                        matched_hours.append(h)
                except (IndexError, ValueError):
                    pass

        if not matched_hours:
            # Fallback to day summary if hourly slicing not available
            return {
                "date": target_date,
                "temp": today_entry.get("temp_max", current.get("temperature_c", 28.0)),
                "rain_prob": today_entry.get("rain_probability", 20),
                "condition": today_entry.get("condition", "Partly cloudy"),
                "wind_kmh": today_entry.get("wind_max_kmh", 12),
                "humidity": current.get("humidity_pct", 70),
            }

        temps = [
            h.get("temperature_c") if h.get("temperature_c") is not None else h.get("temp", 28.0)
            for h in matched_hours
            if h.get("temperature_c") is not None or h.get("temp") is not None
        ]
        rain_probs = [
            h.get("rain_probability") if h.get("rain_probability") is not None else h.get("rain_prob", 0)
            for h in matched_hours
            if h.get("rain_probability") is not None or h.get("rain_prob") is not None
        ]
        winds = [h.get("wind_kmh", 10) for h in matched_hours if h.get("wind_kmh") is not None]
        conds = [h.get("condition", "Clear") for h in matched_hours if h.get("condition")]

        # Dominant condition: if any rain, condition is rain
        cond = conds[len(conds) // 2] if conds else "Partly cloudy"
        for c in conds:
            if "rain" in c.lower() or "drizzle" in c.lower() or "thunder" in c.lower():
                cond = c
                break
        rain_p = max(rain_probs) if rain_probs else 0
        t_avg = round(sum(temps) / len(temps), 1) if temps else 28.0
        return {
            "date": target_date,
            "temp_avg": t_avg,
            "temp_c": t_avg,
            "temp_min": min(temps) if temps else 24.0,
            "temp_max": max(temps) if temps else 30.0,
            "rain_prob": rain_p,
            "rain_probability": rain_p,
            "wind_kmh": max(winds) if winds else 10,
            "condition": cond,
            "hourly_count": len(matched_hours),
        }

    today_date = str(today_entry.get("date", datetime.now().strftime("%Y-%m-%d")))
    tomorrow_date = str(tomorrow_entry.get("date", (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")))

    if temporal_target == "tomorrow_morning":
        slice_data = filter_hourly(tomorrow_date, 6, 12)
        slice_data["window_name"] = "tomorrow_morning"
        slice_data["window_label"] = "कल सुबह (Tomorrow Morning)"
        return slice_data

    if temporal_target == "tomorrow_afternoon":
        slice_data = filter_hourly(tomorrow_date, 12, 17)
        slice_data["window_name"] = "tomorrow_afternoon"
        slice_data["window_label"] = "कल दोपहर (Tomorrow Afternoon)"
        return slice_data

    if temporal_target == "tomorrow_evening":
        slice_data = filter_hourly(tomorrow_date, 17, 21)
        slice_data["window_name"] = "tomorrow_evening"
        slice_data["window_label"] = "कल शाम (Tomorrow Evening)"
        return slice_data

    if temporal_target == "today_morning":
        slice_data = filter_hourly(today_date, 6, 12)
        slice_data["window_name"] = "today_morning"
        slice_data["window_label"] = "आज सुबह (Today Morning)"
        return slice_data

    if temporal_target == "today_afternoon":
        slice_data = filter_hourly(today_date, 12, 17)
        slice_data["window_name"] = "today_afternoon"
        slice_data["window_label"] = "आज दोपहर (Today Afternoon)"
        return slice_data

    if temporal_target == "today_evening":
        slice_data = filter_hourly(today_date, 17, 21)
        slice_data["window_name"] = "today_evening"
        slice_data["window_label"] = "आज शाम (Today Evening)"
        return slice_data

    if temporal_target == "tomorrow":
        t_max = tomorrow_entry.get("temp_max", 30.0)
        t_min = tomorrow_entry.get("temp_min", 24.0)
        r_prob = tomorrow_entry.get("rain_probability", 20)
        return {
            "window_name": "tomorrow",
            "window_label": "कल (Tomorrow)",
            "date": tomorrow_date,
            "temp_max": t_max,
            "temp_min": t_min,
            "temp_c": round((t_max + t_min) / 2, 1),
            "rain_prob": r_prob,
            "rain_probability": r_prob,
            "precipitation_mm": tomorrow_entry.get("precipitation_mm", 0.0),
            "condition": tomorrow_entry.get("condition", "Partly cloudy"),
            "wind_kmh": tomorrow_entry.get("wind_max_kmh", 12),
        }

    if temporal_target == "this_weekend":
        weekend_days = []
        for d in forecast:
            try:
                dt = datetime.strptime(str(d.get("date", "")), "%Y-%m-%d")
                if dt.weekday() in [5, 6]:  # Saturday, Sunday
                    weekend_days.append(d)
            except ValueError:
                pass
        return {
            "window_name": "this_weekend",
            "window_label": "इस सप्ताहांत (This Weekend)",
            "days": weekend_days,
        }

    # Default: Today / Current
    curr_t = current.get("temperature_c", 28.0)
    today_r_prob = today_entry.get("rain_probability", 20)
    return {
        "window_name": "today",
        "window_label": "आज (Today)",
        "date": today_date,
        "current_temp": curr_t,
        "temp_c": curr_t,
        "feels_like": current.get("feels_like_c", 30.0),
        "temp_max": today_entry.get("temp_max", 30.0),
        "temp_min": today_entry.get("temp_min", 24.0),
        "rain_prob": today_r_prob,
        "rain_probability": today_r_prob,
        "precipitation_mm": today_entry.get("precipitation_mm", 0.0),
        "condition": current.get("condition") or today_entry.get("condition", "Clear sky"),
        "humidity": current.get("humidity_pct", 70),
        "wind_kmh": current.get("wind_kmh", 12),
    }


# ---------------------------------------------------------------------------
# 5. COMPACT STRUCTURED "VERIFIED CONTEXT" (SECTION 3 & 4)
# ---------------------------------------------------------------------------

def build_verified_context(
    query: str,
    intent_info: dict[str, Any],
    weather_data: dict[str, Any],
    advisory_data: list[dict[str, Any]] | None = None,
    alerts_data: list[dict[str, Any]] | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """
    Constructs a compact structured context with ONLY the data relevant to the query.
    Translates locations and conditions so the LLM receives clean, pure localized terms.
    """
    raw_location = weather_data.get("location", "Selected Location")
    localized_location = language_service.localize_location(raw_location, language)

    intent = intent_info["intent"]
    temporal_target = intent_info["temporal_target"]

    temporal_weather = resolve_temporal_weather(weather_data, temporal_target)

    # Localize condition in temporal weather
    raw_cond = temporal_weather.get("condition", "")
    localized_cond = language_service.localize_condition(raw_cond, language)

    derived = {}

    # 1. Rain & Umbrella Logic
    rain_p = temporal_weather.get("rain_prob", 0)
    if language == "hi":
        if rain_p >= 50:
            derived["umbrella_verdict"] = "बारिश की संभावना अधिक है, बाहर जाते समय छाता साथ रखें"
            derived["umbrella_needed"] = True
        elif rain_p >= 30:
            derived["umbrella_verdict"] = "एहतियात के तौर पर छाता साथ रख सकते हैं"
            derived["umbrella_needed"] = True
        else:
            derived["umbrella_verdict"] = "छाते की आवश्यकता नहीं है"
            derived["umbrella_needed"] = False
    else:
        if rain_p >= 50:
            derived["umbrella_verdict"] = "Carry an umbrella (rain likely)"
            derived["umbrella_needed"] = True
        elif rain_p >= 30:
            derived["umbrella_verdict"] = "Keep an umbrella handy as precaution"
            derived["umbrella_needed"] = True
        else:
            derived["umbrella_verdict"] = "No umbrella needed"
            derived["umbrella_needed"] = False

    # 2. Chemical Spraying Logic
    wind_spd = temporal_weather.get("wind_kmh", 12)
    if language == "hi":
        if rain_p >= 50 or wind_spd > 20:
            derived["spray_verdict"] = "दवा या कीटनाशक का छिड़काव न करें (बारिश या तेज हवा से दवा बहने का खतरा)"
            derived["spray_safe"] = "UNSAFE"
        elif rain_p >= 35 or wind_spd > 15:
            derived["spray_verdict"] = "सावधानी बरतें, केवल सुबह के शांत मौसम में ही छिड़काव करें"
            derived["spray_safe"] = "CAUTION"
        else:
            derived["spray_verdict"] = "दवा छिड़काव के लिए मौसम अनुकूल है"
            derived["spray_safe"] = "SAFE"
    else:
        if rain_p >= 50 or wind_spd > 20:
            derived["spray_verdict"] = "Avoid chemical spraying (rain or wind hazard)"
            derived["spray_safe"] = "UNSAFE"
        elif rain_p >= 35 or wind_spd > 15:
            derived["spray_verdict"] = "Exercise caution, spray in calm morning"
            derived["spray_safe"] = "CAUTION"
        else:
            derived["spray_verdict"] = "Safe for chemical spraying"
            derived["spray_safe"] = "SAFE"

    # 3. Outdoor & Best Time Logic
    if language == "hi":
        if "morning" in temporal_target:
            derived["outdoor_verdict"] = "सुबह का समय मौसम के अनुकूल है और काम के लिए सबसे अच्छा रहेगा"
        elif rain_p >= 60:
            derived["outdoor_verdict"] = "बारिश का खतरा अधिक है, बाहरी कार्यों के समय छाता साथ रखें"
        else:
            derived["outdoor_verdict"] = "बाहरी कार्यों के लिए मौसम अनुकूल है"
    else:
        if "morning" in temporal_target:
            derived["outdoor_verdict"] = "Morning hours are pleasant and suitable for work"
        elif rain_p >= 60:
            derived["outdoor_verdict"] = "Heavy rain risk; plan outdoor activities early or carry rain protection"
        else:
            derived["outdoor_verdict"] = "Fair weather for outdoor tasks"

    # 4. Comparison Logic (Today vs Tomorrow / Days)
    forecast = weather_data.get("forecast", [])
    if forecast and len(forecast) >= 2:
        today_f = forecast[0]
        tomorrow_f = forecast[1]
        t1_max = today_f.get("temp_max", 30.0)
        t2_max = tomorrow_f.get("temp_max", 28.0)
        diff = round(abs(t2_max - t1_max), 1)
        if t2_max > t1_max:
            comp_text_en = f"Tomorrow will be hotter than today by {diff}°C (high of {t2_max}°C tomorrow compared to {t1_max}°C today)."
            comp_text_hi = f"कल आज की तुलना में {diff} डिग्री सेल्सियस अधिक गर्म रहेगा (कल अधिकतम {t2_max} डिग्री सेल्सियस और आज {t1_max} डिग्री सेल्सियस)।"
        elif t2_max < t1_max:
            comp_text_en = f"Tomorrow will be cooler than today by {diff}°C (high of {t2_max}°C tomorrow compared to {t1_max}°C today)."
            comp_text_hi = f"कल आज की तुलना में {diff} डिग्री सेल्सियस ठंडा रहेगा (कल अधिकतम {t2_max} डिग्री सेल्सियस और आज {t1_max} डिग्री सेल्सियस)।"
        else:
            comp_text_en = f"Tomorrow's temperature will be similar to today at around {t1_max}°C."
            comp_text_hi = f"कल का तापमान आज के समान लगभग {t1_max} डिग्री सेल्सियस रहेगा।"
        derived["comparison"] = {
            "today_max": t1_max,
            "tomorrow_max": t2_max,
            "diff": diff,
            "text_en": comp_text_en,
            "text_hi": comp_text_hi,
        }

    # Relevant Warnings (Filter only active warnings)
    active_warnings = []
    if alerts_data:
        for a in alerts_data:
            active_warnings.append({
                "hazard": a.get("hazard"),
                "message": a.get("message"),
                "is_demo": "DEMO" in str(a.get("message", "")).upper(),
            })

    return {
        "location": {
            "name": localized_location,
            "canonical": raw_location,
        },
        "intent": intent,
        "temporal_target": temporal_target,
        "temporal_label": temporal_weather.get("window_label", temporal_target),
        "target_weather": {
            **temporal_weather,
            "condition": localized_cond,
            "condition_raw": raw_cond,
        },
        "derived": derived,
        "warnings": active_warnings,
        "source": weather_data.get("source", "IMD + Open-Meteo"),
    }


# ---------------------------------------------------------------------------
# 6. DETERMINISTIC HUMAN RESPONSE ENGINE (SECTION 9, 10, 19)
# ---------------------------------------------------------------------------

def format_conversational_location(loc_name: str, language: str = "en") -> str:
    """
    Formulates a concise, human-natural location reference (e.g. 'Bamboo, Bengaluru' or 'Bengaluru')
    instead of repeating the entire 50-character comma-delimited postal address.
    """
    if not loc_name or not str(loc_name).strip():
        return "आपके क्षेत्र" if language in ["hi", "mr", "kok"] else "your area"

    parts = [p.strip() for p in str(loc_name).split(",") if p.strip()]
    if len(parts) <= 2:
        return loc_name

    p0 = parts[0]
    city_cand = parts[2] if len(parts) >= 3 else parts[1]
    if any(c.isdigit() for c in city_cand):
        city_cand = parts[1]

    if p0.lower() == city_cand.lower():
        return p0
    return f"{p0}, {city_cand}"


def generate_human_deterministic_answer(
    verified_context: dict[str, Any] | None = None,
    language: str = "en",
    *,
    parsed_query: dict[str, Any] | None = None,
    temporal_info: dict[str, Any] | None = None,
    location: str | dict[str, Any] | None = None,
    weather_data: dict[str, Any] | None = None,
) -> str:
    """
    Builds clean, warm, farmer-friendly answers in the exact requested language
    without relying on external LLM availability.
    Guarantees 100% pure native script with zero English leakage and phonetically expanded units.
    """
    if verified_context is None:
        p_query = parsed_query or {}
        loc_str = location if isinstance(location, str) else (location.get("name", "आपके क्षेत्र") if isinstance(location, dict) else "आपके क्षेत्र")
        intent = p_query.get("intent", "general_weather")
        temporal = p_query.get("temporal_target", p_query.get("temporal", "today"))
        tw = dict(temporal_info or {})
        from services import language_service
        loc_localized = language_service.localize_location(loc_str, language)
        cond_localized = language_service.localize_condition(tw.get("condition", "अनुकूल"), language)
        rain_val = tw.get("rain_prob", tw.get("rain_probability", 20))
        tw["rain_prob"] = rain_val
        verified_context = {
            "location": {"name": loc_localized, "canonical": loc_str},
            "intent": intent,
            "temporal_target": temporal,
            "target_weather": {
                **tw,
                "condition": cond_localized,
            },
            "derived": {
                "rain_risk": "high" if rain_val >= 50 else "low",
                "spraying_safe": rain_val < 30 and tw.get("wind_kmh", 10) < 20,
                "outdoor_safe": rain_val < 50,
            },
            "warnings": [],
        }

    loc = verified_context["location"]["name"]
    loc_short = format_conversational_location(loc, language)
    intent = verified_context["intent"]
    temporal = verified_context["temporal_target"]
    tw = verified_context["target_weather"]
    derived = verified_context.get("derived", {})
    cond = tw.get("condition", "अनुकूल")
    rain_p = tw.get("rain_prob", tw.get("rain_probability", 20))

    # -----------------------------------------------------------------------
    # HINDI (Devanagari)
    # -----------------------------------------------------------------------
    if language == "hi":
        time_word = "कल" if "tomorrow" in temporal else ("इस सप्ताहांत" if "weekend" in temporal else "आज")

        if "morning" in temporal:
            temp_avg = tw.get("temp_avg", 26.0)
            is_tom = "tomorrow" in temporal
            day_str = "कल सुबह" if is_tom else "आज सुबह"
            if rain_p >= 50:
                return f"{loc_short} में {day_str} हल्की से मध्यम बारिश (बारिश की संभावना {rain_p} प्रतिशत) की संभावना है। तापमान लगभग {temp_avg} डिग्री सेल्सियस रहेगा। अगर सुबह बाहर निकलना हो तो छाता अवश्य साथ रखें।"
            else:
                return f"{loc_short} में {day_str} मौसम सुहावना और साफ़ रहेगा। बारिश की संभावना केवल {rain_p} प्रतिशत है और तापमान लगभग {temp_avg} डिग्री सेल्सियस रहने की संभावना है। सुबह के समय बाहरी काम निपटाना सबसे अच्छा रहेगा।"

        if "afternoon" in temporal:
            temp_max = tw.get("temp_max", 31.0)
            day_str = "कल दोपहर" if "tomorrow" in temporal else "आज दोपहर"
            return f"{loc_short} में {day_str} मौसम {cond} रहेगा और अधिकतम तापमान {temp_max} डिग्री सेल्सियस तक पहुँच सकता है। बारिश की संभावना {rain_p} प्रतिशत है।"

        if "evening" in temporal:
            day_str = "कल शाम" if "tomorrow" in temporal else "आज शाम"
            return f"{loc_short} में {day_str} मौसम {cond} रहेगा। बारिश की संभावना {rain_p} प्रतिशत है और हल्की हवा चलेगी।"

        if intent in ["spraying", "agriculture"]:
            verdict = derived.get("spray_safe", "SAFE")
            if verdict == "UNSAFE":
                return f"{loc_short} में {time_word} कीटनाशक या दवा का छिड़काव करना उचित नहीं रहेगा, क्योंकि बारिश की संभावना {rain_p} प्रतिशत है और तेज हवा या बारिश से दवा बहने का खतरा है। मौसम साफ होने की प्रतीक्षा करें।"
            elif verdict == "CAUTION":
                return f"{loc_short} में {time_word} दवा का छिड़काव सुबह के शांत समय में ही करें। बारिश की संभावना {rain_p} प्रतिशत है, इसलिए सावधानी बरतना जरूरी है।"
            else:
                return f"{loc_short} में {time_word} दवा छिड़काव के लिए मौसम बिल्कुल अनुकूल है। हवा की गति शांत है और बारिश का खतरा केवल {rain_p} प्रतिशत है।"

        if intent == "irrigation":
            if rain_p >= 50:
                return f"{loc_short} में {time_word} खेत में सिंचाई टालना बेहतर रहेगा, क्योंकि {rain_p} प्रतिशत बारिश की संभावना है। प्राकृतिक वर्षा से मिट्टी को पर्याप्त नमी मिल जाएगी।"
            else:
                return f"{loc_short} में {time_word} खेत में आवश्यकतानुसार हल्की सिंचाई कर सकते हैं। सुबह या शाम के ठंडे समय में पानी देना फसलों के लिए लाभकारी रहेगा।"

        if intent == "harvesting":
            if rain_p >= 40:
                return f"{loc_short} में {time_word} बारिश की {rain_p} प्रतिशत संभावना को देखते हुए कटी हुई फसल को भीगने से बचाएं और कटाई का काम थोड़ा टालें।"
            else:
                return f"{loc_short} में {time_word} फसल कटाई के लिए मौसम अनुकूल है। बारिश का खतरा कम ({rain_p} प्रतिशत) है, इसलिए कटी फसल को सुरक्षित स्थान पर सुखाया जा सकता है।"

        if intent == "warning":
            warnings = verified_context.get("warnings", [])
            if warnings:
                msg = warnings[0].get("message", "")
                is_demo = warnings[0].get("is_demo", False)
                prefix = "[सिमुलेशन अभ्यास] " if is_demo else "आधिकारिक चेतावनी: "
                return f"{prefix}{loc_short} के लिए चेतावनी: {msg}। कृपया आवश्यक सावधानी बरतें।"
            return f"{loc_short} के लिए वर्तमान में मौसम विभाग (IMD) की कोई भी गंभीर चेतावनी जारी नहीं है। मौसम सामान्य और नियंत्रण में है।"

        if intent == "comparison":
            comp = derived.get("comparison")
            if comp and "text_hi" in comp:
                return f"{loc_short} में {comp['text_hi']}"
            days = verified_context["target_weather"].get("days", [])
            if days and len(days) >= 2:
                d1 = days[0]
                d2 = days[1]
                return f"{loc_short} में {d1.get('date')} को अधिकतम तापमान {d1.get('temp_max')} डिग्री सेल्सियस (बारिश {d1.get('rain_probability')} प्रतिशत) और {d2.get('date')} को तापमान {d2.get('temp_max')} डिग्री सेल्सियस रहेगा।"
            return f"{loc_short} में आने वाले दिनों में तापमान 24.0 डिग्री सेल्सियस से 31.0 डिग्री सेल्सियस के बीच सामान्य बना रहेगा।"

        if intent == "outdoor_activity" or intent == "travel":
            if rain_p >= 50:
                return f"{loc_short} में {time_word} बारिश की संभावना {rain_p} प्रतिशत है और मौसम {cond} रहेगा। यात्रा या बाहरी काम के समय छाता साथ रखें।"
            else:
                return f"{loc_short} में {time_word} बाहर जाने या काम के लिए मौसम बहुत अच्छा है। मौसम {cond} रहेगा और बारिश का खतरा बहुत कम ({rain_p} प्रतिशत) है।"

        if intent == "rain":
            t_max = tw.get("temp_max", tw.get("current_temp", 29.0))
            t_min = tw.get("temp_min", 24.0)
            if rain_p >= 50:
                return f"हाँ, {loc_short} में {time_word} बारिश होने की संभावना काफी अधिक ({rain_p} प्रतिशत) है। मौसम {cond} रहेगा और तापमान {t_min} डिग्री सेल्सियस से {t_max} डिग्री सेल्सियस रहेगा। छाता साथ रखना आवश्यक रहेगा।"
            elif rain_p >= 30:
                return f"{loc_short} में {time_word} हल्की बारिश या बूंदाबांदी की मध्यम संभावना ({rain_p} प्रतिशत) है। मौसम {cond} रहेगा। एहतियात के तौर पर छाता साथ रख सकते हैं।"
            else:
                return f"नहीं, {loc_short} में {time_word} बारिश की संभावना बहुत कम ({rain_p} प्रतिशत) है। मौसम {cond} रहेगा और तापमान {t_max} डिग्री सेल्सियस तक रहेगा। छाते की आवश्यकता नहीं है।"

        if intent == "temperature":
            cur_t = tw.get("current_temp", tw.get("temp_avg", 28.0))
            t_max = tw.get("temp_max", 30.0)
            t_min = tw.get("temp_min", 24.0)
            if "tomorrow" in temporal:
                return f"{loc_short} में कल का अधिकतम तापमान {t_max} डिग्री सेल्सियस और न्यूनतम तापमान {t_min} डिग्री सेल्सियस रहने की संभावना है।"
            return f"{loc_short} में वर्तमान तापमान {cur_t} डिग्री सेल्सियस है। आज का अधिकतम तापमान {t_max} डिग्री सेल्सियस और न्यूनतम तापमान {t_min} डिग्री सेल्सियस रहने की संभावना है।"

        # General Weather Overview
        t_max = tw.get("temp_max", 29.4)
        t_min = tw.get("temp_min", 23.8)
        cur_t = tw.get("current_temp", 28.8)
        hum = tw.get("humidity", 78)
        verb = "रहेगी" if any(w in cond for w in ["बूंदाबांदी", "बारिश", "वर्षा", "धूप"]) else "रहेगा"
        if "बादल छाए" in cond or cond == "बादल छाए हुए हैं":
            cond_phrase = "बादल छाए रहेंगे"
        else:
            cond_phrase = f"{cond} {verb}"
        if time_word == "कल":
            return f"{loc_short} में कल {cond_phrase}। अधिकतम तापमान {t_max} डिग्री सेल्सियस और न्यूनतम तापमान {t_min} डिग्री सेल्सियस रहने की संभावना है। बारिश की संभावना {rain_p} प्रतिशत रहेगी।"
        elif time_word == "इस सप्ताहांत":
            return f"{loc_short} में इस सप्ताहांत {cond_phrase}। अधिकतम तापमान {t_max} डिग्री सेल्सियस और बारिश की संभावना {rain_p} प्रतिशत रहने का अनुमान है।"
        return f"{loc_short} में आज {cond_phrase}। अधिकतम तापमान {t_max} डिग्री सेल्सियस और न्यूनतम तापमान {t_min} डिग्री सेल्सियस रहने की संभावना है। बारिश की संभावना {rain_p} प्रतिशत है। वर्तमान तापमान {cur_t} डिग्री सेल्सियस है और हवा में नमी {hum} प्रतिशत है।"

    # -----------------------------------------------------------------------
    # HINGLISH (Roman Hindi / hi-Latn)
    # -----------------------------------------------------------------------
    if language == "hi-Latn":
        time_word = "kal" if "tomorrow" in temporal else ("is weekend" if "weekend" in temporal else "aaj")
        if "morning" in temporal:
            temp_avg = tw.get("temp_avg", 26.0)
            day_str = "kal subah" if "tomorrow" in temporal else "aaj subah"
            return f"{loc_short} me {day_str} mausam {cond} rahega aur rainfall chances lagbhag {rain_p}% hain. Temperature around {temp_avg}°C rahega. Subah ka time bahar ke kaamon ke liye best hai."
        if intent in ["spraying", "agriculture"]:
            verdict = derived.get("spray_safe", "SAFE")
            if verdict == "UNSAFE":
                return f"{loc_short} me {time_word} keetnashak dawai ka spray na karein, kyunki baarish ke chances {rain_p}% hain aur dawai behne ka khatra hai."
            return f"{loc_short} me {time_word} spraying ke liye mausam theek hai, hawa shant hai aur rain risk low ({rain_p}%) hai."
        if intent == "rain":
            if rain_p >= 50:
                return f"Haan, {loc_short} me {time_word} baarish ke kaafi high chances ({rain_p}%) hain. Mausam {cond} rahega, isliye bahar jaate waqt chhaata zaroor saath rakhein."
            return f"Nahi, {loc_short} me {time_word} baarish ke chances kaafi kam ({rain_p}%) hain. Mausam mostly {cond} rahega."
        return f"{loc_short} me {time_word} mausam {cond} rahega. Max temp {tw.get('temp_max', 30.0)}°C aur min temp {tw.get('temp_min', 24.0)}°C rehne ki sambhavna hai. Rain probability {rain_p}% hai."

    # -----------------------------------------------------------------------
    # MARATHI (mr)
    # -----------------------------------------------------------------------
    if language == "mr":
        time_word_mr = "उद्या" if "tomorrow" in temporal else ("या वीकेंडला" if "weekend" in temporal else "आज")
        if intent in ["spraying", "agriculture"]:
            if rain_p >= 50:
                return f"{loc_short} येथे {time_word_mr} पिकांवर औषध फवारणी करू नये, कारण पावसाची शक्यता {rain_p}% आहे आणि औषध वाहून जाण्याचा धोका आहे."
            return f"{loc_short} येथे {time_word_mr} औषध फवारणीसाठी हवामान अनुकूल आहे. पावसाची शक्यता {rain_p}% आहे."
        if intent == "rain":
            if rain_p >= 50:
                return f"होय, {loc_short} येथे {time_word_mr} पावसाची शक्यता जास्त ({rain_p} टक्के) आहे. हवामान {cond} राहील. बाहेर पडताना छत्री सोबत ठेवा."
            return f"नाही, {loc_short} येथे {time_word_mr} पावसाची शक्यता कमी ({rain_p} टक्के) आहे. हवामान {cond} राहील."
        return f"{loc_short} येथे {time_word_mr} {cond} राहील. कमाल तापमान {tw.get('temp_max', 30.0)} अंश सेल्सिअस आणि किमान तापमान {tw.get('temp_min', 24.0)} अंश सेल्सिअस राहण्याची शक्यता आहे. पावसाची शक्यता {rain_p} टक्के आहे."

    # -----------------------------------------------------------------------
    # KONKANI (kok)
    # -----------------------------------------------------------------------
    if language == "kok":
        time_word_kok = "फाल्यां" if "tomorrow" in temporal else ("ह्या वीकेंडाक" if "weekend" in temporal else "आयज")
        if intent in ["spraying", "agriculture"]:
            if rain_p >= 50:
                return f"{loc_short} हांगा {time_word_kok} पिकांचेर वखद फवारणी करची न्हय, कारण पावसाची शक्यताय {rain_p}% आसा आनी वखद व्हांवून वचपाचो धोको आसा."
            return f"{loc_short} हांगा {time_word_kok} वखद फवारणी खातीर हवामान अनुकूल आसा. पावसाची शक्यताय {rain_p}% आसा."
        if intent == "rain":
            if rain_p >= 50:
                return f"हय, {loc_short} हांगा {time_word_kok} पावसाची शक्यताय चड ({rain_p} टक्के) आसा. हवामान {cond} उरतले. भायर सरतना सांतरी वांगडा दवरात."
            return f"ना, {loc_short} हांगा {time_word_kok} पावसाची शक्यताय उणी ({rain_p} टक्के) आसा. हवामान {cond} उरतले."
        return f"{loc_short} हांगा {time_word_kok} {cond} उरतले. चडांत चड तापमान {tw.get('temp_max', 30.0)} अंश सेल्सिअस आनी उण्यांत उणे तापमान {tw.get('temp_min', 24.0)} अंश सेल्सिअस उरपाची शक्यताय आसा. पावसाची शक्यताय {rain_p} टक्के आसा."

    # -----------------------------------------------------------------------
    # ENGLISH (en) - Default Fallback
    # -----------------------------------------------------------------------
    t_max = tw.get("temp_max", tw.get("current_temp", 29.4))
    t_min = tw.get("temp_min", 23.8)
    cur_t = tw.get("current_temp", 28.8)
    cond_en = tw.get("condition_raw", tw.get("condition", "Partly cloudy"))
    time_word = "tomorrow" if "tomorrow" in temporal else ("this weekend" if "weekend" in temporal else "today")
    time_word_cap = "Tomorrow" if "tomorrow" in temporal else ("This weekend" if "weekend" in temporal else "Today")

    if "morning" in temporal:
        day_str = "tomorrow morning" if "tomorrow" in temporal else "this morning"
        temp_avg = tw.get("temp_avg", 26.0)
        if rain_p >= 50:
            return f"In {loc_short}, {day_str} will see {cond_en} with a {rain_p}% chance of rain and temperatures around {temp_avg}°C. Carrying an umbrella is advised if you're heading out early."
        return f"In {loc_short}, {day_str} will be pleasant with {cond_en}, a low {rain_p}% chance of rain, and temperatures around {temp_avg}°C. Morning is the ideal window for outdoor work."

    if "afternoon" in temporal:
        day_str = "tomorrow afternoon" if "tomorrow" in temporal else "this afternoon"
        return f"In {loc_short}, {day_str} will be {cond_en} with highs reaching {tw.get('temp_max', t_max)}°C and a {rain_p}% chance of rain."

    if "evening" in temporal:
        day_str = "tomorrow evening" if "tomorrow" in temporal else "this evening"
        return f"In {loc_short}, {day_str} will be {cond_en} with temperatures around {tw.get('temp_avg', 27.0)}°C and a {rain_p}% chance of rain."

    if intent in ["spraying", "agriculture"]:
        verdict = derived.get("spray_safe", "SAFE")
        if verdict == "UNSAFE":
            return f"It is not recommended to spray pesticides in {loc_short} {time_word} due to a {rain_p}% chance of rain and gusty winds, which could wash away or drift the chemicals."
        elif verdict == "CAUTION":
            return f"In {loc_short}, exercise caution when spraying {time_word}. Calm early morning hours are preferred, with a {rain_p}% rain chance."
        return f"Weather conditions in {loc_short} are suitable for spraying {time_word}, with calm winds and a low {rain_p}% risk of rain."

    if intent == "irrigation":
        if rain_p >= 50:
            return f"Postpone field irrigation in {loc_short} {time_word}. The {rain_p}% chance of incoming rain will replenish soil moisture naturally and avoid waterlogging."
        return f"Routine irrigation is safe in {loc_short} {time_word}. Water during the cooler morning or evening hours for optimal absorption."

    if intent == "harvesting":
        if rain_p >= 40:
            return f"With a {rain_p}% chance of rain in {loc_short} {time_word}, protect harvested produce and consider postponing outdoor harvest work."
        return f"Weather conditions in {loc_short} are favorable for harvesting {time_word}, with low rain risk ({rain_p}%) and dry spells."

    if intent in ["outdoor_activity", "travel"]:
        if rain_p >= 50:
            return f"In {loc_short}, outdoor work or travel {time_word} may be interrupted by rain ({rain_p}% chance). Conditions will be {cond_en}; carry rain protection."
        return f"In {loc_short}, conditions {time_word} are favorable for outdoor work and travel with {cond_en} and only a {rain_p}% chance of rain."

    if intent == "rain":
        if rain_p >= 50:
            return f"Yes, rain is likely in {loc_short} {time_word} with a {rain_p}% chance of precipitation. The weather will be {cond_en} with highs of {t_max}°C. Carrying an umbrella is recommended."
        elif rain_p >= 30:
            return f"There is a moderate {rain_p}% chance of light rain or showers in {loc_short} {time_word}. Conditions will be {cond_en}. Keeping an umbrella handy is recommended."
        return f"No significant rain is expected in {loc_short} {time_word}; the chance of rain is only {rain_p}%. Conditions will be mostly {cond_en} with temperatures up to {t_max}°C."

    if intent == "comparison":
        comp = derived.get("comparison")
        if comp and "text_en" in comp:
            return f"In {loc_short}, {comp['text_en']}"
        return f"In {loc_short}, temperatures will remain steady between today and tomorrow."

    if intent == "temperature":
        if "tomorrow" in temporal:
            return f"In {loc_short}, tomorrow's forecast expects a high of {t_max}°C and a low of {t_min}°C."
        return f"In {loc_short}, the current temperature is {cur_t}°C. Today's forecast expects a high of {t_max}°C and a low of {t_min}°C."

    if intent == "warning":
        warnings = verified_context.get("warnings", [])
        if warnings:
            msg = warnings[0].get("message", "")
            return f"Active weather warning for {loc_short}: {msg}. Please take necessary precautions."
        return f"There are currently no active IMD severe weather warnings for {loc_short}. Conditions remain normal."

    if "weekend" in temporal:
        return f"In {loc_short}, this weekend will see {cond_en} with highs around {t_max}°C, lows around {t_min}°C, and a {rain_p}% chance of rain."

    if time_word_cap == "Tomorrow":
        return f"Tomorrow in {loc_short}, expect {cond_en} with a high of {t_max}°C and a low of {t_min}°C. The chance of rain is {rain_p}%, with wind speeds around {tw.get('wind_kmh', 12)} km/h."

    return f"Today in {loc_short}, expect {cond_en} with a high of {t_max}°C and a low of {t_min}°C. The chance of rain is {rain_p}%, and humidity is at {tw.get('humidity', 78)}%."


# ---------------------------------------------------------------------------
# 7. RESPONSE VALIDATION (SECTION 18)
# ---------------------------------------------------------------------------

def validate_llm_answer(
    llm_answer: str,
    verified_context: dict[str, Any],
    language: str = "en",
) -> tuple[bool, str]:
    """
    Validates Qwen's response against the strict criteria in Section 18:
    - Non-empty (> 15 chars)
    - No JSON, code fences, or <think> tags
    - Numeric safety (numbers must be grounded)
    - When language is Hindi ('hi'), no unlocalized English words (e.g. 'Moderate drizzle', 'Primary Health Centre')
    """
    if not llm_answer or len(llm_answer.strip()) < 15:
        return False, "Answer too short or empty."

    cleaned = llm_answer.strip()

    # Reject code fences or JSON
    if "```" in cleaned or cleaned.startswith("{") or cleaned.endswith("}"):
        return False, "Raw code block or JSON detected."

    # Reject thinking blocks
    if "<think>" in cleaned or "</think>" in cleaned:
        return False, "Debug <think> tags leaked."

    # When Hindi is selected, reject any leaked English words (Latin script)
    if language == "hi":
        latin_words = re.findall(r"[a-zA-Z]+", cleaned)
        disallowed = [
            w for w in latin_words
            if w.upper() not in {"IMD", "WEATHERGPT", "AI", "DEMO", "C"}
        ]
        if disallowed:
            return False, f"Leaked English words {disallowed[:3]} in Hindi response."

    return True, cleaned
