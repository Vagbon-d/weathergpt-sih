"""
Native System Text-to-Speech (TTS) Provider for WeatherGPT.

Leverages installed operating system speech synthesis (e.g. macOS `say` + `afconvert`)
to produce authentic, high-quality audio with native Indic pronunciation (Lekha for Hindi,
Rishi for Indian English, Piya for Bengali, Vani for Tamil, Geeta for Telugu, Soumya for Kannada).

Outputs standard 16-bit PCM WAV base64 audio compatible with any HTML5 browser.
"""

from __future__ import annotations

import base64
import logging
import os
import platform
import shutil
import subprocess
import tempfile
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Native voice map for macOS speech synthesis
MACOS_VOICE_MAP = {
    "hi": "Lekha",
    "hi-latn": "Rishi",
    "en": "Rishi",
    "kn": "Soumya",
    "te": "Geeta",
    "ta": "Vani",
    "bn": "Piya",
    "mr": "Lekha",  # Lekha natively speaks Devanagari phonemes
    "kok": "Lekha", # Lekha natively speaks Devanagari phonemes
}

_AVAILABLE_VOICES_CACHE: Optional[set[str]] = None


def get_available_macos_voices() -> set[str]:
    """Inspect and cache voices installed on macOS."""
    global _AVAILABLE_VOICES_CACHE
    if _AVAILABLE_VOICES_CACHE is not None:
        return _AVAILABLE_VOICES_CACHE

    voices = set()
    if platform.system() == "Darwin" and shutil.which("say"):
        try:
            res = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=3.0)
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if parts:
                    voices.add(parts[0])
        except Exception as exc:
            logger.warning("Failed to query macOS voices: %s", exc)

    _AVAILABLE_VOICES_CACHE = voices
    return _AVAILABLE_VOICES_CACHE


def synthesize_native_tts(text: str, language: str = "hi") -> Optional[dict[str, Any]]:
    """
    Synthesizes speech using the local operating system voice and converts to standard WAV.
    Returns dictionary with audio_base64, format, provider, and voice details, or None if unavailable.
    """
    clean_lang = (language or "en").lower().split("-")[0]
    if clean_lang == "hi" and "latn" in language.lower():
        clean_lang = "hi-latn"

    target_voice = MACOS_VOICE_MAP.get(clean_lang)
    if not target_voice and clean_lang == "en":
        target_voice = "Samantha"

    if not target_voice:
        return None

    # Check if voice is installed on macOS
    installed = get_available_macos_voices()
    if target_voice not in installed:
        logger.info("Target voice '%s' for language '%s' is not installed in macOS.", target_voice, clean_lang)
        return None

    afconvert_bin = shutil.which("afconvert") or "/usr/bin/afconvert"
    if not os.path.exists(afconvert_bin):
        logger.warning("afconvert utility not found; cannot convert audio.")
        return None

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            aiff_path = os.path.join(tmpdir, "output.aiff")
            wav_path = os.path.join(tmpdir, "output.wav")

            # 1. Synthesize AIFF audio using native say command
            say_proc = subprocess.run(
                ["say", "-v", target_voice, "-o", aiff_path, text],
                capture_output=True,
                text=True,
                timeout=8.0,
            )
            if say_proc.returncode != 0 or not os.path.exists(aiff_path):
                logger.warning("say command failed: %s", say_proc.stderr)
                return None

            # 2. Convert AIFF to standard 16-bit PCM Linear WAV
            conv_proc = subprocess.run(
                [afconvert_bin, "-f", "WAVE", "-d", "LEI16", aiff_path, wav_path],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if conv_proc.returncode != 0 or not os.path.exists(wav_path):
                logger.warning("afconvert command failed: %s", conv_proc.stderr)
                return None

            with open(wav_path, "rb") as f:
                wav_bytes = f.read()

            if not wav_bytes:
                return None

            b64_str = base64.b64encode(wav_bytes).decode("ascii")
            return {
                "available": True,
                "provider": "macos_system",
                "voice": target_voice,
                "format": "wav",
                "language": clean_lang,
                "audio_base64": b64_str,
                "size_bytes": len(wav_bytes),
            }
    except Exception as exc:
        logger.error("Exception during native system TTS synthesis: %s", exc)
        return None
