"""
Weather Provider Aggregator for WeatherGPT.

Merges authoritative Indian observations and official warnings from IMD
with detailed high-resolution model forecasts from Open-Meteo.
Applies data validation and attaches source attribution to every key metric.
"""

import time
import logging
from datetime import datetime, timezone
from typing import Any

from services.weather.base import SourceType
from services.weather.imd_provider import IMDProvider
from services.weather.open_meteo_provider import OpenMeteoProvider
from services.validation_service import (
    validate_coordinates,
    validate_current_metrics,
    validate_forecast_metrics,
)

logger = logging.getLogger(__name__)

# Cache: key -> (timestamp, data)
_AGGREGATOR_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 60.0


class WeatherAggregator:
    def __init__(self):
        self.imd = IMDProvider()
        self.open_meteo = OpenMeteoProvider()

    async def get_weather(
        self,
        latitude: float,
        longitude: float,
        location_name: str = "",
        district: str = "",
        state: str = "",
    ) -> dict[str, Any]:
        """
        Aggregate weather from IMD and Open-Meteo for given coordinates.
        """
        if not validate_coordinates(latitude, longitude):
            raise ValueError(f"Invalid coordinates: ({latitude}, {longitude})")

        cache_key = f"{latitude:.3f},{longitude:.3f}"
        now = time.time()

        if cache_key in _AGGREGATOR_CACHE:
            cached_time, cached_data = _AGGREGATOR_CACHE[cache_key]
            if now - cached_time < CACHE_TTL_SECONDS:
                return cached_data

        # 1. Fetch Open-Meteo model forecast & hourly projections
        om_data = await self.open_meteo.fetch_forecast(latitude, longitude, days=7)

        # 2. Fetch IMD warnings and observations
        imd_obs = await self.imd.fetch_current(latitude, longitude, location_name)
        imd_warnings = await self.imd.fetch_warnings(
            latitude=latitude,
            longitude=longitude,
            district=district,
            state=state,
            location_name=location_name,
            current_weather=om_data.get("current") if om_data else None,
            forecast=om_data.get("forecast") if om_data else None,
        )

        if not om_data and not imd_obs:
            raise RuntimeError(
                "Could not retrieve reliable weather data right now. Please try again shortly."
            )

        # Merge Current Conditions
        current = {}
        sources_used = []

        if om_data and om_data.get("current"):
            current = dict(om_data["current"])
            sources_used.append("Open-Meteo (Model Forecast)")

        # If IMD official observation exists, prioritize real-world station values
        if imd_obs:
            if imd_obs.get("temperature_c") is not None:
                current["temperature_c"] = imd_obs["temperature_c"]
                current["temperature_source"] = SourceType.IMD_OFFICIAL
            if imd_obs.get("humidity_pct") is not None:
                current["humidity_pct"] = imd_obs["humidity_pct"]
            if imd_obs.get("wind_kmh") is not None:
                current["wind_kmh"] = imd_obs["wind_kmh"]
            sources_used.append("IMD (Official Station Observation)")

        current = validate_current_metrics(current)

        # Forecast & Hourly
        forecast = om_data.get("forecast", []) if om_data else []
        forecast = validate_forecast_metrics(forecast)
        hourly = om_data.get("hourly", []) if om_data else []

        if imd_warnings:
            sources_used.append("IMD (Official Meteorological Warnings)")

        iso_timestamp = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )

        display_location = location_name or f"Lat {latitude:.2f}, Lon {longitude:.2f}"

        result = {
            "location": display_location,
            "district": district,
            "state": state,
            "latitude": round(latitude, 4),
            "longitude": round(longitude, 4),
            "current": current,
            "forecast": forecast,
            "hourly": hourly,
            "warnings": imd_warnings,
            "sources": sources_used or ["Open-Meteo"],
            "source": ", ".join(sources_used) or f"Open-Meteo, updated {iso_timestamp}",
            "retrieved_at": iso_timestamp,
        }

        _AGGREGATOR_CACHE[cache_key] = (now, result)
        return result


# Singleton instance
aggregator = WeatherAggregator()
