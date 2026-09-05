"""
Lightweight retrieval and deterministic rule evaluation layer.
No vector database or embeddings: keyword and crop matching with
deterministic Python rule evaluation ensures agricultural thresholds
are verified mathematically before prompting the LLM.

The LLM is strictly a language layer and is never asked to calculate
whether a weather threshold is triggered.
"""

import json
import os
from typing import Any

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

with open(os.path.join(DATA_DIR, "advisory_kb.json"), encoding="utf-8") as f:
    ADVISORY_KB = json.load(f)

with open(os.path.join(DATA_DIR, "alerts_demo.json"), encoding="utf-8") as f:
    ALERTS = json.load(f)


def get_alerts(location: str | None = None) -> list[dict[str, Any]]:
    """
    Return demo alerts, filtered by case-insensitive substring location match.
    Every demo alert contains 'DEMO' and 'NOT AN OFFICIAL WARNING'.
    """
    if not location or not location.strip():
        return ALERTS

    loc = location.strip().lower()
    return [
        alert for alert in ALERTS
        if loc in alert["location"].lower() or alert["location"].lower() in loc
    ]


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
