"""
Crawler Management API Router for WeatherGPT (SIH26068).

Provides inspection of crawler status, document repository metrics,
and on-demand crawl triggers for demonstration and operations.
"""

from fastapi import APIRouter
from services.crawler.scheduler import crawler_scheduler

router = APIRouter(prefix="/crawl", tags=["crawler"])


@router.get("/status")
async def get_crawler_status():
    """Retrieve operational status, last run time, and document metrics."""
    return crawler_scheduler.get_status()


@router.post("/run")
async def trigger_crawler_run():
    """Trigger an immediate asynchronous crawl cycle across official IMD sources."""
    result = await crawler_scheduler.run_once()
    return result
