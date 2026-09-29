from contextlib import asynccontextmanager
from pathlib import Path
import os

from dotenv import load_dotenv

# Ensure root .env is loaded before router initialization
_root_env = Path(__file__).resolve().parent.parent / ".env"
if _root_env.exists():
    load_dotenv(_root_env, override=True)
else:
    load_dotenv(override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers import weather, chat, alerts, advisory, location, language, crawler
from routers import webhook
from routers import ws_call_status
from services.crawler import crawler_scheduler
from db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialise caller-profile SQLite DB, then start IMD crawler
    await init_db()
    crawler_scheduler.start()
    yield
    # Shutdown: stop crawler scheduler
    crawler_scheduler.stop()


app = FastAPI(title="WeatherGPT Prototype API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # prototype only -- tighten before any real deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve synthesised IVR audio clips for Twilio <Play> URLs
_static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(_static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# Existing routers
app.include_router(weather.router)
app.include_router(chat.router)
app.include_router(alerts.router)
app.include_router(advisory.router)
app.include_router(location.router)
app.include_router(language.router)
app.include_router(crawler.router)

# IVR / SMS webhook router
app.include_router(webhook.router)

# Live call-status WebSocket feed (demo/observability layer)
app.include_router(ws_call_status.router)


@app.post("/tts")
async def tts_root(req: language.TTSRequest):
    """Root /tts endpoint forwarding to language.text_to_speech."""
    return await language.text_to_speech(req)


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "WeatherGPT prototype backend running",
        "endpoints": [
            "/health",
            "/weather",
            "/chat",
            "/alerts",
            "/advisory",
            "/location/search",
            "/location/reverse",
            "/language/tts",
            "/language/asr",
            "/language/detect",
            "/webhook/sms",
            "/webhook/voice",
            "/webhook/voice/process",
            "/webhook/sms/simulate",
            "/webhook/sms/register-caller",
            "/alerts/proactive-push",
            "/crawl/status",
            "/crawl/run",
            "/docs",
        ],
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "WeatherGPT API",
        "version": "0.2.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
