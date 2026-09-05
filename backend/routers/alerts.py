"""
Alerts endpoint for WeatherGPT.
Demo alerts are retrieved from local simulation data and explicitly labeled
as DEMO ALERTS -- NOT OFFICIAL WARNINGS to ensure user safety and compliance.
"""

from fastapi import APIRouter
from services import rag_service
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
        try:
            weather = await weather_service.get_current_and_forecast(location=location.strip())
            return {"alerts": weather.get("warnings", [])}
        except Exception:
            return {"alerts": rag_service.get_alerts(location)}

    return {"alerts": []}
