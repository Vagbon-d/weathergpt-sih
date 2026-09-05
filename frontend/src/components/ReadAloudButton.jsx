import React, { useState, useRef, useEffect } from "react";
import { synthesizeSpeech } from "../api";
import {
  speechManager,
  prepareTTS,
  stopGlobalAudio,
  registerGlobalAudio,
  VOICE_NOT_FOUND_MESSAGES,
} from "../utils/speechManager";
import { useLanguage } from "../i18n/LanguageContext";
import { IconVolume2, IconVolumeX, IconInfo, IconAlertTriangle } from "./Icons";

export default function ReadAloudButton({ text, language: overrideLang, t: overrideT }) {
  const { language: currentLang, t } = useLanguage();
  const activeLang = (overrideLang || currentLang || "en").toLowerCase().split("-")[0];

  const [status, setStatus] = useState("idle"); // "idle" | "preparing" | "playing"
  const [errorMessage, setErrorMessage] = useState(null);
  const [diagInfo, setDiagInfo] = useState(null);
  const [showDiag, setShowDiag] = useState(false);
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
    if (diagInfo) {
      setDiagInfo((prev) => (prev ? { ...prev, status: "Idle" } : null));
    }
  }

  async function handleToggleSpeech() {
    if (status === "playing" || status === "preparing") {
      stopGlobalAudio();
      return;
    }

    if (!text) return;
    setErrorMessage(null);
    stopGlobalAudio();
    setStatus("preparing");

    const cleanText = prepareTTS(text, activeLang);

    // Initial diagnostic state
    setDiagInfo({
      provider: "Connecting...",
      lang: activeLang,
      voice: "Searching...",
      locale: activeLang,
      status: "Preparing",
    });

    console.group("[WeatherGPT TTS] Read Aloud Request");
    console.log("Input Text:", cleanText);
    console.log("Requested Language:", activeLang);

    // 1. Attempt primary TTS via backend service (Bhashini or Native System Lekha/Rishi)
    try {
      const res = await synthesizeSpeech(cleanText, activeLang);
      if (res && res.audio_base64) {
        const mimeType = `audio/${res.format || "wav"}`;
        const audio = new Audio(`data:${mimeType};base64,${res.audio_base64}`);
        audioRef.current = audio;
        registerGlobalAudio(audio);

        const providerLabel =
          res.provider === "macos_system"
            ? `System TTS (${res.voice || "Native"})`
            : res.provider === "bhashini"
            ? "Bhashini Cloud TTS"
            : (res.provider || "Backend TTS");

        console.log("TTS Provider:", providerLabel);
        console.log("Selected Voice:", res.voice || res.service_id || "Native Indic");
        console.log("HTTP Status Code: 200");
        console.log("Audio Format / MIME:", mimeType);
        console.log("Audio Payload Size (bytes):", res.size_bytes || Math.round(res.audio_base64.length * 0.75));

        setDiagInfo({
          provider: providerLabel,
          lang: activeLang,
          voice: res.voice || res.service_id || "Native Indic",
          locale: res.language || activeLang,
          status: "Playing",
        });

        audio.onplay = () => {
          setStatus("playing");
          console.log("[WeatherGPT TTS] Audio playback started (HTML5 Audio)");
        };
        audio.onended = () => {
          audioRef.current = null;
          setStatus("idle");
          setDiagInfo((prev) => (prev ? { ...prev, status: "Finished" } : null));
          console.log("[WeatherGPT TTS] Audio playback finished successfully");
          console.groupEnd();
        };
        audio.onerror = (e) => {
          console.error("[WeatherGPT TTS] Audio playback error:", e);
          console.groupEnd();
          audioRef.current = null;
          playViaBrowserSpeech(cleanText);
        };

        await audio.play();
        return;
      }
    } catch (err) {
      console.warn("[WeatherGPT TTS] Backend TTS unavailable; falling back to browser SpeechSynthesis.", err);
    }

    // 2. Fallback to browser SpeechSynthesis with strict language voice matching
    playViaBrowserSpeech(cleanText);
  }

  async function playViaBrowserSpeech(cleanText) {
    console.log("Fallback Provider: Browser SpeechSynthesis");
    const voiceInfo = await speechManager.getVoiceInfo(activeLang);
    console.log("Matched Browser Voice:", voiceInfo ? `${voiceInfo.name} (${voiceInfo.lang})` : "None");

    if (!voiceInfo && activeLang !== "en") {
      setStatus("idle");
      const err =
        VOICE_NOT_FOUND_MESSAGES[activeLang] ||
        `इस डिवाइस पर ${activeLang.toUpperCase()} आवाज़ उपलब्ध नहीं है।`;
      setErrorMessage(err);
      setDiagInfo({
        provider: "Browser SpeechSynthesis",
        lang: activeLang,
        voice: "None (No voice matched)",
        locale: activeLang,
        status: "Voice Not Found",
      });
      console.warn(`[WeatherGPT TTS] Refusing to use an English voice for ${activeLang.toUpperCase()} speech.`);
      console.groupEnd();
      setTimeout(() => setErrorMessage(null), 5000);
      return;
    }

    setDiagInfo({
      provider: "Browser SpeechSynthesis",
      lang: activeLang,
      voice: voiceInfo ? voiceInfo.name : "System Default",
      locale: voiceInfo ? voiceInfo.lang : "en-IN",
      status: "Playing",
    });

    speechManager.speak(cleanText, activeLang, {
      onStart: () => {
        setStatus("playing");
        setErrorMessage(null);
        console.log("[WeatherGPT TTS] Browser speech playback started");
      },
      onEnd: () => {
        setStatus("idle");
        setDiagInfo((prev) => (prev ? { ...prev, status: "Finished" } : null));
        console.log("[WeatherGPT TTS] Browser speech playback finished");
        console.groupEnd();
      },
      onError: (err) => {
        setStatus("idle");
        setErrorMessage(err);
        setDiagInfo((prev) => (prev ? { ...prev, status: "Error" } : null));
        console.error("[WeatherGPT TTS] Browser speech error:", err);
        console.groupEnd();
        setTimeout(() => setErrorMessage(null), 4000);
      },
    });
  }

  const readLabel = overrideT?.readAloud || t("readAloud", "Read Aloud");
  const preparingLabel = overrideT?.preparingAudio || t("preparingAudio", "Preparing audio...");
  const stopLabel = overrideT?.stopAudio || t("stopAudio", "Stop");

  return (
    <div className="inline-flex flex-col items-start gap-1">
      <div className="inline-flex items-center gap-1.5">
        <button
          type="button"
          onClick={handleToggleSpeech}
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all shadow-sm select-none ${
            status === "playing"
              ? "bg-amber-500 text-white hover:bg-amber-600 animate-pulse"
              : status === "preparing"
              ? "bg-gray-200 text-gray-700 cursor-wait dark:bg-gray-700 dark:text-gray-300"
              : "bg-white text-gray-700 border border-gray-200 hover:bg-gray-50 hover:text-blue-600 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700"
          }`}
          title={status === "playing" ? stopLabel : status === "preparing" ? preparingLabel : readLabel}
        >
          {status === "playing" ? (
            <>
              <span className="w-2 h-2 rounded-sm bg-white inline-block"></span>
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

        {/* Diagnostic Toggle Button */}
        {diagInfo && (
          <button
            type="button"
            onClick={() => setShowDiag((v) => !v)}
            className="text-[10px] text-stone-400 hover:text-stone-600 px-1.5 py-0.5 rounded border border-stone-200 inline-flex items-center gap-1 cursor-pointer"
            title="Toggle TTS Diagnostic Info"
          >
            <IconInfo className="w-3 h-3" />
            <span>{showDiag ? "Hide TTS Info" : "TTS Info"}</span>
          </button>
        )}
      </div>

      {/* Temporary Development TTS Diagnostic Panel */}
      {diagInfo && (showDiag || status === "playing") && (
        <div className="text-[10px] font-mono px-2 py-1 rounded bg-stone-50 border border-stone-200 text-stone-600 flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5">
          <span className="font-semibold text-[#1E5631]">TTS:</span>
          <span>Provider: <span className="font-medium text-stone-800">{diagInfo.provider}</span></span>
          <span>•</span>
          <span>Lang: <span className="font-medium text-stone-800">{diagInfo.lang}</span></span>
          <span>•</span>
          <span>Voice: <span className="font-medium text-stone-800">{diagInfo.voice}</span></span>
          <span>•</span>
          <span>Locale: <span className="font-medium text-stone-800">{diagInfo.locale}</span></span>
          <span>•</span>
          <span className={`font-semibold ${status === "playing" ? "text-amber-600" : "text-emerald-600"}`}>
            [{diagInfo.status}]
          </span>
        </div>
      )}

      {errorMessage && (
        <span className="text-[11px] text-amber-700 mt-0.5 font-medium inline-flex items-center gap-1">
          <IconAlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
          <span>{errorMessage}</span>
        </span>
      )}
    </div>
  );
}
