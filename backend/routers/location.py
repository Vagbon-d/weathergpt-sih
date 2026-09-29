"""
Location endpoint for WeatherGPT.

Provides high-accuracy geocoding and reverse geocoding via Photon OpenStreetMap API.
"""

from fastapi import APIRouter, HTTPException, Query
from services.location import photon_service

router = APIRouter(prefix="/location", tags=["location"])


import logging

logger = logging.getLogger(__name__)


@router.get("/search")
async def search_location(
    q: str = Query("", description="Place, city, village, district, or landmark to search"),
    limit: int = Query(6, ge=1, le=15, description="Maximum number of candidates to return"),
):
    """
    Search for places, cities, villages, or districts in India.
    Returns normalized candidates with latitude, longitude, district, state, and country.
    Always returns clean JSON without exposing raw exceptions to frontend.
    """
    query = (q or "").strip()
    if not query or len(query) < 2:
        return {
            "success": True,
            "query": query,
            "count": 0,
            "results": [],
        }

    try:
        results = await photon_service.search_locations(query=query, limit=limit)
        return {
            "success": True,
            "query": query,
            "count": len(results),
            "results": results,
        }
    except Exception as exc:
        logger.error("Location search failed for '%s': %s", query, exc)
        return {
            "success": False,
            "message": "Location search is temporarily unavailable.",
            "query": query,
            "count": 0,
            "results": [],
        }


@router.get("/reverse")
async def reverse_location(
    lat: float | None = Query(None, description="Latitude shorthand"),
    lon: float | None = Query(None, description="Longitude shorthand"),
    latitude: float | None = Query(None, description="Latitude full name"),
    longitude: float | None = Query(None, description="Longitude full name"),
):
    """
    Reverse geocode coordinates to a canonical Indian location details dictionary.
    Supports both 'lat'/'lon' and 'latitude'/'longitude' parameter names.
    """
    actual_lat = lat if lat is not None else latitude
    actual_lon = lon if lon is not None else longitude

    if actual_lat is None or actual_lon is None:
        raise HTTPException(status_code=400, detail="Latitude and longitude coordinates are required.")

    if not (-90.0 <= actual_lat <= 90.0) or not (-180.0 <= actual_lon <= 180.0):
        raise HTTPException(status_code=400, detail="Coordinates out of valid geographical bounds.")

    resolved = await photon_service.reverse_geocode(latitude=actual_lat, longitude=actual_lon)
    return resolved
