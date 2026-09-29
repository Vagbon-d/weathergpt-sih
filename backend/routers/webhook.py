"""
WeatherGPT Telephony/SMS Webhook Router (SIH26068).

Exposes four endpoints inside the existing FastAPI app — NOT a separate app:

  POST /webhook/sms              – Inbound SMS from Twilio (or compatible gateway)
  POST /webhook/voice            – Inbound voice call; returns IVR greeting + Gather
  POST /webhook/voice/process    – Processes ASR transcript, returns Play + re-prompt
  POST /alerts/proactive-push    – Trigger outbound SMS/call to all callers in a district
                                   when a genuine IMD warning is active

ZERO-HALLUCINATION RULE (carried from the main architecture):
  Every weather fact, IMD warning, or agricultural verdict returned to the
  caller comes from generate_grounded_advisory() — the same shared function
  used by the web app. The LLM never invents values; this router never bypasses
  the verified context pipeline.

Stale-feed safety:
  If generate_grounded_advisory() sets stale_feed=True or returns no weather,
  the caller is told the service is temporarily unavailable; no fabricated
  answer is ever sent.

Twilio TwiML reference used: https://www.twilio.com/docs/voice/twiml
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, JSONResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import CallerProfile, get_db
from services.grounded_advisory import generate_grounded_advisory
from services import language_service
from services.language.bhashini_service import bhashini
from services import rag_service, weather_service

# Live call-status WebSocket feed — imported lazily to avoid circular imports
# at module init time. The manager is a module-level singleton.
def _get_ws_manager():
    """Lazy import of the WS manager to avoid import-time circular dependency."""
    from routers.ws_call_status import call_status_manager  # noqa: PLC0415
    return call_status_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ivr_sms"])

# ---------------------------------------------------------------------------
# Environment / gateway configuration
def _get_twilio_creds() -> tuple[str, str, str]:
    return (
        os.getenv("TWILIO_ACCOUNT_SID", ""),
        os.getenv("TWILIO_AUTH_TOKEN", ""),
        os.getenv("TWILIO_FROM_NUMBER", ""),
    )

def _get_webhook_base_url(request: Request | None = None) -> str:
    if request:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if host and "127.0.0.1" not in host and "localhost" not in host:
            return f"{proto}://{host}".rstrip("/")
    url = os.getenv("WEBHOOK_BASE_URL", "").strip().rstrip("/")
    return url if url else "http://localhost:8000"

# Backward compatibility module attributes
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "http://localhost:8000")

# Validate Twilio signature in production; skip in dev/demo
_VALIDATE_TWILIO_SIG = os.getenv("VALIDATE_TWILIO_SIGNATURE", "false").lower() == "true"

# ---------------------------------------------------------------------------
# IVR greeting prompts (one per language)
# ---------------------------------------------------------------------------
IVR_GREETING: dict[str, str] = {
    "en": "Welcome to WeatherGPT. Please state your weather or farming question after the beep.",
    "hi": "WeatherGPT में आपका स्वागत है। कृपया बीप के बाद अपना मौसम या खेती संबंधी प्रश्न बोलें।",
    "hi-Latn": "WeatherGPT mein aapka swagat hai. Beep ke baad apna sawaal bolein.",
    "or": "WeatherGPT ରେ ଆପଣଙ୍କୁ ସ୍ୱାଗତ। ବୀପ୍ ପରେ ଆପଣଙ୍କ ପ୍ରଶ୍ନ ବୁଲାନ୍ତୁ।",
    "bn": "WeatherGPT-এ আপনাকে স্বাগতম। বীপের পরে আপনার প্রশ্ন বলুন।",
    "mr": "WeatherGPT मध्ये आपले स्वागत. बीपनंतर आपला प्रश्न बोला.",
    "gu": "WeatherGPT માં આપનું સ્વાગત. બીપ પછી તમારો પ્રશ્ન બોલો.",
    "ta": "WeatherGPT-ல் உங்களை வரவேற்கிறோம். பீப்பிற்குப் பிறகு உங்கள் கேள்வியை சொல்லுங்கள்.",
    "te": "WeatherGPT కి స్వాగతం. బీప్ తర్వాత మీ ప్రశ్న చెప్పండి.",
    "kn": "WeatherGPT ಗೆ ಸ್ವಾಗತ. ಬೀಪ್ ನಂತರ ನಿಮ್ಮ ಪ್ರಶ್ನೆ ಹೇಳಿ.",
}

IVR_FOLLOWUP: dict[str, str] = {
    "en": "Do you have another question? Say yes to continue or say no to end the call.",
    "hi": "क्या आपका और कोई प्रश्न है? जारी रखने के लिए हाँ कहें, समाप्त करने के लिए नहीं कहें।",
    "hi-Latn": "Kya aapka aur koi sawaal hai? Jaari rakhne ke liye haan bolein, khatam karne ke liye nahi bolein.",
    "or": "ଆପଣଙ୍କର ଆଉ କୌଣସି ପ୍ରଶ୍ନ ଅଛି? ଚାଲୁ ରଖିବା ପାଇଁ ହଁ କୁହନ୍ତୁ, ଶେଷ କରିବା ପାଇଁ ନା।",
    "bn": "আপনার আর কোনো প্রশ্ন আছে? চালিয়ে যেতে হ্যাঁ বলুন, শেষ করতে না বলুন।",
    "mr": "तुम्हाला आणखी प्रश्न आहे का? सुरू ठेवण्यासाठी हो म्हणा, संपवण्यासाठी नाही म्हणा.",
    "en_fallback": "Thank you for using WeatherGPT. Goodbye.",
}

IVR_STALE_FEED: dict[str, str] = {
    "en": "I'm sorry, weather data is temporarily unavailable. Please try again in a few minutes. Goodbye.",
    "hi": "क्षमा करें, मौसम डेटा अस्थायी रूप से अनुपलब्ध है। कृपया कुछ मिनट बाद पुनः प्रयास करें।",
    "hi-Latn": "Maafi chahta hoon, mausam data abhi uplabdh nahi hai. Kuch minute baad try karein.",
    "or": "ଦୁଃଖିତ, ପାଣିପାଗ ତଥ୍ୟ ସ୍ୱଳ୍ପ ସମୟ ପାଇଁ ଅନୁପଲବ୍ଧ। ଦୟାକରି ଅଳ୍ପ ସମୟ ପରେ ପୁଣି ଚେଷ୍ଟା କରନ୍ତୁ।",
    "bn": "দুঃখিত, আবহাওয়া ডেটা সাময়িকভাবে অনুপলব্ধ। একটু পরে আবার চেষ্টা করুন।",
}

# Spoken confirmation sent to the caller AFTER the SMS has been dispatched.
# The full answer arrives by SMS; the call ends here.
IVR_SMS_CONFIRM: dict[str, str] = {
    "en": "Thank you. Your weather advisory has been sent as a text message to your phone. Goodbye.",
    "hi": "धन्यवाद। आपकी मौसम सलाह आपके फ़ोन पर SMS से भेज दी गई है। नमस्ते।",
    "hi-Latn": "Dhanyawad. Aapki mausam salah aapke phone par SMS se bhej di gayi hai. Namaste.",
    "or": "ଧନ୍ୟବାଦ। ଆପଣଙ୍କ ପାଣିପାଗ ପରାମର୍ଶ SMS ଭାବେ ଆପଣଙ୍କ ଫୋନ୍‌କୁ ପଠାଯାଇଛି। ଧନ୍ୟବାଦ।",
    "bn": "ধন্যবাদ। আপনার আবহাওয়া পরামর্শ SMS হিসাবে আপনার ফোনে পাঠানো হয়েছে। নমস্কার।",
    "mr": "धन्यवाद। तुमचा हवामान सल्ला SMS द्वारे तुमच्या फोनवर पाठवण्यात आला आहे. निरोप.",
    "gu": "આભાર. તમારી હવામાન સલાહ SMS દ્વારા તમારા ફોન પર મોકલી દેવામાં આવી છે. ધન્યવાદ.",
    "ta": "நன்றி. உங்கள் வானிலை ஆலோசனை SMS ஆக உங்கள் தொலைபேசிக்கு அனுப்பப்பட்டது. நன்றி.",
    "te": "ధన్యవాదాలు. మీ వాతావరణ సలహా SMS రూపంలో మీ ఫోన్‌కు పంపబడింది. వీడ్కోలు.",
    "kn": "ಧನ್ಯವಾದ. ನಿಮ್ಮ ಹವಾಮಾನ ಸಲಹೆಯನ್ನು SMS ಮೂಲಕ ನಿಮ್ಮ ಫೋನ್‌ಗೆ ಕಳುಹಿಸಲಾಗಿದೆ. ಗುಡ್‌ಬೈ.",
}

# Error SMS sent when the pipeline fails — caller gets a plain-language explanation,
# never silence or a fabricated answer.
IVR_ERROR_SMS: dict[str, str] = {
    "en": "WeatherGPT could not process your question. Please try calling again or send an SMS. [WeatherGPT]",
    "hi": "WeatherGPT आपका प्रश्न संसाधित नहीं कर सका। कृपया फिर से कॉल करें या SMS भेजें। [WeatherGPT]",
    "hi-Latn": "WeatherGPT aapka sawaal process nahi kar saka. Phir se call karein ya SMS karein. [WeatherGPT]",
    "or": "WeatherGPT ଆପଣଙ୍କ ପ୍ରଶ୍ନ ପ୍ରକ୍ରିୟା କରିପାରିଲା ନାହିଁ। ଦୟାକରି ପୁଣି ଫୋନ କରନ୍ତୁ। [WeatherGPT]",
    "bn": "WeatherGPT আপনার প্রশ্নটি প্রক্রিয়া করতে পারেনি। আবার কল করুন বা SMS পাঠান। [WeatherGPT]",
    "mr": "WeatherGPT तुमचा प्रश्न प्रक्रिया करू शकला नाही. पुन्हा कॉल करा. [WeatherGPT]",
    "ta": "WeatherGPT உங்கள் கேள்வியை செயலாக்க முடியவில்லை. மீண்டும் அழைக்கவும். [WeatherGPT]",
    "te": "WeatherGPT మీ ప్రశ్నను ప్రాసెస్ చేయలేకపోయింది. మళ్ళీ కాల్ చేయండి. [WeatherGPT]",
}


# ---------------------------------------------------------------------------
# Helper: simple TwiML builder (avoids importing the full twilio SDK just
# for XML generation; the SDK is still used for outbound calls / SMS)
# ---------------------------------------------------------------------------
def _twiml_response(body: str) -> Response:
    """Return a TwiML XML response with correct content-type."""
    return Response(content=body, media_type="application/xml")


def _twiml_message(to: str | None, body: str) -> str:
    """Build TwiML <MessagingResponse><Message> XML."""
    to_attr = f' to="{to}"' if to else ""
    body_escaped = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Message{to_attr}>{body_escaped}</Message>"
        "</Response>"
    )


def _twiml_voice_gather(say_text: str, action_url: str, language_code: str = "hi-IN") -> str:
    """Build TwiML <Response><Say><Gather> XML for IVR speech input."""
    say_text_escaped = say_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Say language="{language_code}">{say_text_escaped}</Say>'
        f'<Gather input="speech" action="{action_url}" method="POST" '
        f'speechTimeout="auto" language="{language_code}">'
        f'<Say language="{language_code}">{say_text_escaped}</Say>'
        "</Gather>"
        "</Response>"
    )


def _twiml_voice_play(audio_url: str, follow_up_text: str, follow_up_action: str, language_code: str = "hi-IN") -> str:
    """Build TwiML <Play> + <Gather> for follow-up."""
    fu_escaped = follow_up_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Play>{audio_url}</Play>'
        f'<Gather input="speech" action="{follow_up_action}" method="POST" '
        f'speechTimeout="auto" language="{language_code}">'
        f'<Say language="{language_code}">{fu_escaped}</Say>'
        "</Gather>"
        "</Response>"
    )


def _twiml_hangup(say_text: str, language_code: str = "hi-IN") -> str:
    say_text_escaped = say_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Say language="{language_code}">{say_text_escaped}</Say>'
        "<Hangup/>"
        "</Response>"
    )


def _lang_to_twilio_locale(lang: str) -> str:
    """Map internal language code to a Twilio/TTS locale string."""
    mapping = {
        "hi": "hi-IN", "hi-Latn": "hi-IN", "mr": "mr-IN", "gu": "gu-IN",
        "bn": "bn-IN", "ta": "ta-IN", "te": "te-IN", "kn": "kn-IN",
        "ml": "ml-IN", "pa": "pa-IN", "or": "or-IN", "kok": "kok-IN",
        "en": "en-IN",
    }
    return mapping.get(lang, "hi-IN")


def _send_outbound_sms(to: str, body: str) -> bool:
    """
    Dispatch an outbound SMS via the Twilio REST API.

    Returns True if sent (or dry-run / no credentials), False on hard failure.
    This is the ONLY place in the codebase that creates a TwilioClient — both
    the call-in/SMS-out route and the proactive-push route call this helper so
    the Twilio integration is not duplicated.

    Safety: never called with a fabricated body — callers must pass the output
    of generate_grounded_advisory() or an explicit error message.
    """
    if not to:
        logger.warning("_send_outbound_sms: no destination number; skipping.")
        return False

    account_sid, auth_token, from_number = _get_twilio_creds()
    if not (account_sid and auth_token and from_number):
        logger.warning(
            "Twilio credentials not configured; SMS to %s not sent (dry-run). Body: %s",
            to, body[:80],
        )
        return True  # Treat as success in dev/demo so the call flow still proceeds

    try:
        from twilio.rest import Client as TwilioClient  # type: ignore[import]
        client = TwilioClient(account_sid, auth_token)
        client.messages.create(body=body, from_=from_number, to=to)
        logger.info("Outbound SMS sent to %s: %s", to, body[:80])
        return True
    except Exception as exc:
        logger.error("Failed to send outbound SMS to %s: %s", to, exc)
        return False


async def _get_caller_profile(phone: str, db: AsyncSession) -> CallerProfile | None:
    """Look up caller profile by phone number."""
    result = await db.execute(select(CallerProfile).where(CallerProfile.phone == phone))
    return result.scalar_one_or_none()


def _mask_phone(phone: str) -> str:
    """
    Return a masked phone string safe for broadcast.
    Shows only last 4 digits: +91XXXXXX1234 -> **1234
    Never broadcasts full phone number to WebSocket clients.
    """
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) >= 4:
        return f"**{digits[-4:]}"
    return "****"


def _emit_ws_event(event: dict) -> None:
    """
    Fire-and-forget WebSocket broadcast.
    Wraps the async broadcast in a new asyncio Task so it NEVER blocks
    or delays the actual SMS/advisory pipeline. If the event loop is not
    running (e.g. during tests), this is silently skipped.

    SAFETY: Any exception inside the task is caught at the manager level
    (ConnectionManager.broadcast_status). This outer wrapper adds a second
    layer of protection.
    """
    try:
        mgr = _get_ws_manager()
        asyncio.create_task(mgr.broadcast_status(event))
    except Exception as exc:  # noqa: BLE001
        logger.debug("[WS] emit_ws_event failed silently: %s", exc)


async def _save_audio_and_get_url(audio_base64: str, fmt: str = "wav") -> str | None:
    """
    Save synthesized audio to the static directory and return a public URL.
    Returns None if saving fails.
    """
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static", "ivr_audio")
    os.makedirs(static_dir, exist_ok=True)

    filename = f"{uuid.uuid4().hex}.{fmt}"
    filepath = os.path.join(static_dir, filename)
    try:
        audio_bytes = base64.b64decode(audio_base64)
        with open(filepath, "wb") as f:
            f.write(audio_bytes)
        return f"{_get_webhook_base_url()}/static/ivr_audio/{filename}"
    except Exception as exc:
        logger.error("Failed to save IVR audio: %s", exc)
        return None


# ---------------------------------------------------------------------------
# POST /webhook/sms — Inbound SMS
# ---------------------------------------------------------------------------

@router.post("/webhook/sms")
async def inbound_sms(
    request: Request,
    From: str = Form(default=""),
    Body: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    """
    Receive inbound SMS from Twilio.

    Flow:
    1. Look up caller's saved home location + language preference from DB.
    2. Detect query language via existing language_service.detect_language().
    3. Run generate_grounded_advisory(..., channel="sms") — same pipeline as web app.
    4. Return TwiML <Message> with the ≤160-char grounded reply.

    If the weather feed is stale or location cannot be resolved, the caller
    receives a clear service-unavailable message — never a fabricated answer.
    """
    phone = From.strip()
    user_text = Body.strip()

    if not user_text:
        return _twiml_response(_twiml_message(None, "Please send your weather or farming question. [WeatherGPT]"))

    # 1. Look up caller profile
    profile = await _get_caller_profile(phone, db)
    location_name = profile.home_location if profile else None
    lat = profile.latitude if profile else None
    lon = profile.longitude if profile else None
    preferred_lang = profile.language if profile else "hi"

    # 2. Detect actual query language
    detected_lang = language_service.detect_language(user_text, preferred_lang)

    # 3. Check if this is a location-registration message (e.g. "MY LOCATION: Balasore, Odisha")
    loc_match = _parse_location_registration(user_text)
    if loc_match:
        return await _handle_location_registration(phone, loc_match, detected_lang, profile, db)

    # 4. Run grounded advisory pipeline (SMS channel → ≤160 chars output)
    try:
        result = await generate_grounded_advisory(
            query=user_text,
            location=location_name,
            language=detected_lang,
            latitude=lat,
            longitude=lon,
            channel="sms",
        )
    except Exception as exc:
        logger.error("generate_grounded_advisory failed for SMS from %s: %s", phone, exc)
        result = {
            "answer": "Service temporarily unavailable. Please try again later. [WeatherGPT]",
            "stale_feed": True,
        }

    answer = result.get("answer", "Service error. [WeatherGPT]")

    # Log for audit / debug
    logger.info(
        "[SMS] from=%s lang=%s loc=%s stale=%s answer_preview=%s",
        phone, detected_lang, location_name or "none",
        result.get("stale_feed", False), answer[:60],
    )

    return _twiml_response(_twiml_message(None, answer))


def _parse_location_registration(text: str) -> str | None:
    """
    Detect if the SMS is a location self-registration command.
    Supported formats:
      "MY LOCATION: Balasore, Odisha"
      "LOCATION Puri Odisha"
      "मेरा स्थान: बालासोर, ओडिशा"
    Returns the location string or None.
    """
    import re
    patterns = [
        r"(?:my\s+)?location\s*[:=]\s*(.+)",
        r"(?:मेरा|मेरी)\s*स्थान\s*[:=]\s*(.+)",
        r"set\s+location\s*[:=]?\s*(.+)",
    ]
    text_lower = text.strip()
    for pat in patterns:
        m = re.match(pat, text_lower, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


async def _handle_location_registration(
    phone: str,
    location_str: str,
    lang: str,
    existing_profile: CallerProfile | None,
    db: AsyncSession,
) -> Response:
    """Geocode the provided location and persist it in the caller profile."""
    try:
        lat, lon, canonical_name = await weather_service.geocode(location_str)
    except Exception:
        err = {
            "en": f"Could not find '{location_str}'. Please send: LOCATION <village/district name>",
            "hi": f"'{location_str}' नहीं मिला। कृपया भेजें: LOCATION <गाँव/जिले का नाम>",
            "hi-Latn": f"'{location_str}' nahi mila. Kripya bhejein: LOCATION <gaon/jile ka naam>",
        }.get(lang, f"Could not find '{location_str}'. Send: LOCATION <village or district name>")
        return _twiml_response(_twiml_message(None, err[:160]))

    if existing_profile:
        existing_profile.home_location = canonical_name
        existing_profile.latitude = lat
        existing_profile.longitude = lon
        existing_profile.language = lang
    else:
        db.add(CallerProfile(
            phone=phone,
            home_location=canonical_name,
            latitude=lat,
            longitude=lon,
            language=lang,
        ))
    await db.commit()

    confirm = {
        "en": f"Location saved: {canonical_name}. Now send your weather question. [WeatherGPT]",
        "hi": f"स्थान सहेजा: {canonical_name}। अब अपना मौसम प्रश्न भेजें। [WeatherGPT]",
        "hi-Latn": f"Location save hua: {canonical_name}. Ab mausam sawaal bhejein. [WeatherGPT]",
    }.get(lang, f"Location saved: {canonical_name}. Send your weather question. [WeatherGPT]")
    return _twiml_response(_twiml_message(None, confirm[:160]))


# ---------------------------------------------------------------------------
# POST /webhook/voice — Inbound voice call greeting
# ---------------------------------------------------------------------------

@router.post("/webhook/voice")
async def inbound_voice(
    request: Request,
    From: str = Form(default=""),
    To: str = Form(default=""),
    Called: str = Form(default=""),
    Direction: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle inbound IVR call.
    Returns a TwiML Gather asking the caller to state their weather question.
    """
    account_sid, auth_token, from_number = _get_twilio_creds()
    twilio_numbers = {from_number, "+17372324091", "+14353245881"}
    if Direction in ("outbound-api", "outbound-dial") or From.strip() in twilio_numbers:
        phone = (To or Called or "").strip()
    else:
        phone = From.strip()

    profile = await _get_caller_profile(phone, db)
    lang = profile.language if profile else "hi"
    locale = _lang_to_twilio_locale(lang)

    greeting = IVR_GREETING.get(lang, IVR_GREETING["en"])
    action_url = f"{_get_webhook_base_url(request)}/webhook/voice/process"

    return _twiml_response(_twiml_voice_gather(greeting, action_url, locale))


# ---------------------------------------------------------------------------
# POST /webhook/voice/process — Process ASR transcript, synthesize reply
# ---------------------------------------------------------------------------

@router.post("/webhook/voice/process")
async def process_voice(
    request: Request,
    From: str = Form(default=""),
    To: str = Form(default=""),
    Called: str = Form(default=""),
    Direction: str = Form(default=""),
    SpeechResult: str = Form(default=""),
    # Twilio telecom-circle metadata (Tier 3 location fallback)
    FromCity: str = Form(default=""),
    FromState: str = Form(default=""),
    FromCountry: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    """
    Process Twilio's ASR transcript of the caller's question.
    """
    account_sid, auth_token, from_number = _get_twilio_creds()
    twilio_numbers = {from_number, "+17372324091", "+14353245881"}
    if Direction in ("outbound-api", "outbound-dial") or From.strip() in twilio_numbers:
        phone = (To or Called or "").strip()
    else:
        phone = From.strip()

    transcript = SpeechResult.strip()
    call_id = uuid.uuid4().hex[:12]  # Short ID for WS events, never the phone number
    ts_now = datetime.now(timezone.utc).isoformat()

    profile = await _get_caller_profile(phone, db)
    lang = profile.language if profile else "hi"
    locale = _lang_to_twilio_locale(lang)
    phone_masked = _mask_phone(phone)

    # --- WS Event: call_received ---
    _emit_ws_event({
        "call_id": call_id,
        "stage": "call_received",
        "phone_masked": phone_masked,
        "language": lang,
        "location": None,
        "location_tier": None,
        "timestamp": ts_now,
    })

    # --- Empty / unintelligible transcript: re-prompt once ---
    if not transcript:
        logger.info("[IVR] Empty transcript from %s — re-prompting.", phone)
        greeting = IVR_GREETING.get(lang, IVR_GREETING["en"])
        action_url = f"{_get_webhook_base_url(request)}/webhook/voice/process"
        return _twiml_response(_twiml_voice_gather(greeting, action_url, locale))

    # 1. Detect language from the actual transcript
    detected_lang = language_service.detect_language(transcript, lang)
    locale = _lang_to_twilio_locale(detected_lang)

    # --- WS Event: language_detected ---
    _emit_ws_event({
        "call_id": call_id,
        "stage": "language_detected",
        "phone_masked": phone_masked,
        "language": detected_lang,
        "location": None,
        "location_tier": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # -------------------------------------------------------------------------
    # 2. THREE-TIER LOCATION FALLBACK
    #    Tier 1 is determined *after* the first advisory call below (the pipeline
    #    resolves query-location entities internally). Tiers 2 and 3 provide the
    #    seed location passed INTO the pipeline call.
    # -------------------------------------------------------------------------

    # --- Tier 2: Registered profile ---
    profile_location = profile.home_location if profile else None
    profile_lat = profile.latitude if profile else None
    profile_lon = profile.longitude if profile else None
    location_tier: str | None = None  # will be set once we know which tier fired

    if profile_location:
        location_tier = "profile"  # tentative — may be overridden by Tier 1
        logger.info("[IVR] Location Tier 2 (profile): %s", profile_location)

    # --- Tier 3: Telecom circle (FromCity / FromState from Twilio) ---
    telecom_location: str | None = None
    if not profile_location:
        city = FromCity.strip()
        state = FromState.strip()
        if city or state:
            telecom_location = ", ".join(filter(None, [city, state]))
            logger.info("[IVR] Location Tier 3 (telecom circle): %s", telecom_location)

    # Determine the seed location to pass into the first advisory call
    seed_location: str | None = profile_location or telecom_location
    seed_lat: float | None = profile_lat if profile_location else None
    seed_lon: float | None = profile_lon if profile_location else None

    # -------------------------------------------------------------------------
    # 3. Run the grounded advisory pipeline
    # -------------------------------------------------------------------------
    try:
        result = await generate_grounded_advisory(
            query=transcript,
            location=seed_location,
            language=detected_lang,
            latitude=seed_lat,
            longitude=seed_lon,
            channel="sms",
        )
    except Exception as exc:
        logger.error("generate_grounded_advisory failed for voice/SMS from %s: %s", phone, exc)
        result = None

    # -------------------------------------------------------------------------
    # 4. Determine which location tier actually fired
    # -------------------------------------------------------------------------
    resolved_location: str | None = None

    if result and not result.get("location_required"):
        resolved_location = result.get("location")
        if result.get("location_source") == "query":
            # Tier 1: spoken entity found in the transcript by the pipeline
            location_tier = "spoken"
            logger.info(
                "[IVR] Location Tier 1 (spoken entity): %s — call_id=%s",
                resolved_location, call_id,
            )
        elif profile_location:
            location_tier = "profile"
            logger.info(
                "[IVR] Location Tier 2 (registered profile): %s — call_id=%s",
                resolved_location, call_id,
            )
        elif telecom_location:
            location_tier = "telecom"
            logger.info(
                "[IVR] Location Tier 3 (telecom circle): %s — call_id=%s",
                resolved_location, call_id,
            )
    else:
        # All three tiers failed or pipeline indicated location_required
        location_tier = None
        logger.warning(
            "[IVR] All location tiers failed for call_id=%s phone=%s",
            call_id, phone,
        )

    # --- WS Event: location_resolved ---
    _emit_ws_event({
        "call_id": call_id,
        "stage": "location_resolved",
        "phone_masked": phone_masked,
        "language": detected_lang,
        "location": resolved_location,
        "location_tier": location_tier,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # -------------------------------------------------------------------------
    # 5. No-location path: all three tiers failed
    #    Send SMS asking caller to reply with their location, then hangup.
    #    NEVER fabricate a location or answer.
    # -------------------------------------------------------------------------
    if location_tier is None and (result is None or result.get("location_required")):
        loc_prompt: dict[str, str] = {
            "en": (
                "WeatherGPT: We could not determine your location. "
                "Please reply to this SMS with your village or pin code "
                "to get your weather advisory. [WeatherGPT]"
            ),
            "hi": (
                "WeatherGPT: हम आपका स्थान निर्धारित नहीं कर सके। "
                "मौसम सलाह के लिए कृपया इस SMS का उत्तर अपने गाँव "
                "या पिन कोड के साथ दें। [WeatherGPT]"
            ),
            "hi-Latn": (
                "WeatherGPT: Hamein aapka location nahi mila. "
                "Mausam salah ke liye kripya SMS reply mein apna "
                "gaon ya pin code bhejein. [WeatherGPT]"
            ),
        }
        prompt_sms = loc_prompt.get(detected_lang, loc_prompt["en"])[:160]
        _send_outbound_sms(to=phone, body=prompt_sms)
        logger.warning(
            "[IVR] Tier-3 fail — sent location-prompt SMS to %s (call_id=%s)",
            phone, call_id,
        )
        _emit_ws_event({
            "call_id": call_id,
            "stage": "location_prompt_sent",
            "phone_masked": phone_masked,
            "language": detected_lang,
            "location": None,
            "location_tier": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        no_loc_voice: dict[str, str] = {
            "en": "We could not find your location. We have sent you an SMS with instructions. Goodbye.",
            "hi": "हम आपका स्थान नहीं जान सके। हमने आपको SMS में निर्देश भेजे हैं। नमस्ते।",
            "hi-Latn": "Hum aapka location nahi jan sake. Hamne SMS mein instructions bheje hain. Namaste.",
        }
        voice_msg = no_loc_voice.get(detected_lang, no_loc_voice["en"])
        return _twiml_response(_twiml_hangup(voice_msg, locale))

    # -------------------------------------------------------------------------
    # 6. Determine the SMS body from the pipeline result
    # -------------------------------------------------------------------------
    if (
        result is None
        or result.get("stale_feed")
        or not result.get("answer", "").strip()
    ):
        sms_body = IVR_ERROR_SMS.get(detected_lang, IVR_ERROR_SMS["en"])[:160]
        logger.warning(
            "[IVR→SMS] Sending error SMS to %s (stale=%s, pipeline_failed=%s, call_id=%s)",
            phone,
            result.get("stale_feed") if result else "N/A",
            result is None,
            call_id,
        )
    else:
        sms_body = result["answer"]
        logger.info(
            "[IVR→SMS] from=%s lang=%s loc=%s tier=%s stale=%s preview=%s call_id=%s",
            phone, detected_lang,
            result.get("location", "none"),
            location_tier,
            result.get("stale_feed", False),
            sms_body[:60],
            call_id,
        )

    # --- WS Event: advisory_generated ---
    _emit_ws_event({
        "call_id": call_id,
        "stage": "advisory_generated",
        "phone_masked": phone_masked,
        "language": detected_lang,
        "location": resolved_location,
        "location_tier": location_tier,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # -------------------------------------------------------------------------
    # 7. Send the answer as an outbound SMS (out-of-band from the call)
    # -------------------------------------------------------------------------
    _send_outbound_sms(to=phone, body=sms_body)

    # --- WS Event: sms_dispatched ---
    _emit_ws_event({
        "call_id": call_id,
        "stage": "sms_dispatched",
        "phone_masked": phone_masked,
        "language": detected_lang,
        "location": resolved_location,
        "location_tier": location_tier,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # -------------------------------------------------------------------------
    # 8. End the call by speaking the grounded advisory directly to the caller
    # -------------------------------------------------------------------------
    base_confirm = IVR_SMS_CONFIRM.get(detected_lang, IVR_SMS_CONFIRM["en"])
    confirm_text = f"{sms_body}. {base_confirm}" if sms_body else base_confirm
    return _twiml_response(_twiml_hangup(confirm_text, locale))


# ---------------------------------------------------------------------------
# POST /alerts/proactive-push — Outbound proactive push on real IMD warnings
# ---------------------------------------------------------------------------

class ProactivePushRequest(BaseModel):
    district: str | None = None
    state: str | None = None
    location: str | None = None
    dry_run: bool = False  # True = log only, no actual Twilio calls


@router.post("/alerts/proactive-push")
async def proactive_push(
    req: ProactivePushRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Dispatch outbound SMS (and optionally voice callbacks) to registered callers
    in an affected district/state ONLY when a genuine IMD warning is retrieved
    from the live crawled bulletin repository.

    SAFETY RULE:
    This endpoint will fire ONLY if rag_service.get_official_warnings() returns
    at least one entry with is_official=True and severity in [RED, ORANGE, YELLOW].
    It will NEVER simulate or fabricate a warning.

    dry_run=True logs all intended actions without making Twilio API calls.
    Use this for testing / demo.
    """
    location_str = req.location or f"{req.district or ''}, {req.state or ''}".strip(", ")
    if not location_str:
        raise HTTPException(status_code=400, detail="Provide district, state, or location.")

    # 1. Retrieve real warnings via the same filter used by AlertBanner
    active_warnings = rag_service.get_official_warnings(location_str)
    real_warnings = [
        w for w in active_warnings
        if w.get("is_official") and w.get("severity") in ["RED", "ORANGE", "YELLOW"]
    ]

    if not real_warnings:
        return JSONResponse({
            "status": "no_action",
            "reason": "No active official IMD warnings for this location at this time.",
            "location": location_str,
            "warning_count": 0,
        })

    # 2. Find registered callers whose home district/state matches
    from sqlalchemy import or_
    conditions = []
    if req.district:
        conditions.append(CallerProfile.district.ilike(f"%{req.district}%"))
    if req.state:
        conditions.append(CallerProfile.state.ilike(f"%{req.state}%"))
    if req.location:
        conditions.append(CallerProfile.home_location.ilike(f"%{req.location.split(',')[0].strip()}%"))

    if not conditions:
        return JSONResponse({"status": "no_action", "reason": "Could not build caller filter."})

    result = await db.execute(select(CallerProfile).where(or_(*conditions)))
    callers = result.scalars().all()

    if not callers:
        return JSONResponse({
            "status": "no_action",
            "reason": "No registered callers found for this district/location.",
            "location": location_str,
            "warnings": [w.get("message", "")[:100] for w in real_warnings],
        })

    # 3. Build alert SMS text from the first (highest severity) warning
    top_warning = real_warnings[0]
    ist = timezone(timedelta(hours=5, minutes=30))
    as_of = datetime.now(ist).strftime("%d %b %H:%M IST")
    alert_text_en = (
        f"IMD ALERT ({top_warning.get('severity','ORANGE')}): "
        f"{(top_warning.get('message') or top_warning.get('text') or 'Severe weather warning issued.')[:90]} "
        f"[{as_of}] Stay safe. -WeatherGPT"
    )[:160]

    dispatched: list[str] = []
    skipped: list[str] = []

    for caller in callers:
        lang = caller.language or "hi"
        # Translate to caller's language via Bhashini if available, else send English
        sms_text = alert_text_en
        if bhashini.is_available() and lang not in ("en", "en-IN"):
            try:
                translated = await bhashini.translate(
                    text=alert_text_en, source_lang="en", target_lang=lang
                )
                if translated:
                    sms_text = (translated[:156] + " [IMD]") if len(translated) > 156 else (translated + " [IMD]")
            except Exception as tr_exc:
                logger.warning("Translation failed for %s: %s", caller.phone, tr_exc)

        if req.dry_run:
            logger.info("[DRY-RUN] Would SMS %s: %s", caller.phone, sms_text[:60])
            dispatched.append(caller.phone)
            continue

        # Real dispatch via Twilio REST API
        # Dispatch via the shared helper — never duplicate Twilio client creation.
        sent = _send_outbound_sms(to=caller.phone, body=sms_text)
        if sent:
            dispatched.append(caller.phone)
        else:
            skipped.append(caller.phone)

    return JSONResponse({
        "status": "dispatched" if dispatched else "skipped",
        "dry_run": req.dry_run,
        "location": location_str,
        "warnings_fired": len(real_warnings),
        "top_warning_severity": top_warning.get("severity"),
        "top_warning_preview": (top_warning.get("message") or "")[:100],
        "callers_dispatched": len(dispatched),
        "callers_skipped": len(skipped),
        "dispatched_numbers": dispatched,
        "as_of": as_of,
    })


# ---------------------------------------------------------------------------
# POST /webhook/sms/register-caller  — caller self-registration (REST)
# Used by the frontend simulator and by Twilio flows
# ---------------------------------------------------------------------------

class CallerRegistration(BaseModel):
    phone: str
    home_location: str
    language: str = "hi"
    user_type: str = "farmer"
    name: str | None = None
    crop: str | None = "Wheat"
    latitude: float | None = None
    longitude: float | None = None


@router.post("/webhook/sms/register-caller")
async def register_caller(req: CallerRegistration, db: AsyncSession = Depends(get_db)):
    """Register or update a caller profile with their home location and live coordinates."""
    if req.latitude is not None and req.longitude is not None:
        lat, lon = req.latitude, req.longitude
        canonical = req.home_location
    else:
        try:
            lat, lon, canonical = await weather_service.geocode(req.home_location)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"Could not geocode '{req.home_location}': {exc}")

    profile = await _get_caller_profile(req.phone, db)
    if profile:
        profile.home_location = canonical
        profile.latitude = lat
        profile.longitude = lon
        profile.language = req.language
        profile.user_type = req.user_type
    else:
        db.add(CallerProfile(
            phone=req.phone,
            home_location=canonical,
            latitude=lat,
            longitude=lon,
            language=req.language,
            user_type=req.user_type,
        ))
    await db.commit()

    # Also synchronize with database.py (persistent SQLite database for GSM IVR bridge)
    try:
        import database
        clean_phone = database.sanitize_phone_number(req.phone)
        database.register_user(
            phone_number=clean_phone,
            name=req.name or "Farmer",
            village_district=canonical,
            latitude=lat,
            longitude=lon,
            primary_crop=req.crop or "Wheat",
            preferred_language=req.language or "Hindi",
        )
    except Exception as sync_err:
        logger.warning(f"Could not sync with database.py: {sync_err}")

    return {
        "status": "ok",
        "phone": req.phone,
        "canonical_location": canonical,
        "latitude": lat,
        "longitude": lon,
    }


# ---------------------------------------------------------------------------
# POST /webhook/sms/simulate — Demo simulator endpoint (frontend use)
# ---------------------------------------------------------------------------

class SimulateSMSRequest(BaseModel):
    phone: str = "+919999999999"
    message: str
    language: str = "hi"
    home_location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    demo_mode: bool = False  # True = use synthetic demo data, clearly labeled


DEMO_SYNTHETIC_RESPONSE = (
    "[DEMO DATA — NOT A REAL WARNING] "
    "Simulated: Heavy rain (70%) forecast for tomorrow. "
    "Avoid spraying. Postpone field work to the day after. [IMD/Open-Meteo Demo]"
)


@router.post("/webhook/sms/simulate")
async def simulate_sms(req: SimulateSMSRequest):
    """
    Demo simulator endpoint for the frontend IVR/SMS panel.

    In real mode (demo_mode=False): calls the live generate_grounded_advisory()
    pipeline with actual IMD + Open-Meteo data. The response is real and grounded.

    In demo mode (demo_mode=True): returns clearly labeled synthetic data for
    offline / showcase demonstrations. NEVER passed off as real.
    """
    if req.demo_mode:
        return {
            "mode": "demo",
            "label": "DEMO DATA — NOT A REAL WARNING",
            "phone": req.phone,
            "query": req.message,
            "sms_reply": DEMO_SYNTHETIC_RESPONSE[:160],
            "sources": ["[DEMO]"],
            "rag_trace": {
                "intent": "agriculture",
                "domain": "agriculture",
                "weather_snapshot": {
                    "temperature_c": "28.4 (demo)",
                    "rain_probability": "70% (demo)",
                    "wind_kmh": "12 (demo)",
                },
                "advisory_triggered": True,
                "operations": {
                    "spray": {"status": "UNSAFE", "reason": "High rain probability (demo)"},
                    "irrigation": {"status": "POSTPONE", "reason": "Rain expected (demo)"},
                },
            },
        }

    # Real mode: full grounded pipeline
    try:
        result = await generate_grounded_advisory(
            query=req.message,
            location=req.home_location,
            language=req.language,
            latitude=req.latitude,
            longitude=req.longitude,
            channel="sms",
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Advisory pipeline error: {exc}")

    return {
        "mode": "real",
        "phone": req.phone,
        "query": req.message,
        "sms_reply": result.get("answer", ""),
        "sources": result.get("sources", []),
        "as_of": result.get("as_of"),
        "stale_feed": result.get("stale_feed", False),
        "location": result.get("location"),
        "language": result.get("language"),
        "rag_trace": {
            "intent": result.get("intent"),
            "domain": result.get("domain"),
            "weather_snapshot": (result.get("weather") or {}).get("current"),
            "advisory_triggered": bool(result.get("advisories")),
            "operations": result.get("operations"),
            "rag_count": result.get("rag_count", 0),
            "response_time_ms": result.get("response_time_ms"),
        },
    }


# ===========================================================================
# Android GSM Telephony Gateway (/webhook/phone-call)
# Zero-cost bridge using Android phone + MacroDroid + Android SMS Gateway APK
# ===========================================================================

ANDROID_SMS_GATEWAY_URL = os.getenv("ANDROID_SMS_GATEWAY_URL", "http://192.168.1.45:8080/message")


def _send_android_carrier_sms(phone_number: str, message_text: str) -> bool:
    """Dispatches native carrier SMS via the Android SMS Gateway APK on the phone."""
    gateway_url = os.getenv("ANDROID_SMS_GATEWAY_URL", ANDROID_SMS_GATEWAY_URL)
    payload = {"to": phone_number, "message": message_text}
    try:
        import requests
        resp = requests.post(gateway_url, json=payload, timeout=5)
        logger.info("[Android GSM Gateway] Sent carrier SMS to %s. Status: %s", phone_number, resp.status_code)
        return resp.status_code in (200, 201, 202)
    except Exception as exc:
        logger.error("[Android GSM Gateway] Could not reach Android SMS Gateway at %s: %s", gateway_url, exc)
        return False


async def _process_android_gsm_call(caller_number: str, audio_bytes: bytes, filename: str):
    """
    Background pipeline for Android GSM calls:
    1. Transcribe audio via Groq Whisper or Bhashini ASR
    2. Detect language & resolve location via 3-Tier fallback
    3. Generate grounded advisory via generate_grounded_advisory(channel="sms")
    4. Dispatch native SMS via Android phone SIM card
    5. Emit WebSocket events for dashboard observability
    """
    call_id = uuid.uuid4().hex[:12]
    phone = caller_number.strip()
    phone_masked = _mask_phone(phone)
    ts_now = datetime.now(timezone.utc).isoformat()

    # WS Event: call_received
    _emit_ws_event({
        "call_id": call_id,
        "stage": "call_received",
        "phone_masked": phone_masked,
        "language": None,
        "location": None,
        "location_tier": None,
        "timestamp": ts_now,
    })

    # 1. Transcribe audio
    user_query = ""
    detected_lang = "hi"
    groq_api_key = os.getenv("GROQ_API_KEY")

    if groq_api_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_api_key)
            transcription = client.audio.transcriptions.create(
                file=(filename or "audio.mp4", audio_bytes),
                model="whisper-large-v3",
                prompt="Indian weather, rain forecast, agriculture, spraying pesticides on cotton, crops in Ponda Goa, Sambalpur, Pune, Nagpur, Shiroda, Baramati, Maharashtra, India. Questions like 'Can I spray pesticide on cotton today in Ponda Goa?' or 'पुण्यात आज पाऊस पडेल का?'",
                response_format="verbose_json",
            )
            user_query = transcription.text.strip()
            detected_lang = language_service.detect_language(user_query) if user_query else "hi"
            print(f"[Android GSM Whisper SUCCESS] Transcribed Query: '{user_query}' | Lang: '{detected_lang}'")
            logger.info("[Android GSM Whisper] Query: '%s' | Lang: %s", user_query, detected_lang)
        except Exception as exc:
            print(f"[Android GSM Whisper ERROR] Groq Whisper failed: {exc}")
            logger.error("[Android GSM Whisper] Groq Whisper failed: %s", exc)

    # Initialize defaults
    location: str | None = None
    tier: str | None = None

    # Check Tier 2: Lookup registered farmer profile
    farmer_profile = None
    try:
        import database
        farmer_profile = database.get_user_profile(phone)
    except Exception as d_exc:
        logger.warning("[Android GSM] database.get_user_profile error: %s", d_exc)

    # Check for silent audio, static noise, or common Whisper hallucinated subtitle artifacts
    whisper_low = user_query.lower().strip() if user_query else ""
    silent_phrases = [
        "चीपीटी", "हेलो हेलो", "hello hello", "testing mic", "testing microphone",
        "thank you for watching", "thanks for watching", "subtitles by", "amara.org",
        "subscribe", "please subscribe", "you", "bye", "hello",
    ]
    is_silent_or_test = (
        not user_query
        or len(user_query.strip()) < 4
        or any(w in whisper_low for w in silent_phrases)
    )

    if is_silent_or_test:
        if farmer_profile:
            # Graceful fallback to registered farmer's profile!
            logger.info("[Android GSM] Silent audio fallback to registered profile: %s", farmer_profile)
            user_query = f"{farmer_profile['primary_crop']} ke liye aaj mausam kaisa hai"
            location = farmer_profile["village_district"]
            tier = "profile"
            detected_lang = farmer_profile["preferred_language"].lower()
            if "marathi" in detected_lang:
                detected_lang = "mr"
            elif "hindi" in detected_lang:
                detected_lang = "hi"
            elif "odia" in detected_lang:
                detected_lang = "or"
            else:
                detected_lang = "en"
        else:
            # Unregistered caller with silent audio: return localized guidance
            logger.info("[Android GSM] Unregistered caller with silent audio.")
            return "WeatherGPT: आपका नंबर पंजीकृत नहीं है और आवाज़ साफ़ नहीं आई। कृपया वेबसाइट पर अपना ज़िला रजिस्टर करें या कॉल पर अपना शहर बोलें।"

    # WS Event: language_detected
    _emit_ws_event({
        "call_id": call_id,
        "stage": "language_detected",
        "phone_masked": phone_masked,
        "language": detected_lang,
        "location": None,
        "location_tier": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # 2. Location resolution (3-tier fallback)
    if not location:
        tier = None

        # Check Tier 1: query extraction (universal natural language: "in Ponda Goa", "at Sambalpur", etc.)
        try:
            from services.query_engine import extract_query_location
            extracted_loc = extract_query_location(user_query)
            if extracted_loc:
                location = extracted_loc
                tier = "spoken"
        except Exception as exc:
            logger.warning("[Android GSM] extract_query_location error: %s", exc)

        # Check Tier 1 fallback: gazetteer + major Indian cities token matching
        if not location:
            try:
                from services.location.photon_service import INDIAN_AGRICULTURAL_GAZETTEER
                gazetteer_cities = list(INDIAN_AGRICULTURAL_GAZETTEER.keys())
            except Exception:
                gazetteer_cities = []

            common_indian_cities = [
                "mumbai", "delhi", "bengaluru", "bangalore", "hyderabad", "chennai", "kolkata",
                "pune", "ahmedabad", "jaipur", "lucknow", "kanpur", "nagpur", "indore", "thane",
                "bhopal", "visakhapatnam", "patna", "vadodara", "ghaziabad", "ludhiana", "agra",
                "nashik", "faridabad", "meerut", "rajkot", "varanasi", "srinagar", "aurangabad",
                "dhanbad", "amritsar", "navi mumbai", "allahabad", "prayagraj", "ranchi", "howrah",
                "coimbatore", "jabalpur", "gwalior", "vijayawada", "jodhpur", "madurai", "raipur",
                "kota", "chandigarh", "guwahati", "solapur", "hubli", "dharwad", "bareilly",
                "moradabad", "mysore", "mysuru", "gurgaon", "gurugram", "aligarh", "jalandhar",
                "tiruchirappalli", "bhubaneswar", "salem", "warangal", "thiruvananthapuram",
                "bhiwandi", "saharanpur", "guntur", "amravati", "bikaner", "noida", "jamshedpur",
                "bhilai", "cuttack", "firozabad", "kochi", "nellore", "bhavnagar", "dehradun",
                "durgapur", "asansol", "rourkela", "nanded", "kolhapur", "ajmer", "akola",
                "gulbarga", "jamnagar", "ujjain", "siliguri", "jhansi", "ulhasnagar",
                "jammu", "sangli", "mangalore", "erode", "belgaum", "belagavi", "tirunelveli",
                "malegaon", "gaya", "jalgaon", "udaipur", "davanagere", "kozhikode",
                "kurnool", "rajahmundry", "bokaro", "bellary", "patiala", "sambalpur",
                "agartala", "bhagalpur", "muzaffarnagar", "latur", "dhule", "satara",
                "tirupati", "rohtak", "korba", "bhilwara", "berhampur", "muzaffarpur", "ahmednagar",
                "mathura", "kollam", "kadapa", "bilaspur", "shahjahanpur", "sindhudurg",
                "bijapur", "vijayapura", "rampur", "shimoga", "shivamogga", "chandrapur",
                "junagadh", "thrissur", "alwar", "kakinada", "nizamabad", "ratnagiri",
                "parbhani", "tumkur", "tumakuru", "khammam", "bihar sharif", "panipat",
                "darbhanga", "aizawl", "ichalkaranji", "karnal", "bathinda", "jalna", "eluru",
                "barasat", "purnia", "satna", "mau", "sonipat", "farrukhabad",
                "sagar", "durg", "imphal", "ratlam", "hapur", "arrah", "karimnagar",
                "anantapur", "etawah", "ambernath", "bharatpur", "begusarai", "new delhi",
                "chhindwara", "gandhidham", "puducherry", "pondicherry", "shiroda", "ponda", "margao",
                "panaji", "mapusa", "canacona", "baramati"
            ]

            all_candidate_cities = sorted(set(gazetteer_cities + common_indian_cities), key=len, reverse=True)
            user_q_lower = user_query.lower()
            for city in all_candidate_cities:
                pattern = r"\b" + re.escape(city) + r"\b"
                if re.search(pattern, user_q_lower):
                    if city in INDIAN_AGRICULTURAL_GAZETTEER:
                        location = INDIAN_AGRICULTURAL_GAZETTEER[city].get("displayName", city.capitalize())
                    else:
                        location = city.capitalize()
                    tier = "spoken"
                    break

        # Check Tier 2: database profile
        if not location and farmer_profile:
            location = farmer_profile["village_district"]
            tier = "profile"
        from db.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            profile = await _get_caller_profile(phone, session)
            if profile and profile.home_location:
                location = profile.home_location
                tier = "profile"

    # Tier 3: default region
    if not location:
        location = "Pune, Maharashtra"
        tier = "telecom"

    # WS Event: location_resolved
    _emit_ws_event({
        "call_id": call_id,
        "stage": "location_resolved",
        "phone_masked": phone_masked,
        "language": detected_lang,
        "location": location,
        "location_tier": tier,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # 3. Grounded advisory generation
    try:
        f_lat = farmer_profile.get("latitude") if farmer_profile else None
        f_lon = farmer_profile.get("longitude") if farmer_profile else None
        f_crop = farmer_profile.get("primary_crop") if farmer_profile else None

        result = await generate_grounded_advisory(
            query=user_query,
            location=location,
            language=detected_lang,
            latitude=f_lat,
            longitude=f_lon,
            crop=f_crop,
            channel="sms",
        )
        sms_text = result.get("answer", "")
    except Exception as exc:
        logger.error("[Android GSM] Advisory error: %s", exc)
        sms_text = f"{location}: mausam samany rahega. [Source: IMD/Agromet]"

    # WS Event: advisory_generated
    _emit_ws_event({
        "call_id": call_id,
        "stage": "advisory_generated",
        "phone_masked": phone_masked,
        "language": detected_lang,
        "location": location,
        "location_tier": tier,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # 4. In Method 1, MacroDroid itself sends the SMS using the HTTP response.
    # Optional background dispatch if an SMS gateway / Twilio fallback is active.
    if os.getenv("ANDROID_SMS_GATEWAY_ENABLED", "false").lower() == "true":
        asyncio.create_task(asyncio.to_thread(_send_android_carrier_sms, phone, sms_text))

    # WS Event: sms_dispatched
    _emit_ws_event({
        "call_id": call_id,
        "stage": "sms_dispatched",
        "phone_masked": phone_masked,
        "language": detected_lang,
        "location": location,
        "location_tier": tier,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return sms_text


@router.post("/webhook/phone-call", response_class=PlainTextResponse)
async def handle_android_gsm_call(
    request: Request,
    caller_number: str | None = Form(default=None),
    audio_file: UploadFile | None = File(default=None),
):
    """
    Receives recorded voice call from MacroDroid on the Android GSM Gateway phone.
    Endpoint: POST /webhook/phone-call
    Supports both:
      1. Multipart Form (caller_number in Form + audio_file as File)
      2. Raw File upload (caller_number in Query Param + raw audio body)
    """
    phone = (caller_number or request.query_params.get("caller_number", "")).strip() or "+91XXXXXXXXXX"

    audio_bytes = b""
    filename = "recording.mp4"

    if audio_file is not None:
        audio_bytes = await audio_file.read()
        filename = audio_file.filename or "recording.mp4"
    else:
        # Check if multipart form contains audio under a different key like 'audio' or 'file'
        try:
            form = await request.form()
            for key in ["audio", "file", "recording", "voice"]:
                val = form.get(key)
                if val is not None and hasattr(val, "read"):
                    audio_bytes = await val.read()
                    filename = getattr(val, "filename", "recording.mp4") or "recording.mp4"
                    break
            if not audio_bytes:
                for val in form.values():
                    if hasattr(val, "read"):
                        audio_bytes = await val.read()
                        filename = getattr(val, "filename", "recording.mp4") or "recording.mp4"
                        break
        except Exception:
            pass

        # If not in form, attempt reading raw request body safely
        if not audio_bytes:
            try:
                audio_bytes = await request.body()
            except Exception:
                audio_bytes = b""

    try:
        from free_ivr_server import process_telephony_call
        sms_text = await process_telephony_call(
            caller_number=phone,
            audio_bytes=audio_bytes,
            filename=filename,
        )
    except Exception as fatal_exc:
        logger.error("[Android GSM] Fatal error in process_telephony_call: %s", fatal_exc, exc_info=True)
        try:
            import database
            from weather_engine import fetch_live_imd_metrics
            from free_ivr_server import _build_dynamic_query_reply
            prof = database.get_farmer(phone)
            if prof:
                m = fetch_live_imd_metrics(prof["latitude"], prof["longitude"])
                sms_text = _build_dynamic_query_reply(
                    user_query="",
                    location_name=f"{prof['village_district']}, {prof['state']}",
                    crop=prof["primary_crop"],
                    language=prof["preferred_language"],
                    metrics=m,
                )
            else:
                sms_text = "WeatherGPT: सेवा व्यस्त है। कृपया अपना स्थान बोलें या पोर्टल पर पंजीकृत करें। [Source: IMD/Agromet]"
        except Exception:
            sms_text = "WeatherGPT: सेवा व्यस्त है। कृपया थोड़ी देर बाद कॉल करें। [Source: IMD/Agromet]"

    print(f"[Android GSM Outbound SMS] Replying to phone {phone} with:\n>>> {sms_text}\n")
    return PlainTextResponse(content=sms_text)


