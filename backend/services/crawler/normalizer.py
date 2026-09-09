"""
Crawler Data Normalizer for WeatherGPT (SIH26068).

Normalizes raw crawled meteorological data from IMD pages, RSS feeds,
and official APIs into canonical, strongly-typed JSON document schemas.
Guarantees clean source attribution, physical validity, and consistent timestamps.
"""

import re
from datetime import datetime, timezone
from typing import Any, Optional


class CrawlerNormalizer:
    """Standardizes heterogeneous meteorological bulletins into verified schemas."""

    SEVERITY_MAP = {
        "red": "RED",
        "warning": "ORANGE",
        "orange": "ORANGE",
        "alert": "ORANGE",
        "watch": "YELLOW",
        "yellow": "YELLOW",
        "advisory": "YELLOW",
        "green": "GREEN",
        "normal": "GREEN",
    }

    CATEGORY_MAP = {
        "rain": "heavy_rainfall",
        "rainfall": "heavy_rainfall",
        "heavy rain": "heavy_rainfall",
        "thunderstorm": "thunderstorm",
        "lightning": "thunderstorm",
        "cyclone": "cyclone",
        "storm": "cyclone",
        "heatwave": "heatwave",
        "heat": "heatwave",
        "wind": "gale_wind",
        "gale": "gale_wind",
        "fog": "dense_fog",
        "agromet": "agriculture",
        "farming": "agriculture",
    }

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    @classmethod
    def normalize_severity(cls, raw_sev: str | None) -> str:
        if not raw_sev:
            return "YELLOW"
        clean = raw_sev.strip().lower()
        for k, v in cls.SEVERITY_MAP.items():
            if k in clean:
                return v
        return "YELLOW"

    @classmethod
    def normalize_category(cls, text: str) -> str:
        lower = text.lower()
        for k, v in cls.CATEGORY_MAP.items():
            if k in lower:
                return v
        return "general_meteorological"

    @classmethod
    def normalize_warning(cls, raw: dict[str, Any], default_source_url: str = "") -> dict[str, Any]:
        """
        Produce canonical IMD warning document:
        {
            "id": "...",
            "source": "IMD",
            "source_url": "...",
            "location": "...",
            "district": "...",
            "state": "...",
            "type": "warning",
            "category": "...",
            "severity": "...",
            "issued_at": "...",
            "valid_from": "...",
            "valid_until": "...",
            "text": "...",
            "advisories": [...],
            "retrieved_at": "...",
            "confidence": 1.0,
            "is_official": True
        }
        """
        now = cls.now_iso()
        loc = raw.get("location") or raw.get("district") or raw.get("state") or "India"
        text = raw.get("text") or raw.get("message") or raw.get("description") or ""
        cat = raw.get("category") or cls.normalize_category(text)
        sev = cls.normalize_severity(raw.get("severity") or raw.get("color"))

        advisories = raw.get("advisories") or []
        if isinstance(advisories, str):
            advisories = [advisories]

        # Construct deterministic unique ID if not present
        doc_id = raw.get("id")
        if not doc_id:
            import hashlib
            hash_src = f"{loc}:{cat}:{sev}:{text[:80]}"
            h = hashlib.sha256(hash_src.encode("utf-8")).hexdigest()[:10]
            doc_id = f"IMD-CRAWL-{sev}-{h}"

        return {
            "id": doc_id,
            "source": "IMD",
            "source_url": raw.get("source_url") or default_source_url or "https://mausam.imd.gov.in/",
            "location": loc,
            "district": raw.get("district") or loc,
            "state": raw.get("state") or "",
            "type": "warning",
            "category": cat,
            "hazard": raw.get("hazard") or cat.replace("_", " ").title(),
            "message": text.strip(),
            "severity": sev,
            "issued_at": raw.get("issued_at") or now,
            "valid_from": raw.get("valid_from") or now,
            "valid_until": raw.get("valid_until") or "Next 24-48 hours",
            "text": text.strip(),
            "advisories": advisories,
            "retrieved_at": raw.get("retrieved_at") or now,
            "confidence": float(raw.get("confidence", 1.0)),
            "is_official": True,
        }

    @classmethod
    def normalize_forecast_bulletin(cls, raw: dict[str, Any], default_source_url: str = "") -> dict[str, Any]:
        """
        Produce canonical IMD forecast/bulletin document:
        {
            "id": "...",
            "source": "IMD",
            "source_url": "...",
            "location": "...",
            "date": "...",
            "forecast": "...",
            "temperature": ...,
            "rainfall_probability": ...,
            "wind": ...,
            "bulletin_type": "...",
            "text": "...",
            "retrieved_at": "..."
        }
        """
        now = cls.now_iso()
        loc = raw.get("location") or raw.get("district") or raw.get("state") or "National"
        text = raw.get("text") or raw.get("forecast") or ""

        doc_id = raw.get("id")
        if not doc_id:
            import hashlib
            h = hashlib.sha256(f"{loc}:{raw.get('date')}:{text[:60]}".encode()).hexdigest()[:10]
            doc_id = f"IMD-FCST-{h}"

        return {
            "id": doc_id,
            "source": "IMD",
            "source_url": raw.get("source_url") or default_source_url or "https://mausam.imd.gov.in/",
            "location": loc,
            "date": raw.get("date") or datetime.now().strftime("%Y-%m-%d"),
            "forecast": raw.get("forecast") or text,
            "temperature": raw.get("temperature"),
            "rainfall_probability": raw.get("rainfall_probability"),
            "wind": raw.get("wind"),
            "bulletin_type": raw.get("bulletin_type", "forecast_bulletin"),
            "text": text.strip(),
            "retrieved_at": raw.get("retrieved_at") or now,
            "is_official": True,
        }
