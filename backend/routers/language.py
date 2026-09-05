"""
Language & Voice Router for WeatherGPT.

Provides endpoints for:
- Text-to-Speech (TTS) via Bhashini pipeline or browser fallback instruction
- Speech-to-Text (ASR) via Bhashini
- Language identification and translation
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.language.bhashini_service import bhashini
from services.language import native_tts
from services import language_service

router = APIRouter(prefix="/language", tags=["language"])

LOCALE_MAP = {
    "hi": "hi-IN",
    "hi-latn": "hi-IN",
    "mr": "mr-IN",
    "gu": "gu-IN",
    "bn": "bn-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
    "pa": "pa-IN",
    "or": "or-IN",
    "kok": "kok-IN",
    "en": "en-IN",
}


class TTSRequest(BaseModel):
    text: str
    language: str = "en"
    gender: str = "female"


class DetectRequest(BaseModel):
    text: str


@router.post("/tts")
async def text_to_speech(req: TTSRequest):
    """
    Generate Text-to-Speech audio for an assistant response.
    Attempts Bhashini TTS pipeline first.
    If unconfigured or unavailable, attempts native operating system TTS (macOS say/Lekha/Rishi).
    If unavailable, returns fallback instructions for browser SpeechSynthesis.
    """
    raw_text = req.text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    clean_lang = req.language.lower().split("-")[0]
    if clean_lang == "hi" and "latn" in req.language.lower():
        clean_lang = "hi-latn"
    normalized_speech_text = language_service.prepareTTS(raw_text, clean_lang)

    # 1. Try Bhashini TTS if configured
    if bhashini.is_available():
        tts_res = await bhashini.generate_tts(
            text=normalized_speech_text,
            language=clean_lang,
            gender=req.gender,
        )
        if tts_res and "audioContent" in tts_res:
            return {
                "available": True,
                "provider": "bhashini",
                "voice": tts_res.get("serviceId", "Bhashini TTS"),
                "audio_base64": tts_res["audioContent"],
                "format": tts_res.get("audioFormat", "wav"),
                "source": "bhashini",
                "service_id": tts_res.get("serviceId"),
                "language": clean_lang,
                "normalized_text": normalized_speech_text,
            }

    # 2. Try Native Operating System Speech Synthesis (e.g. macOS Lekha for hi, Rishi for en)
    system_tts_res = native_tts.synthesize_native_tts(
        text=normalized_speech_text,
        language=clean_lang,
    )
    if system_tts_res and system_tts_res.get("audio_base64"):
        return {
            "available": True,
            "provider": "macos_system",
            "voice": system_tts_res.get("voice", "System Voice"),
            "audio_base64": system_tts_res["audio_base64"],
            "format": system_tts_res.get("format", "wav"),
            "source": "macos_system",
            "language": clean_lang,
            "normalized_text": normalized_speech_text,
        }

    # 3. Seamless fallback to browser Web Speech API
    target_locale = LOCALE_MAP.get(clean_lang, "en-IN")
    return {
        "available": False,
        "fallback": "browser",
        "provider": "browser",
        "language": clean_lang,
        "locale": target_locale,
        "voice_target": target_locale,
        "normalized_text": normalized_speech_text,
        "message": "Bhashini and System TTS unavailable for this language; falling back to browser SpeechSynthesis.",
    }


@router.post("/detect")
async def detect_language(req: DetectRequest):
    """
    Detect language of input text deterministically or via Bhashini.
    """
    lang = language_service.detect_language(req.text)
    return {
        "detected_language": lang,
        "is_indian_language": lang != "en",
    }


class ASRRequest(BaseModel):
    audio_base64: str
    language: str = "hi"


@router.post("/asr")
async def speech_to_text(req: ASRRequest):
    """
    Transcribe speech audio via Bhashini ASR pipeline.
    """
    if not req.audio_base64:
        raise HTTPException(status_code=400, detail="Audio content is required.")
    if not bhashini.is_available():
        return {
            "available": False,
            "provider": "browser",
            "text": "",
            "message": "Bhashini ASR unconfigured or offline; use browser SpeechRecognition.",
        }
    transcript = await bhashini.recognize_speech(req.audio_base64, req.language)
    return {
        "available": bool(transcript),
        "provider": "bhashini",
        "text": transcript or "",
    }
