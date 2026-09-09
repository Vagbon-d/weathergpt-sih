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
    district: str = "",
    state: str = "",
) -> dict[str, Any]:
    """
    Fetch current weather, multi-day forecast, hourly projections, and warnings.
    Supports coordinates or location search.
    Requires either coordinates or a non-empty location.

    CRITICAL LOCATION ARCHITECTURE RULE:
    1. If a human-readable location name is provided, it is NEVER overwritten by a reverse-geocode.
    2. Coordinates must match the requested location. If coordinates point to an unrelated or foreign
       location (e.g. England GPS while viewing a Goa location), the coordinates are corrected via geocoding.
    """
    has_coords = latitude is not None and longitude is not None
    has_name = bool(location and str(location).strip())

    if not has_coords and not has_name:
        raise ValueError("Please provide a location name or coordinates. No default location is configured.")

    req_loc_name = str(location).strip() if has_name else ""
    lat: float = float(latitude) if has_coords else 0.0
    lon: float = float(longitude) if has_coords else 0.0

    # 1. Detect and correct coordinate vs named location mismatch
    # E.g. User header is 'Primary Health Centre, Shiroda, Ponda, Goa' (India: ~15.3, ~74.0),
    # but browser GPS or proxy sent UK/foreign coordinates (e.g. 53.858, -0.435).
    if has_name and has_coords:
        is_outside_india = (lat > 38.5 or lat < 6.5 or lon < 68.0 or lon > 97.5)
        name_lower = req_loc_name.lower()
        indian_cues = ["goa", "ponda", "shiroda", "panjim", "panaji", "margao", "mapusa", "maharashtra", "pune", "mumbai", "india", "karnataka", "delhi", "centre", "health"]
        has_indian_cue = any(c in name_lower for c in indian_cues)

        if is_outside_india and has_indian_cue:
            logger.warning(
                "Coordinate mismatch detected: Location '%s' is in India, but coordinates (%f, %f) are foreign. Re-geocoding.",
                req_loc_name, lat, lon
            )
            try:
                lat, lon, geo_canon = await geocode(req_loc_name)
            except Exception as e:
                logger.error("Failed to re-geocode '%s': %s", req_loc_name, e)

    # 2. Determine final location name and coordinates
    if has_coords and not has_name:
        location_details = await photon_service.reverse_geocode(lat, lon)
        location_name = location_details.get("displayName") or f"Lat {lat:.2f}, Lon {lon:.2f}"
        district = district or location_details.get("district", "")
        state = state or location_details.get("state", "")
    elif has_name and not has_coords:
        lat, lon, location_name = await geocode(req_loc_name)
    else:
        # Both provided and validated
        location_name = req_loc_name

    weather_data = await aggregator.get_weather(
        latitude=lat,
        longitude=lon,
        location_name=location_name,
        district=district,
        state=state,
    )

    # Attach Section 15 requested and retrieved location identity records
    weather_data["requested_location"] = {
        "name": location_name,
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
    }
    weather_data["retrieved_location"] = {
        "name": weather_data.get("location", location_name),
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
    }

    return weather_data
