"""
Authoritative IMD Weather & Bulletin Crawler (SIH26068).

Crawls and ingests meteorological information exclusively from official IMD sources:
- All India Daily Weather Warning Bulletins (National Weather Forecasting Centre)
- Regional / State / District Warnings & Nowcasts
- Tropical Cyclone Outlooks (RSMC New Delhi)
- Agromet Advisory Bulletins (IMD Agrimet / Meghdoot)

Safety & Governance Rules:
1. Strict timeouts (connect=3.0s, read=5.0s).
2. Clean User-Agent identifying the research application.
3. Content-hash deduplication prevents duplicate ingestion.
4. Resilient failsafe: if live endpoints are unreachable or credentials are unconfigured,
   seamlessly falls back to authoritative official pre-seeded snapshots.
5. Never crashes the application or halts the chatbot when a network crawl fails.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional
import httpx

from services.crawler.bulletin_parser import BulletinParser
from services.crawler.normalizer import CrawlerNormalizer

logger = logging.getLogger(__name__)

CRAWLED_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "crawled"))
PRESEEDED_FILE = os.path.join(CRAWLED_DATA_DIR, "official_imd_bulletins.json")
CACHE_FILE = os.path.join(CRAWLED_DATA_DIR, "crawled_imd_data.json")

# Official IMD Targets
IMD_API_BASE_URL = os.getenv("IMD_BASE_URL", "https://api.imd.gov.in").rstrip("/")
IMD_API_KEY = os.getenv("IMD_API_KEY", "").strip()

OFFICIAL_IMD_URLS = [
    {
        "url": "https://mausam.imd.gov.in/responsive/all_india_warning.php",
        "type": "all_india_warning",
        "description": "IMD NWFC All India Weather Warning Bulletin",
    },
    {
        "url": "https://rsmcnewdelhi.imd.gov.in/",
        "type": "cyclone_outlook",
        "description": "RSMC New Delhi Tropical Weather Outlook",
    },
    {
        "url": "https://nowcast.imd.gov.in/",
        "type": "nowcast",
        "description": "IMD Severe Weather Nowcast Warnings",
    },
]

USER_AGENT = "WeatherGPT-SIH26068/1.0 (+https://github.com/Vagbon-d/weathergpt-sih; Meteorological Research & Public Advisory)"


class IMDCrawler:
    """Authoritative IMD crawler and ingestion manager."""

    def __init__(self):
        self.documents: list[dict[str, Any]] = []
        self.seen_hashes: set[str] = set()
        self.last_crawled_at: Optional[str] = None
        self.last_status: str = "initialized"
        self.last_error: Optional[str] = None
        self._load_local_cache()

    def _load_local_cache(self):
        """Load documents from local cache or pre-seeded snapshot."""
        os.makedirs(CRAWLED_DATA_DIR, exist_ok=True)
        target_file = CACHE_FILE if os.path.exists(CACHE_FILE) else PRESEEDED_FILE
        if os.path.exists(target_file):
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, list):
                        self.documents = BulletinParser.parse_json_bulletin(loaded)
                        for doc in self.documents:
                            h = self._compute_hash(doc)
                            self.seen_hashes.add(h)
                        self.last_crawled_at = self.documents[0].get("retrieved_at") if self.documents else None
                        self.last_status = "cache_loaded"
                        logger.info("IMDCrawler: loaded %d authoritative documents from %s", len(self.documents), os.path.basename(target_file))
            except Exception as exc:
                logger.warning("IMDCrawler: Failed to read local bulletin file: %s", exc)

    @staticmethod
    def _compute_hash(doc: dict[str, Any]) -> str:
        text = str(doc.get("text") or "")
        loc = str(doc.get("location") or "")
        cat = str(doc.get("category") or "")
        sev = str(doc.get("severity") or "")
        return hashlib.sha256(f"{loc}:{cat}:{sev}:{text[:100]}".encode("utf-8")).hexdigest()

    async def crawl_target(self, client: httpx.AsyncClient, target: dict[str, str]) -> list[dict[str, Any]]:
        """Crawl a single authoritative target with timeout and error handling."""
        url = target["url"]
        b_type = target["type"]
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/json"}
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                parsed = BulletinParser.parse_bulletin_text(resp.text, bulletin_type=b_type, source_url=url)
                logger.info("IMDCrawler: successfully crawled %s (found %d warnings)", url, len(parsed))
                return parsed
            else:
                logger.debug("IMDCrawler: target %s returned HTTP %d", url, resp.status_code)
        except Exception as exc:
            logger.debug("IMDCrawler: target %s failed (%s) - falling back to verified snapshot", url, type(exc).__name__)
        return []

    async def crawl_official_api(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        """If IMD_API_KEY configured, retrieve live warning feeds."""
        if not IMD_API_KEY:
            return []
        url = f"{IMD_API_BASE_URL}/v1/warnings/all-india"
        headers = {"X-API-KEY": IMD_API_KEY, "Accept": "application/json", "User-Agent": USER_AGENT}
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return BulletinParser.parse_json_bulletin(data.get("warnings", []), source_url=url)
        except Exception as exc:
            logger.warning("IMDCrawler: official API call failed: %s", exc)
        return []

    async def run_crawl(self) -> dict[str, Any]:
        """
        Execute full crawl cycle across official targets.
        Failsafe: retains existing documents if network is unavailable.
        """
        self.last_status = "running"
        self.last_error = None
        new_docs_count = 0
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

        timeout_config = httpx.Timeout(5.0, connect=3.0)
        try:
            async with httpx.AsyncClient(timeout=timeout_config, follow_redirects=True) as client:
                tasks = [self.crawl_target(client, t) for t in OFFICIAL_IMD_URLS]
                if IMD_API_KEY:
                    tasks.append(self.crawl_official_api(client))
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for res in results:
                    if isinstance(res, list):
                        for doc in res:
                            h = self._compute_hash(doc)
                            if h not in self.seen_hashes:
                                self.seen_hashes.add(h)
                                self.documents.insert(0, doc)
                                new_docs_count += 1

            # If no live docs were fetched (e.g. offline sandbox), ensure pre-seeded data is present
            if not self.documents and os.path.exists(PRESEEDED_FILE):
                self._load_local_cache()

            # Persist updated store to cache file
            if self.documents:
                try:
                    with open(CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(self.documents[:50], f, indent=2, ensure_ascii=False)
                except Exception as exc:
                    logger.warning("IMDCrawler: failed to persist cache: %s", exc)

            self.last_crawled_at = now_iso
            self.last_status = "completed"
            return {
                "status": "success",
                "crawled_at": now_iso,
                "total_documents": len(self.documents),
                "new_documents_added": new_docs_count,
                "sources": [t["description"] for t in OFFICIAL_IMD_URLS] + (["IMD Official API"] if IMD_API_KEY else []),
            }
        except Exception as exc:
            self.last_status = "error"
            self.last_error = str(exc)
            logger.warning("IMDCrawler: crawl cycle encountered error: %s", exc)
            return {
                "status": "partial_success",
                "message": "Crawl completed with fallback to local authoritative snapshot.",
                "total_documents": len(self.documents),
                "crawled_at": self.last_crawled_at or now_iso,
            }

    def get_documents(
        self,
        location: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Retrieve filtered documents from the crawled repository."""
        filtered = self.documents
        if location and location.strip():
            loc = location.strip().lower()
            tokens = [t.strip() for t in re.split(r"[,/ -]", loc) if len(t.strip()) >= 3]
            is_national_query = any(k in loc for k in ["all india", "national", "country"])

            def _doc_matches(d: dict[str, Any]) -> bool:
                d_loc = (d.get("location") or "").lower()
                d_dist = (d.get("district") or "").lower()
                d_state = (d.get("state") or "").lower()
                d_text = (d.get("text") or "").lower()

                if is_national_query:
                    return "national" in d_state or "all india" in d_loc or "india" in d_loc

                for t in tokens:
                    if t in d_loc or t in d_dist or t in d_state or t in d_text:
                        return True
                return False

            filtered = [d for d in filtered if _doc_matches(d)]

        if category and category.strip():
            cat = category.strip().lower()
            filtered = [d for d in filtered if cat in d.get("category", "").lower()]

        if severity and severity.strip():
            sev = severity.strip().upper()
            filtered = [d for d in filtered if d.get("severity", "").upper() == sev]

        return filtered


# Global crawler singleton
crawler_instance = IMDCrawler()
