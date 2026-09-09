"""
Alerts endpoint for WeatherGPT (SIH26068).

Returns active authoritative IMD meteorological warnings and data-supported alerts.
Guarantees zero fake or manufactured alerts.
"""

from fastapi import APIRouter
from services.weather.imd_provider import IMDProvider

router = APIRouter()
_imd_provider = IMDProvider()


@router.get("/alerts")
async def get_alerts(
    location: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
):
    """
    Return active alerts filtered by location or coordinates.
    Evaluates official IMD warnings and real data-supported meteorological thresholds.
    """
    from services import weather_service

    if latitude is not None and longitude is not None:
        try:
            weather = await weather_service.get_current_and_forecast(
                latitude=latitude, longitude=longitude
            )
            return {"alerts": weather.get("warnings", [])}
        except Exception:
            warnings = await _imd_provider.fetch_warnings(
                latitude=latitude,
                longitude=longitude,
                district=location or "",
            )
            return {"alerts": warnings}

    if location and location.strip():
        loc_str = location.strip()
        try:
            weather = await weather_service.get_current_and_forecast(location=loc_str)
            return {"alerts": weather.get("warnings", [])}
        except Exception:
            warnings = await _imd_provider.fetch_warnings(
                latitude=0.0,
                longitude=0.0,
                district=loc_str,
            )
            return {"alerts": warnings}

    return {"alerts": []}
