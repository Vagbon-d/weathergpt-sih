"""
India Meteorological Department (IMD) Weather & Warning Provider.

Highest authority for official meteorological warnings, cyclone tracks,
nowcasts, and Agromet advisories in India.
"""

import os
import json
import logging
from typing import Any
import httpx

from services.weather.base import WeatherProvider, SourceType

logger = logging.getLogger(__name__)

IMD_API_KEY = os.getenv("IMD_API_KEY", "").strip()
IMD_BASE_URL = os.getenv("IMD_BASE_URL", "https://api.imd.gov.in").rstrip("/")

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
ALERTS_FILE = os.path.join(DATA_DIR, "alerts_demo.json")

# Load local demo alert database for fallback when IMD API credentials are unconfigured
try:
    with open(ALERTS_FILE, encoding="utf-8") as f:
        DEMO_ALERTS = json.load(f)
except Exception:
    DEMO_ALERTS = []


class IMDProvider(WeatherProvider):
    name = "IMD"
    authority_priority = 10  # Highest authority for Indian warnings

    def __init__(self):
        self.has_api_key = bool(IMD_API_KEY)
        if not self.has_api_key:
            logger.info("IMDProvider: IMD_API_KEY is not set. Operating in verified simulation/demo mode.")

    async def fetch_current(
        self, latitude: float, longitude: float, location_name: str = ""
    ) -> dict[str, Any] | None:
        """
        Fetch real-time station observation from IMD AWS/ARG network if key configured.
        """
        if not self.has_api_key:
            return None

        url = f"{IMD_BASE_URL}/v1/observations/current"
        headers = {"X-API-KEY": IMD_API_KEY, "Accept": "application/json"}
        params = {"lat": latitude, "lon": longitude}

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "temperature_c": data.get("temperature"),
                        "humidity_pct": data.get("humidity"),
                        "wind_kmh": data.get("wind_speed"),
                        "rainfall_mm": data.get("rainfall_last_24h"),
                        "source": SourceType.IMD_OFFICIAL,
                    }
        except Exception as exc:
            logger.debug("IMD live observation unavailable: %s", exc)

        return None

    async def fetch_forecast(
        self, latitude: float, longitude: float, days: int = 7
    ) -> dict[str, Any] | None:
        """
        Fetch IMD City/District-level multi-day forecast if key configured.
        """
        if not self.has_api_key:
            return None

        url = f"{IMD_BASE_URL}/v1/forecast/district"
        headers = {"X-API-KEY": IMD_API_KEY, "Accept": "application/json"}
        params = {"lat": latitude, "lon": longitude, "days": days}

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
        except Exception as exc:
            logger.debug("IMD forecast API unavailable: %s", exc)

        return None

    async def fetch_warnings(
        self,
        latitude: float,
        longitude: float,
        district: str = "",
        state: str = "",
        location_name: str = "",
        current_weather: dict[str, Any] | None = None,
        forecast: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch active official IMD warnings (Color-coded: Green, Yellow, Orange, Red).
        Evaluates real data-supported meteorological conditions:
        - Heavy rain >= 64.5mm
        - Thunderstorm / Hail codes 95, 96, 99
        - Heatwave >= 40°C
        - High wind gusts >= 50km/h
        - Dense fog
        Only matches simulated demo feed if the user explicitly queried a simulated drill location.
        """
        # 1. Try Live IMD Warning API if credentials provided
        if self.has_api_key:
            url = f"{IMD_BASE_URL}/v1/warnings/district"
            headers = {"X-API-KEY": IMD_API_KEY, "Accept": "application/json"}
            params = {"lat": latitude, "lon": longitude, "district": district}
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get(url, params=params, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_warnings = data.get("warnings", [])
                        if raw_warnings:
                            normalized = []
                            for w in raw_warnings:
                                normalized.append({
                                    "id": w.get("id", "IMD-WARN"),
                                    "hazard": w.get("hazard", "Weather Warning"),
                                    "severity": w.get("severity", "YELLOW").upper(),
                                    "location": district or state or location_name or "Local Area",
                                    "message": w.get("message", ""),
                                    "advisory": "Follow local district disaster management guidelines.",
                                    "valid_for": w.get("valid_for", "Next 24 hours"),
                                    "source": "IMD Official",
                                    "is_official": True,
                                })
                            return normalized
            except Exception as exc:
                logger.warning("IMD live warning API call failed: %s", exc)

        # 2. Evaluate Real Meteorological Thresholds from verified weather data
        curr = current_weather or {}
        fcst_today = (forecast[0] if forecast and len(forecast) > 0 else {})
        loc_display = district or state or location_name or f"Lat {latitude:.2f}, Lon {longitude:.2f}"

        data_alerts: list[dict[str, Any]] = []

        # Rainfall evaluation (IMD criteria: >= 64.5mm is Heavy Rain, >= 115.6mm is Very Heavy Rain)
        cur_precip = float(curr.get("precipitation_mm") or 0.0)
        fcst_precip = float(fcst_today.get("precipitation_sum_mm") or 0.0)
        rain_prob = float(fcst_today.get("rain_probability") or 0.0)
        max_rain = max(cur_precip, fcst_precip)

        if max_rain >= 115.6:
            data_alerts.append({
                "id": f"IMD-RAIN-EXTREME-{int(abs(latitude)*100)}",
                "hazard": "IMD Very Heavy Rainfall Alert",
                "severity": "RED",
                "location": loc_display,
                "message": f"Extreme localized rainfall ({max_rain:.1f}mm) recorded or forecast. High danger of localized flooding, waterlogging in low-lying fields, and transport disruption.",
                "advisory": "Provide continuous drainage in fields and move machinery to higher elevation.",
                "valid_for": "Next 24 hours",
                "source": "IMD Threshold Analysis",
                "is_official": False,
            })
        elif max_rain >= 64.5:
            data_alerts.append({
                "id": f"IMD-RAIN-HEAVY-{int(abs(latitude)*100)}",
                "hazard": "IMD Heavy Rainfall Warning",
                "severity": "ORANGE",
                "location": loc_display,
                "message": f"Heavy rainfall ({max_rain:.1f}mm) expected. Saturated soil and localized runoff likely.",
                "advisory": "Postpone all pesticide and fertilizer applications. Keep field drainage channels clear.",
                "valid_for": "Next 24 hours",
                "source": "IMD Threshold Analysis",
                "is_official": False,
            })
        elif max_rain >= 35.5 or rain_prob >= 80:
            data_alerts.append({
                "id": f"IMD-RAIN-WATCH-{int(abs(latitude)*100)}",
                "hazard": "IMD Moderate to Heavy Rain Advisory",
                "severity": "YELLOW",
                "location": loc_display,
                "message": f"Elevated rainfall probability ({rain_prob:.0f}%) with up to {max_rain:.1f}mm precipitation expected.",
                "advisory": "Monitor bunds and delay post-harvest crop drying.",
                "valid_for": "Next 24 hours",
                "source": "IMD Threshold Analysis",
                "is_official": False,
            })

        # Thunderstorm & Lightning evaluation (WMO/Open-Meteo codes 95, 96, 99)
        w_code = curr.get("weather_code") or fcst_today.get("weather_code")
        if w_code == 99:
            data_alerts.append({
                "id": f"IMD-THUNDER-HAIL-{int(abs(latitude)*100)}",
                "hazard": "Severe Thunderstorm & Heavy Hail Alert",
                "severity": "RED",
                "location": loc_display,
                "message": "Severe thunderstorm accompanied by damaging hail, intense lightning, and squally gusts forecast.",
                "advisory": "Move livestock to covered shelters immediately and avoid open fields or metal structures.",
                "valid_for": "Next 12 hours",
                "source": "IMD Threshold Analysis",
                "is_official": False,
            })
        elif w_code in [95, 96]:
            data_alerts.append({
                "id": f"IMD-THUNDER-{int(abs(latitude)*100)}",
                "hazard": "Thunderstorm & Lightning Warning",
                "severity": "ORANGE",
                "location": loc_display,
                "message": "Thunderstorm activity with lightning strikes and gusty convective winds detected in the sector.",
                "advisory": "Do not seek shelter under tall, isolated trees or near water bodies.",
                "valid_for": "Next 12 hours",
                "source": "IMD Threshold Analysis",
                "is_official": False,
            })

        # Heatwave evaluation (IMD: >= 40°C in plains, >= 45°C is Severe)
        t_max = float(fcst_today.get("temp_max") or curr.get("temperature_c") or 0.0)
        if t_max >= 45.0:
            data_alerts.append({
                "id": f"IMD-HEAT-SEVERE-{int(abs(latitude)*100)}",
                "hazard": "Severe Heatwave Warning",
                "severity": "RED",
                "location": loc_display,
                "message": f"Severe heatwave conditions with peak temperatures reaching {t_max:.1f}°C forecast.",
                "advisory": "High risk of heat illness and crop dehydration. Suspend field work between 11 AM and 4 PM.",
                "valid_for": "Next 24 hours",
                "source": "IMD Threshold Analysis",
                "is_official": False,
            })
        elif t_max >= 40.0:
            data_alerts.append({
                "id": f"IMD-HEAT-WARN-{int(abs(latitude)*100)}",
                "hazard": "IMD Heatwave Advisory",
                "severity": "ORANGE",
                "location": loc_display,
                "message": f"High daytime temperature reaching {t_max:.1f}°C expected.",
                "advisory": "Apply light and frequent crop irrigation in early morning to prevent thermal stress.",
                "valid_for": "Next 24 hours",
                "source": "IMD Threshold Analysis",
                "is_official": False,
            })

        # High Wind / Gale evaluation (>= 50 km/h is Strong, >= 70 km/h is Gale)
        w_speed = float(curr.get("wind_kmh") or fcst_today.get("wind_speed_max_kmh") or 0.0)
        if w_speed >= 70.0:
            data_alerts.append({
                "id": f"IMD-WIND-GALE-{int(abs(latitude)*100)}",
                "hazard": "Gale Wind Warning",
                "severity": "RED",
                "location": loc_display,
                "message": f"Dangerous gale-force winds exceeding 70 km/h ({w_speed:.0f} km/h) expected.",
                "advisory": "Secure temporary sheds, propping for banana/sugarcane crops, and stay indoors.",
                "valid_for": "Next 18 hours",
                "source": "IMD Threshold Analysis",
                "is_official": False,
            })
        elif w_speed >= 50.0:
            data_alerts.append({
                "id": f"IMD-WIND-STRONG-{int(abs(latitude)*100)}",
                "hazard": "Strong Wind Advisory",
                "severity": "ORANGE",
                "location": loc_display,
                "message": f"Strong surface wind gusts reaching {w_speed:.0f} km/h forecast.",
                "advisory": "Avoid aerial and knapsack spraying to prevent chemical spray drift.",
                "valid_for": "Next 18 hours",
                "source": "IMD Threshold Analysis",
                "is_official": False,
            })

        # Dense Fog evaluation
        if w_code in [45, 48]:
            data_alerts.append({
                "id": f"IMD-FOG-WATCH-{int(abs(latitude)*100)}",
                "hazard": "Dense Fog Advisory",
                "severity": "YELLOW",
                "location": loc_display,
                "message": "Dense fog causing sharply reduced horizontal visibility during early morning hours.",
                "advisory": "Drive cautiously with low-beam fog lights. Watch for early blight in potato and tomato crops.",
                "valid_for": "Next 12 hours",
                "source": "IMD Threshold Analysis",
                "is_official": False,
            })

        if data_alerts:
            return data_alerts

        # 3. Only match simulated demo alerts if user explicitly queries a demo drill location
        search_terms = [t.lower() for t in [district, state, location_name] if t]
        matched_demo = []
        for item in DEMO_ALERTS:
            item_loc = item.get("location", "").lower()
            if any(term in item_loc or item_loc in term for term in search_terms if len(term) > 2):
                hazard = item.get("hazard", "")
                severity = "YELLOW"
                if any(w in hazard.lower() for w in ["cyclone", "flood", "severe"]):
                    severity = "ORANGE"
                if "red" in hazard.lower() or "extreme" in hazard.lower():
                    severity = "RED"

                matched_demo.append({
                    "id": item.get("id"),
                    "hazard": hazard,
                    "severity": severity,
                    "location": item.get("location"),
                    "message": item.get("message"),
                    "advisory": "Simulation drill scenario for prototype demonstration.",
                    "valid_for": item.get("valid_for", "Next 24 hours"),
                    "source": "IMD (Demo Simulation)",
                    "is_official": False,
                })

        return matched_demo
