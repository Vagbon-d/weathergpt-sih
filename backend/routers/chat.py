"""
WeatherGPT conversational API.

Safety Architecture:
User Question
      ↓
Query Classification (Deterministic keyword routing)
      ↓
Location Enforcement (Requires canonical location or GPS coordinates)
      ↓
Live Weather / Alert / Advisory Retrieval (IMD + Open-Meteo & local KB)
      ↓
Python Threshold, Temporal & Mathematical Evaluation
      ↓
Grounded Context Injection
      ↓
Ollama (qwen3:4b) OR Deterministic Python Fallback
      ↓
Natural Language Answer (Strictly sanitized, no <think> tags, no raw JSON)

The LLM is NEVER the source of weather facts. Every numeric weather value
displayed in the UI originates from authoritative weather providers.

NOTE (refactor): The full grounded pipeline now lives in
services/grounded_advisory.py → generate_grounded_advisory().
This router delegates to that shared function so the IVR/SMS channel
(routers/webhook.py) can reuse the identical pipeline without duplication.
"""

import logging
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.grounded_advisory import generate_grounded_advisory

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    location: str | dict[str, Any] | None = None
    language: str = "en"
    latitude: float | None = None
    longitude: float | None = None
    history: list[dict[str, Any]] | None = None
    crop: str | None = None
    conversation_id: str | None = None


@router.post("/chat")
async def chat(req: ChatRequest):
    """
    End-to-end grounded conversational endpoint.
    Delegates to services.grounded_advisory.generate_grounded_advisory()
    with channel="app" so the full JSON response is returned unchanged.
    """
    query = req.query.strip()
    if not query:
        raise HTTPException(
            status_code=400,
            detail="Please enter a question.",
        )

    result = await generate_grounded_advisory(
        query=query,
        location=req.location,
        language=req.language,
        latitude=req.latitude,
        longitude=req.longitude,
        crop=req.crop,
        history=req.history,
        channel="app",
    )

    # Surface stale-feed errors as HTTP 503 so the frontend handles them correctly
    if result.get("stale_feed") and result.get("intent") == "error":
        raise HTTPException(
            status_code=503,
            detail=result.get("answer", "Weather data service temporarily unavailable."),
        )

    return result
