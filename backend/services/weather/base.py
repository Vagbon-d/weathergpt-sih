"""
Base Weather Provider interfaces and normalized data models for WeatherGPT.
"""

from abc import ABC, abstractmethod
from typing import Any


class SourceType:
    OBSERVED = "OBSERVED"
    IMD_OFFICIAL = "IMD_OFFICIAL"
    MODEL_FORECAST = "MODEL_FORECAST"
    DERIVED = "DERIVED"


class WeatherProvider(ABC):
    """
    Abstract interface for Weather Data Providers.
    """
    name: str = "BaseProvider"
    authority_priority: int = 1  # Higher number means higher authority

    @abstractmethod
    async def fetch_current(
        self, latitude: float, longitude: float, location_name: str = ""
    ) -> dict[str, Any] | None:
        """Fetch real-time observed or current weather."""
        pass

    @abstractmethod
    async def fetch_forecast(
        self, latitude: float, longitude: float, days: int = 7
    ) -> dict[str, Any] | None:
        """Fetch multi-day daily and hourly forecast."""
        pass

    @abstractmethod
    async def fetch_warnings(
        self, latitude: float, longitude: float, district: str = "", state: str = ""
    ) -> list[dict[str, Any]]:
        """Fetch active meteorological warnings (Green, Yellow, Orange, Red)."""
        pass
