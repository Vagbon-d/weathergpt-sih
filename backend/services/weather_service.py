"""
Weather Service Access Layer for WeatherGPT.

Aggregates authoritative Indian weather data and warnings from IMD
and high-resolution numerical model forecasts from Open-Meteo.
Uses Photon for precise geocoding and reverse geocoding.

CRITICAL RULE:
No default city or hardcoded fallback location is ever used.
If location or coordinates are not provided, an explicit error is raised.
The LLM is NEVER the source of weather facts or coordinates.
"""

import logging
from typing import Any

from services.location import photon_service
from services.weather.aggregator import aggregator

logger = logging.getLogger(__name__)


async def geocode(location: str) -> tuple[float, float, str]:
    """
    Geocode an Indian village, town, city, district, or landmark via Photon API.
    Raises ValueError if the location cannot be resolved.
    """
    if not location or not location.strip():
        raise ValueError("Location query cannot be empty.")

    cleaned = location.strip()
    results = await photon_service.search_locations(query=cleaned, limit=1)
    if results:
        res = results[0]
        return res["latitude"], res["longitude"], res["displayName"]

    raise ValueError(
        f"Could not resolve location '{cleaned}'. "
        "Please check the spelling or search for your village, district, town, or state."
    )


async def reverse_geocode(latitude: float, longitude: float) -> str:
    """
    Reverse geocode coordinates to a human-readable location string.
    """
    details = await photon_service.reverse_geocode(latitude=latitude, longitude=longitude)
    return details.get("displayName") or f"Lat {latitude:.2f}, Lon {longitude:.2f}"


async def get_current_and_forecast(
    location: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    """
    Fetch current weather, multi-day forecast, hourly projections, and warnings.
    Supports coordinates or location search.
    Requires either coordinates or a non-empty location.
    """
    if latitude is not None and longitude is not None:
        lat = float(latitude)
        lon = float(longitude)
        location_details = await photon_service.reverse_geocode(lat, lon)
        location_name = location_details.get("displayName") or f"Lat {lat:.2f}, Lon {lon:.2f}"
        district = location_details.get("district", "")
        state = location_details.get("state", "")
    elif location and location.strip():
        lat, lon, location_name = await geocode(location)
        district = ""
        state = ""
    else:
        raise ValueError("Please provide a location name or coordinates. No default location is configured.")

    return await aggregator.get_weather(
        latitude=lat,
        longitude=lon,
        location_name=location_name,
        district=district,
        state=state,
    )
