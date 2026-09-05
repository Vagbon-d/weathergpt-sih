"""
Dedicated agricultural advisory endpoint.

Flow:
location/coords -> live weather -> advisory KB -> Python rule evaluation -> grounded context -> Ollama / Fallback -> answer

Advisories are grounded strictly in weather data and the local advisory KB.
Threshold evaluation is executed in Python, not by the LLM.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services import weather_service, rag_service, llm_service, advisory_service

router = APIRouter()


class AdvisoryRequest(BaseModel):
    location: str | None = None
    crop: str = "rice"
    language: str = "en"
    query: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@router.post("/advisory")
async def advisory(req: AdvisoryRequest):
    """
    End-to-end agricultural advisory endpoint.
    Retrieves weather, evaluates knowledge-base rules in Python,
    and returns a grounded natural language response with full basis.
    """
    if not req.location and (req.latitude is None or req.longitude is None):
        raise HTTPException(
            status_code=400,
            detail="Location or coordinates required. Please specify a location.",
        )

    try:
        if req.latitude is not None and req.longitude is not None:
            weather = await weather_service.get_current_and_forecast(
                latitude=req.latitude, longitude=req.longitude
            )
        else:
            weather = await weather_service.get_current_and_forecast(location=req.location)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Weather data service temporarily unavailable: {exc}",
        )

    # Deterministic ag operations evaluations
    spray_eval = advisory_service.evaluate_spray_safety(weather)
    irrigation_eval = advisory_service.evaluate_irrigation_safety(weather)
    harvest_eval = advisory_service.evaluate_harvest_safety(weather)
    sowing_eval = advisory_service.evaluate_sowing_safety(weather, crop=req.crop)

    # Retrieve matching advisory rules
    search_query = req.query or f"farming advice for {req.crop}"
    raw_advisories = rag_service.retrieve_advisory(query=search_query, crop=req.crop)

    # Evaluate triggers deterministically in Python
    evaluated_advisories = rag_service.evaluate_triggers(raw_advisories, weather)

    # Attempt LLM grounding
    answer = await llm_service.generate_grounded_answer(
        query=search_query,
        domain="agriculture",
        weather_data=weather,
        advisory_data=evaluated_advisories,
        language=req.language,
    )

    # Fallback to deterministic Python generation if Ollama is unavailable
    if not answer:
        answer = llm_service.generate_python_fallback(
            domain="agriculture",
            query=search_query,
            weather_data=weather,
            advisory_data=evaluated_advisories,
            language=req.language,
        )

    today = weather.get("forecast", [{}])[0] if weather.get("forecast") else {}

    return {
        "answer": answer,
        "advisories": evaluated_advisories,
        "operations": {
            "spray": spray_eval,
            "irrigation": irrigation_eval,
            "harvest": harvest_eval,
            "sowing": sowing_eval,
        },
        "basis": {
            "weather": {
                "location": weather.get("location"),
                "current": weather.get("current"),
                "forecast": weather.get("forecast"),
                "source": weather.get("source"),
            },
            "advisories": evaluated_advisories,
        },
        # Backwards-compatible fields
        "weather_used": weather.get("current"),
        "rain_probability_today": today.get("rain_probability", 0),
        "advisory_matches": evaluated_advisories,
        "source": weather.get("source"),
    }
