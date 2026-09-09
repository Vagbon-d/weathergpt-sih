"""
Bulletin Parser for IMD Weather Reports & Bulletins (SIH26068).

Parses official textual, HTML, and JSON bulletins from India Meteorological Department:
- All India Daily Weather Warning Bulletin (NWFC New Delhi)
- Tropical Weather Outlook & Cyclone Warning (RSMC New Delhi)
- State & District Weather Warnings & Nowcasts
- Agromet Advisory Service Bulletins (Meghdoot / IMD Agrimet)

Extracts structured warnings, dates, hazards, color-coded severities,
and actionable agricultural/public protective advisories.
"""

import html
import re
from typing import Any
from services.crawler.normalizer import CrawlerNormalizer


class BulletinParser:
    """Parses raw text and HTML feeds from authoritative IMD bulletins."""

    @staticmethod
    def strip_html(raw_html: str) -> str:
        """Strip HTML tags and unescape entities cleanly using standard library."""
        if not raw_html:
            return ""
        # Remove script and style tags completely
        text = re.sub(r"<(script|style).*?>.*?</\1>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
        # Replace line-breaking elements with newlines
        text = re.sub(r"<(br|p|div|tr|h[1-6]).*?>", "\n", text, flags=re.IGNORECASE)
        # Strip all other tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Unescape HTML entities
        text = html.unescape(text)
        # Normalize whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n", "\n\n", text)
        return text.strip()

    @classmethod
    def parse_bulletin_text(
        cls,
        raw_content: str,
        bulletin_type: str = "all_india_warning",
        source_url: str = "https://mausam.imd.gov.in/",
    ) -> list[dict[str, Any]]:
        """
        Parse raw bulletin text or HTML and return a list of normalized warning documents.
        """
        clean_text = cls.strip_html(raw_content)
        if not clean_text:
            return []

        results = []

        # 1. Look for structured warning segments
        # IMD warnings often contain sections like:
        # "Day 1 (09 Sept): Heavy to very heavy rainfall very likely over..."
        # "Warning for fishermen: Squally weather with wind speed..."
        lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
        full_content = "\n".join(lines)

        # Detect hazard categories in text
        categories_found = []
        if re.search(r"\b(?:heavy|very heavy|extremely heavy)\s+rain", full_content, re.IGNORECASE):
            categories_found.append("heavy_rainfall")
        if re.search(r"\b(?:thunderstorm|lightning|squall)\b", full_content, re.IGNORECASE):
            categories_found.append("thunderstorm")
        if re.search(r"\b(?:cyclone|cyclonic storm|depression|low pressure area)\b", full_content, re.IGNORECASE):
            categories_found.append("cyclone")
        if re.search(r"\b(?:heatwave|severe heatwave|high temperature)\b", full_content, re.IGNORECASE):
            categories_found.append("heatwave")
        if re.search(r"\b(?:gale|strong wind|gusty wind)\b", full_content, re.IGNORECASE):
            categories_found.append("gale_wind")
        if re.search(r"\b(?:dense fog|fog)\b", full_content, re.IGNORECASE):
            categories_found.append("dense_fog")

        if not categories_found:
            categories_found.append("general_meteorological")

        # Detect severity
        severity = "YELLOW"
        if re.search(r"\b(?:red alert|severe alert|take action|extremely heavy)\b", full_content, re.IGNORECASE):
            severity = "RED"
        elif re.search(r"\b(?:orange alert|be prepared|very heavy rain|moderate to severe)\b", full_content, re.IGNORECASE):
            severity = "ORANGE"
        elif re.search(r"\b(?:yellow alert|be updated|isolated heavy)\b", full_content, re.IGNORECASE):
            severity = "YELLOW"
        elif re.search(r"\b(?:no warning|green)\b", full_content, re.IGNORECASE):
            severity = "GREEN"

        # Detect locations / states mentioned
        indian_regions = [
            "Goa", "Konkan", "Karnataka", "Maharashtra", "Kerala", "Tamil Nadu",
            "Andhra Pradesh", "Telangana", "Odisha", "West Bengal", "Gujarat",
            "Rajasthan", "Delhi", "Punjab", "Haryana", "Uttar Pradesh", "Bihar",
            "Assam", "Meghalaya", "Arunachal Pradesh", "Nagaland", "Manipur",
            "Mizoram", "Tripura", "Sikkim", "Himachal Pradesh", "Uttarakhand",
            "Jammu & Kashmir", "Madhya Pradesh", "Chhattisgarh", "Jharkhand"
        ]
        locations_found = [reg for reg in indian_regions if re.search(rf"\b{re.escape(reg)}\b", full_content, re.IGNORECASE)]
        loc_display = ", ".join(locations_found[:3]) if locations_found else "National / Regional"

        # Extract Actionable Advisories
        advisories = []
        if "heavy_rainfall" in categories_found or severity in ["ORANGE", "RED"]:
            advisories.append("Keep field drainage channels clear to prevent localized waterlogging in standing crops.")
            advisories.append("Postpone chemical pesticide spraying and fertilizer application until clear weather.")
        if "thunderstorm" in categories_found:
            advisories.append("Do not take shelter under tall isolated trees or near water bodies during lightning activity.")
            advisories.append("Keep livestock indoors and disconnect electrical motor starters in open pump sheds.")
        if "cyclone" in categories_found or "gale_wind" in categories_found:
            advisories.append("Fishermen are strictly advised not to venture into deep sea or coastal waters.")
            advisories.append("Provide propping support for tall crops (banana, papaya, sugarcane) to avoid lodging.")
        if "heatwave" in categories_found:
            advisories.append("Provide light and frequent irrigation in early morning or late evening.")
            advisories.append("Avoid direct sun exposure between 11:00 AM and 4:00 PM; drink adequate fluids.")

        primary_cat = categories_found[0]
        raw_doc = {
            "source": "IMD",
            "source_url": source_url,
            "location": loc_display,
            "district": loc_display,
            "state": locations_found[0] if locations_found else "National",
            "type": "warning",
            "category": primary_cat,
            "severity": severity,
            "text": full_content[:500] if len(full_content) > 500 else full_content,
            "advisories": advisories,
            "confidence": 1.0,
            "is_official": True,
        }

        results.append(CrawlerNormalizer.normalize_warning(raw_doc, default_source_url=source_url))
        return results

    @classmethod
    def parse_json_bulletin(cls, data: Any, source_url: str = "") -> list[dict[str, Any]]:
        """
        Parse structured JSON feeds from IMD APIs or pre-seeded bulletin snapshots.
        """
        items = data if isinstance(data, list) else [data]
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "forecast":
                normalized.append(CrawlerNormalizer.normalize_forecast_bulletin(item, default_source_url=source_url))
            else:
                normalized.append(CrawlerNormalizer.normalize_warning(item, default_source_url=source_url))
        return normalized
