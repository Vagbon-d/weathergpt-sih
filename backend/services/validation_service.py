"""
Data Validation Service for WeatherGPT.

Validates all incoming weather and forecast metrics against physical bounds
before normalizing, storing, or injecting data into LLM prompts.
Corrupted or impossible numbers are pruned to guarantee data integrity.
"""

from typing import Any
import logging

logger = logging.getLogger(__name__)


def validate_coordinates(lat: Any, lon: Any) -> bool:
    try:
        f_lat = float(lat)
        f_lon = float(lon)
        return -90.0 <= f_lat <= 90.0 and -180.0 <= f_lon <= 180.0
    except (ValueError, TypeError):
        return False


def validate_current_metrics(current: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and sanitize current weather metrics.
    """
    clean = dict(current)

    # Temperature validation (-30°C to +60°C for India)
    temp = clean.get("temperature_c")
    if temp is not None:
        try:
            f_temp = float(temp)
            if not (-30.0 <= f_temp <= 60.0):
                logger.warning("Sanitizing out of bounds temperature: %s", temp)
                clean["temperature_c"] = None
        except (ValueError, TypeError):
            clean["temperature_c"] = None

    # Humidity validation (0 - 100%)
    hum = clean.get("humidity_pct")
    if hum is not None:
        try:
            f_hum = float(hum)
            if not (0.0 <= f_hum <= 100.0):
                clean["humidity_pct"] = max(0.0, min(100.0, f_hum))
        except (ValueError, TypeError):
            clean["humidity_pct"] = None

    # Wind speed validation (>= 0 km/h)
    wind = clean.get("wind_kmh")
    if wind is not None:
        try:
            f_wind = float(wind)
            if f_wind < 0:
                clean["wind_kmh"] = 0.0
        except (ValueError, TypeError):
            clean["wind_kmh"] = None

    # Precipitation validation (>= 0 mm)
    precip = clean.get("precipitation_mm")
    if precip is not None:
        try:
            f_precip = float(precip)
            if f_precip < 0:
                clean["precipitation_mm"] = 0.0
        except (ValueError, TypeError):
            clean["precipitation_mm"] = 0.0

    return clean


def validate_forecast_metrics(forecast: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Validate and sanitize multi-day forecast entries.
    """
    valid_entries = []
    for day in forecast:
        d = dict(day)

        # Probability (0 - 100%)
        prob = d.get("rain_probability")
        if prob is not None:
            try:
                f_prob = float(prob)
                d["rain_probability"] = int(max(0, min(100, round(f_prob))))
            except (ValueError, TypeError):
                d["rain_probability"] = 0

        # Precipitation (>= 0)
        precip = d.get("precipitation_mm")
        if precip is not None:
            try:
                d["precipitation_mm"] = max(0.0, float(precip))
            except (ValueError, TypeError):
                d["precipitation_mm"] = 0.0

        valid_entries.append(d)

    return valid_entries
