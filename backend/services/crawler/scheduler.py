"""
Periodic Crawler Scheduler for WeatherGPT (SIH26068).

Provides lightweight in-process background scheduling to periodically
refresh authoritative IMD bulletins and warnings.
Supports on-demand manual trigger via API and monitors execution health.
"""

import asyncio
import logging
import os
from typing import Any, Optional

from services.crawler.imd_crawler import IMDCrawler, crawler_instance

logger = logging.getLogger(__name__)

CRAWL_INTERVAL_SECONDS = int(os.getenv("IMD_CRAWL_INTERVAL_MINUTES", "60")) * 60
CRAWLER_ENABLED = os.getenv("IMD_CRAWLER_ENABLED", "true").strip().lower() in ["1", "true", "yes"]


class CrawlerScheduler:
    """Manages periodic background crawling of authoritative IMD sources."""

    def __init__(self, crawler: IMDCrawler = crawler_instance):
        self.crawler = crawler
        self.interval_seconds = max(300, CRAWL_INTERVAL_SECONDS)  # Minimum 5 mins
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def _loop(self):
        """Background loop executing crawl at regular intervals."""
        logger.info("CrawlerScheduler: Background loop started (Interval: %d seconds).", self.interval_seconds)
        while self.is_running:
            try:
                logger.info("CrawlerScheduler: Triggering scheduled IMD crawl...")
                await self.crawler.run_crawl()
            except Exception as exc:
                logger.warning("CrawlerScheduler: Crawl task error: %s", exc)
            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break
        logger.info("CrawlerScheduler: Background loop stopped.")

    def start(self):
        """Start the background crawler scheduler if enabled."""
        if not CRAWLER_ENABLED:
            logger.info("CrawlerScheduler: IMD_CRAWLER_ENABLED is false; scheduler disabled.")
            return

        if self.is_running:
            return

        self.is_running = True
        self._task = asyncio.create_task(self._loop())

    def stop(self):
        """Gracefully stop the background crawler task."""
        if not self.is_running:
            return
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def run_once(self) -> dict[str, Any]:
        """Manually trigger an immediate crawl execution."""
        return await self.crawler.run_crawl()

    def get_status(self) -> dict[str, Any]:
        """Return operational status and metrics of the crawler."""
        return {
            "enabled": CRAWLER_ENABLED,
            "running": self.is_running,
            "interval_minutes": self.interval_seconds // 60,
            "last_status": self.crawler.last_status,
            "last_crawled_at": self.crawler.last_crawled_at,
            "last_error": self.crawler.last_error,
            "total_documents": len(self.crawler.documents),
            "document_count": len(self.crawler.documents),
            "sources": [
                "IMD NWFC All India Weather Warning Bulletin",
                "RSMC New Delhi Tropical Weather Outlook",
                "IMD Severe Weather Nowcast Warnings",
                "IMD Agromet Advisory Service Bulletins",
            ],
        }


# Global scheduler instance
crawler_scheduler = CrawlerScheduler()
