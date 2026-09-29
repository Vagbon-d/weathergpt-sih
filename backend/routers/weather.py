"""
Weather endpoint for WeatherGPT.
Weather data is retrieved from authoritative providers before any LLM processing
so that weather numbers are always authoritative and never hallucinated.
"""

from fastapi import APIRouter, HTTPException
from services import weather_service, advisory_service

router = APIRouter()


@router.get("/weather")
async def get_weather(
    location: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
):
    """
    Retrieve current weather, forecast, and daily action recommendations for an Indian location.
    Returns HTTP 400 if neither location nor coordinates are provided.
    Returns HTTP 404 if the location cannot be resolved.
    Returns HTTP 503 if weather providers are temporarily unreachable.
    """
    has_coords = latitude is not None and longitude is not None
    has_location = bool(location and location.strip())

    if not has_coords and not has_location:
        raise HTTPException(
            status_code=400,
            detail="Please specify a location name or coordinates. No default location is configured.",
        )

    try:
        if has_coords:
            data = await weather_service.get_current_and_forecast(
                location=location.strip() if has_location else None,
                latitude=latitude,
                longitude=longitude,
            )
        else:
            data = await weather_service.get_current_and_forecast(location=location.strip())

        # Attach deterministic daily action recommendations ("What should I do today?")
        data["action_recommendations"] = advisory_service.generate_daily_action_recommendations(data)
        return data
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Weather data service temporarily unavailable: {exc}",
        )
