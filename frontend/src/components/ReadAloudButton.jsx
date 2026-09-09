import React, { useState, useRef, useEffect } from "react";
import { synthesizeSpeech } from "../api";
import {
  speechManager,
  prepareTTS,
  stopGlobalAudio,
  registerGlobalAudio,
  detectAnswerLanguage,
  VOICE_NOT_FOUND_MESSAGES,
} from "../utils/speechManager";
import { useLanguage } from "../i18n/LanguageContext";
import { IconVolume2, IconAlertTriangle } from "./Icons";

export default function ReadAloudButton({ text, language: overrideLang, t: overrideT }) {
  const { language: currentLang, t } = useLanguage();

  // Answer Language Detection: Inspect the text content itself (Devanagari -> Hindi)
  // rather than relying solely on the global UI selector.
  const activeLang = detectAnswerLanguage(text, overrideLang || currentLang || "en")
    .toLowerCase()
    .split("-")[0];

  const [status, setStatus] = useState("idle"); // "idle" | "preparing" | "playing"
  const [errorMessage, setErrorMessage] = useState(null);
  const audioRef = useRef(null);

  // Global audio listener: if another message starts speaking or language changes, stop this one
  useEffect(() => {
    const handleStop = () => {
      setStatus("idle");
    };

    window.addEventListener("weathergpt:stop_audio", handleStop);
    return () => {
      window.removeEventListener("weathergpt:stop_audio", handleStop);
      stopAudio();
    };
  }, []);

  useEffect(() => {
    stopAudio();
  }, [activeLang]);

  function stopAudio() {
    if (audioRef.current) {
      try {
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
        if (audioRef.current.src && audioRef.current.src.startsWith("blob:")) {
          URL.revokeObjectURL(audioRef.current.src);
        }
      } catch {}
      audioRef.current = null;
    }
    speechManager.stop();
    setStatus("idle");
  }

  async function handleToggleSpeech() {
    // If currently speaking or preparing, clicking immediately cancels and returns to idle
    if (status === "playing" || status === "preparing") {
      stopAudio();
      stopGlobalAudio();
      return;
    }

    if (!text) return;
    setErrorMessage(null);
    stopGlobalAudio();
    setStatus("preparing");

    const cleanText = prepareTTS(text, activeLang);
    if (!cleanText) {
      setStatus("idle");
      return;
    }

    // 1. Attempt primary TTS via Bhashini if configured in backend
    try {
      const res = await synthesizeSpeech(cleanText, activeLang);
      if (res && res.available && res.provider === "bhashini" && res.audio_base64) {
        const mimeType = `audio/${res.format || "wav"}`;
        const audio = new Audio(`data:${mimeType};base64,${res.audio_base64}`);
        audioRef.current = audio;
        registerGlobalAudio(audio);

        // Required development console log format
        console.log(
          `[TTS]\nProvider: Bhashini\nLanguage: ${activeLang}\nVoice: ${
            res.voice || "Bhashini TTS"
          }\nVoice language: ${res.language || activeLang}\nText: ${cleanText}`
        );

        audio.onplay = () => {
          setStatus("playing");
        };
        audio.onended = () => {
          audioRef.current = null;
          setStatus("idle");
        };
        audio.onerror = (e) => {
          audioRef.current = null;
          // Smoothly fall back to browser speech synthesis
          playViaBrowserSpeech(cleanText, activeLang);
        };

        await audio.play();
        return;
      }
    } catch (err) {
      // Backend/Bhashini unavailable; smoothly continue to browser SpeechSynthesis
    }

    // 2. Smooth fallback to Browser SpeechSynthesis with real Hindi voice selection
    playViaBrowserSpeech(cleanText, activeLang);
  }

  async function playViaBrowserSpeech(cleanText, lang) {
    const voices = await speechManager.getVoicesAsync();
    const matchedVoice = speechManager.findBestVoice(voices, lang);

    // If device lacks genuine voice for this language, refuse to speak with an English voice
    if (!matchedVoice && lang !== "en") {
      setStatus("idle");
      const err =
        VOICE_NOT_FOUND_MESSAGES[lang] ||
        `इस डिवाइस पर ${lang.toUpperCase()} आवाज़ उपलब्ध नहीं है।`;
      setErrorMessage(err);
      console.warn(
        `[TTS] No genuine voice found for ${lang.toUpperCase()} on this device. Refusing to speak with English voice.`
      );
      setTimeout(() => setErrorMessage(null), 5000);
      return;
    }

    speechManager.speak(cleanText, lang, {
      onStart: () => {
        setStatus("playing");
        setErrorMessage(null);
      },
      onEnd: () => {
        setStatus("idle");
      },
      onError: (err) => {
        setStatus("idle");
        setErrorMessage(err);
        setTimeout(() => setErrorMessage(null), 4000);
      },
    });
  }

  const readLabel = overrideT?.readAloud || t("readAloud", "Read Aloud");
  const preparingLabel = overrideT?.preparingAudio || t("preparingAudio", "Preparing audio...");
  const stopLabel = overrideT?.stopAudio || t("stopAudio", "Stop");

  return (
    <div className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={handleToggleSpeech}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all shadow-xs select-none cursor-pointer ${
          status === "playing"
            ? "bg-amber-500 text-white hover:bg-amber-600 animate-pulse"
            : status === "preparing"
            ? "bg-stone-100 text-stone-600 cursor-wait dark:bg-stone-700 dark:text-stone-300"
            : "bg-white text-stone-700 border border-stone-200 hover:bg-stone-50 hover:text-[#1E5631] dark:bg-stone-800 dark:border-stone-700 dark:text-stone-300 dark:hover:bg-stone-700"
        }`}
        title={status === "playing" ? stopLabel : status === "preparing" ? preparingLabel : readLabel}
      >
        {status === "playing" ? (
          <>
            <span className="w-2 h-2 rounded-2xs bg-white inline-block"></span>
            <span>{stopLabel}</span>
          </>
        ) : status === "preparing" ? (
          <>
            <svg
              className="animate-spin -ml-0.5 mr-1 h-3 w-3 text-current"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              ></circle>
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v8H4z"
              ></path>
            </svg>
            <span>{preparingLabel}</span>
          </>
        ) : (
          <>
            <IconVolume2 className="w-3.5 h-3.5" />
            <span>{readLabel}</span>
          </>
        )}
      </button>

      {errorMessage && (
        <span className="text-[11px] text-amber-700 mt-0.5 font-medium inline-flex items-center gap-1">
          <IconAlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
          <span>{errorMessage}</span>
        </span>
      )}
    </div>
  );
}
