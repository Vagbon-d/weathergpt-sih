from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import weather, chat, alerts, advisory, location, language

app = FastAPI(title="WeatherGPT Prototype API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # prototype only -- tighten before any real deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(weather.router)
app.include_router(chat.router)
app.include_router(alerts.router)
app.include_router(advisory.router)
app.include_router(location.router)
app.include_router(language.router)


@app.post("/tts")
async def tts_root(req: language.TTSRequest):
    """Root /tts endpoint forwarding to language.text_to_speech."""
    return await language.text_to_speech(req)


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "WeatherGPT prototype backend running",
        "endpoints": ["/health", "/weather", "/chat", "/alerts", "/advisory", "/location/search", "/location/reverse", "/language/tts", "/docs"],
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "WeatherGPT API",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
