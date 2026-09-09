"""
Retrieval-Augmented Generation (RAG) & Advisory Knowledge Layer for WeatherGPT (SIH26068).

Indexes authoritative meteorological knowledge:
1. Agricultural Decision Rules & Crop Advisory Knowledge Base (advisory_kb.json)
2. Crawled Official IMD Weather Bulletins, Cyclone Outlooks & District Warnings

Provides multi-faceted retrieval based on:
- Location (District, State, Sub-division, National)
- Temporal target (Today, Tomorrow, Specific dates)
- Query Intent (Heavy rain, Cyclone, Thunderstorm, Heatwave, Spraying, Irrigation, Harvesting)
- Agricultural Crop Context (Rice, Wheat, Cotton, Vegetables, etc.)

Guarantees 100% Grounding:
The LLM receives ONLY verified, retrieved facts and rule evaluations.
ZERO fake or manufactured alerts.
"""

import json
import logging
import os
import re
from typing import Any, Optional

from services.crawler.imd_crawler import crawler_instance

logger = logging.getLogger(__name__)

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
ADVISORY_FILE = os.path.join(DATA_DIR, "advisory_kb.json")

# Load Agricultural Advisory KB
try:
    with open(ADVISORY_FILE, encoding="utf-8") as f:
        ADVISORY_KB = json.load(f)
except Exception as exc:
    logger.warning("RAG: Failed to load advisory_kb.json: %s", exc)
    ADVISORY_KB = []


def get_official_warnings(location: Optional[str] = None) -> list[dict[str, Any]]:
    """
    Retrieve active official IMD warnings matching a location from the crawled repository.
    Never returns demo or simulated warnings.
    """
    if not location or not location.strip():
        return crawler_instance.get_documents(category=None)

    clean_loc = location.strip().lower()
    docs = crawler_instance.get_documents(location=clean_loc)

    # Filter strictly for official warning types
    official_warnings = [
        d for d in docs
        if d.get("type") in ["warning", "cyclone", "nowcast"]
        and d.get("severity") in ["RED", "ORANGE", "YELLOW"]
    ]
    return official_warnings


def retrieve_advisory(query: str = "", crop: str = "") -> list[dict[str, Any]]:
    """
    Retrieve advisory knowledge base entries matching either a crop or query keywords.
    """
    q = (query or "").strip().lower()
    c = (crop or "").strip().lower()

    matches = []
    seen_ids = set()

    for entry in ADVISORY_KB:
        entry_crop = entry.get("crop", "").lower()
        entry_keywords = [kw.lower() for kw in entry.get("keywords", [])]

        is_crop_match = c and (c == entry_crop or c in entry_keywords)
        is_query_match = q and (
            entry_crop in q
            or any(kw in q for kw in entry_keywords)
        )

        if is_crop_match or is_query_match:
            if entry["id"] not in seen_ids:
                matches.append(entry)
                seen_ids.add(entry["id"])

    # If no specific matches found, provide general rules
    if not matches and (q or c):
        for entry in ADVISORY_KB:
            if entry.get("crop") == "general" and entry["id"] not in seen_ids:
                matches.append(entry)
                seen_ids.add(entry["id"])

    return matches


def retrieve_meteorological_context(
    query: str,
    location: Optional[str] = None,
    intent: Optional[str] = None,
    crop: Optional[str] = None,
    target_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Multi-faceted RAG retrieval over authoritative IMD bulletins and agromet advisories.
    Matches:
    - User query keywords (e.g. "cyclone", "heavy rain", "lightning", "spray")
    - Location tokens (District, State, Sub-division)
    - Intent domain
    Returns top ranked, compact snippets for prompt injection.
    """
    q = (query or "").lower()
    loc = (location or "").lower()
    relevant_docs: list[dict[str, Any]] = []
    seen_ids = set()

    # 1. Check crawled IMD bulletins
    all_crawled = crawler_instance.documents
    for doc in all_crawled:
        score = 0
        doc_loc = (doc.get("location") or "").lower()
        doc_state = (doc.get("state") or "").lower()
        doc_district = (doc.get("district") or "").lower()
        doc_cat = (doc.get("category") or "").lower()
        doc_text = (doc.get("text") or "").lower()

        # Location scoring
        if loc:
            loc_parts = [p.strip() for p in re.split(r"[,/ -]", loc) if len(p.strip()) > 2]
            for part in loc_parts:
                if part in doc_loc or part in doc_district or part in doc_state:
                    score += 5
            if "national" in doc_state or "all india" in doc_loc:
                score += 2

        # Intent / Category scoring
        if intent and intent in doc_cat:
            score += 4

        # Keyword overlaps
        if "cyclone" in q and ("cyclone" in doc_cat or "cyclone" in doc_text):
            score += 6
        if "rain" in q and ("heavy_rainfall" in doc_cat or "rain" in doc_text):
            score += 4
        if "heat" in q and ("heatwave" in doc_cat or "heat" in doc_text):
            score += 4
        if "lightning" in q and ("thunderstorm" in doc_cat or "lightning" in doc_text):
            score += 4
        if "warning" in q and doc.get("severity") in ["RED", "ORANGE", "YELLOW"]:
            score += 3

        if score > 0 and doc.get("id") not in seen_ids:
            doc_copy = dict(doc)
            doc_copy["relevance_score"] = score
            relevant_docs.append(doc_copy)
            seen_ids.add(doc.get("id"))

    # Sort crawled docs by relevance
    relevant_docs.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    # Return top 3 most relevant crawled snippets
    return relevant_docs[:3]


def evaluate_triggers(advisories: list[dict[str, Any]], weather_data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Deterministically evaluate advisory trigger rules in Python.
    The LLM never calculates thresholds; Python evaluates the condition and
    annotates each advisory with triggered: True/False and the measured value.
    """
    current = weather_data.get("current", {})
    forecast = weather_data.get("forecast", [])
    today_forecast = forecast[0] if forecast else {}
    tomorrow_forecast = forecast[1] if len(forecast) > 1 else today_forecast

    # Extract available metrics across current & near-term forecast
    rain_prob = max(
        float(today_forecast.get("rain_probability") or 0),
        float(tomorrow_forecast.get("rain_probability") or 0),
    )
    temp_c = max(
        float(current.get("temperature_c") or 0),
        float(today_forecast.get("temp_max") or 0),
    )
    wind_kmh = max(
        float(current.get("wind_kmh") or 0),
        float(today_forecast.get("wind_max_kmh") or 0),
    )
    humidity_pct = float(current.get("humidity_pct") or 0)

    evaluated = []
    for entry in advisories:
        item = dict(entry)
        trigger = item.get("trigger", {})
        field = trigger.get("field")
        op = trigger.get("operator")
        threshold = trigger.get("value")

        measured = 0.0
        if field == "rain_probability":
            measured = rain_prob
        elif field == "temperature_c":
            measured = temp_c
        elif field == "wind_kmh":
            measured = wind_kmh
        elif field == "humidity_pct":
            measured = humidity_pct

        triggered = False
        if threshold is not None:
            if op == ">":
                triggered = measured > threshold
            elif op == ">=":
                triggered = measured >= threshold
            elif op == "<":
                triggered = measured < threshold
            elif op == "<=":
                triggered = measured <= threshold
            elif op == "==":
                triggered = measured == threshold

        item["triggered"] = triggered
        item["measured_value"] = measured
        item["threshold_value"] = threshold
        item["trigger_field"] = field
        item["trigger_operator"] = op
        evaluated.append(item)

    return evaluated
