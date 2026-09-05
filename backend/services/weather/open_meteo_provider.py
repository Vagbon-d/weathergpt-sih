"""
Open-Meteo Weather & Numerical Model Forecast Provider.

Provides high-resolution numerical weather forecasts, hourly projections,
precipitation probabilities, wind speeds, and multi-day daily forecasts.
"""

import asyncio
import logging
from typing import Any
import httpx

from services.weather.base import WeatherProvider, SourceType

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def get_value(values: list, index: int, default: Any = None) -> Any:
    try:
        val = values[index]
        return default if val is None else val
    except (IndexError, TypeError):
        return default


class OpenMeteoProvider(WeatherProvider):
    name = "Open-Meteo"
    authority_priority = 5  # Authoritative for numerical model forecast

    async def fetch_current(
        self, latitude: float, longitude: float, location_name: str = ""
    ) -> dict[str, Any] | None:
        """Fetch current weather data."""
        data = await self.fetch_forecast(latitude, longitude, days=1)
        return data.get("current") if data else None

    async def fetch_forecast(
        self, latitude: float, longitude: float, days: int = 7
    ) -> dict[str, Any] | None:
        """
        Fetch current weather, hourly forecast (next 24 hours), and 7-day daily forecast.
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,"
                "relative_humidity_2m,"
                "apparent_temperature,"
                "precipitation,"
                "rain,"
                "showers,"
                "weather_code,"
                "cloud_cover,"
                "wind_speed_10m,"
                "wind_gusts_10m"
            ),
            "hourly": (
                "temperature_2m,"
                "relative_humidity_2m,"
                "precipitation_probability,"
                "weather_code,"
                "wind_speed_10m"
            ),
            "daily": (
                "weather_code,"
                "temperature_2m_max,"
                "temperature_2m_min,"
                "apparent_temperature_max,"
                "apparent_temperature_min,"
                "precipitation_sum,"
                "rain_sum,"
                "showers_sum,"
                "precipitation_probability_max,"
                "precipitation_hours,"
                "wind_speed_10m_max,"
                "wind_gusts_10m_max,"
                "uv_index_max,"
                "sunrise,"
                "sunset"
            ),
            "timezone": "auto",
            "forecast_days": max(1, min(days, 7)),
        }

        headers = {"User-Agent": "WeatherGPT-Prototype/1.0"}

        data = None
        last_exc = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(FORECAST_URL, params=params, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    break
            except Exception as exc:
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(0.5)

        if not data:
            logger.warning("Open-Meteo fetch failed: %s", last_exc)
            return None

        current = data.get("current", {})
        daily = data.get("daily", {})
        hourly = data.get("hourly", {})

        current_code = current.get("weather_code")
        current_data = {
            "temperature_c": current.get("temperature_2m"),
            "feels_like_c": current.get("apparent_temperature"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_kmh": current.get("wind_speed_10m"),
            "wind_gust_kmh": current.get("wind_gusts_10m"),
            "precipitation_mm": current.get("precipitation"),
            "rain_mm": current.get("rain"),
            "showers_mm": current.get("showers"),
            "cloud_cover_pct": current.get("cloud_cover"),
            "condition": WEATHER_CODE_MAP.get(current_code, "Unknown"),
            "weather_code": current_code,
            "source": SourceType.MODEL_FORECAST,
        }

        # Format Daily Forecast
        dates = daily.get("time", [])
        daily_forecast = []
        for i in range(len(dates)):
            wcode = get_value(daily.get("weather_code", []), i)
            daily_forecast.append({
                "date": dates[i],
                "condition": WEATHER_CODE_MAP.get(wcode, "Clear"),
                "weather_code": wcode,
                "temp_min": get_value(daily.get("temperature_2m_min", []), i),
                "temp_max": get_value(daily.get("temperature_2m_max", []), i),
                "feels_like_min": get_value(daily.get("apparent_temperature_min", []), i),
                "feels_like_max": get_value(daily.get("apparent_temperature_max", []), i),
                "rain_probability": get_value(daily.get("precipitation_probability_max", []), i, 0),
                "precipitation_mm": get_value(daily.get("precipitation_sum", []), i, 0.0),
                "rain_mm": get_value(daily.get("rain_sum", []), i, 0.0),
                "showers_mm": get_value(daily.get("showers_sum", []), i, 0.0),
                "precipitation_hours": get_value(daily.get("precipitation_hours", []), i, 0.0),
                "wind_max_kmh": get_value(daily.get("wind_speed_10m_max", []), i),
                "gust_max_kmh": get_value(daily.get("wind_gusts_10m_max", []), i),
                "uv_index": get_value(daily.get("uv_index_max", []), i),
                "sunrise": get_value(daily.get("sunrise", []), i),
                "sunset": get_value(daily.get("sunset", []), i),
                "source": SourceType.MODEL_FORECAST,
            })

        # Format Hourly Forecast (First 72 hours to support temporal queries like tomorrow morning/afternoon)
        hourly_times = hourly.get("time", [])[:72]
        hourly_forecast = []
        for i in range(len(hourly_times)):
            hwcode = get_value(hourly.get("weather_code", []), i)
            hourly_forecast.append({
                "time": hourly_times[i],
                "temperature_c": get_value(hourly.get("temperature_2m", []), i),
                "humidity_pct": get_value(hourly.get("relative_humidity_2m", []), i),
                "rain_probability": get_value(hourly.get("precipitation_probability", []), i, 0),
                "wind_kmh": get_value(hourly.get("wind_speed_10m", []), i),
                "condition": WEATHER_CODE_MAP.get(hwcode, "Clear"),
            })

        return {
            "current": current_data,
            "forecast": daily_forecast,
            "hourly": hourly_forecast,
        }

    async def fetch_warnings(
        self, latitude: float, longitude: float, district: str = "", state: str = ""
    ) -> list[dict[str, Any]]:
        # Open-Meteo does not issue official warnings
        return []
