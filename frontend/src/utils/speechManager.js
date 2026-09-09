/**
 * WeatherGPT Speech Synthesis Manager (SIH26068)
 *
 * Provides a robust controller for browser text-to-speech with:
 * 1. Real Hindi voice discovery & scoring (Lekha, Google हिन्दी, Swara, Madhur)
 * 2. Strict fallback protection (NEVER speaks Hindi or Indic scripts with an English voice)
 * 3. Answer language detection based on text characters (Devanagari -> Hindi)
 * 4. Asynchronous voice loading handling for Chromium & WebKit
 * 5. Instant cancellation of prior audio (single active playback)
 * 6. Development console logging ([TTS] Provider / Language / Voice / Text)
 * 7. Global test function window.__testTTS() for quick verification
 */

export const LOCALE_TARGETS = {
  en: ["en-IN", "en_IN", "en-US", "en-GB", "en"],
  hi: ["hi-IN", "hi_IN", "hi"],
  mr: ["mr-IN", "mr_IN", "mr"],
  gu: ["gu-IN", "gu_IN", "gu"],
  bn: ["bn-IN", "bn_IN", "bn-BD", "bn"],
  ta: ["ta-IN", "ta_IN", "ta-LK", "ta"],
  te: ["te-IN", "te_IN", "te"],
  kn: ["kn-IN", "kn_IN", "kn"],
  ml: ["ml-IN", "ml_IN", "ml"],
  pa: ["pa-IN", "pa_IN", "pa-PK", "pa"],
  or: ["or-IN", "or_IN", "or", "od-IN", "od"],
};

export const LANGUAGE_KEYWORDS = {
  en: ["english", "india", "indian", "rishi", "aman"],
  hi: ["hindi", "हिन्दी", "devanagari", "lekha", "swara", "madhur", "hemant", "kalpana"],
  mr: ["marathi", "मराठी", "lekha"],
  gu: ["gujarati", "ગુજરાતી", "dhwani", "niranjan"],
  bn: ["bengali", "bangla", "বাংলা", "piya", "tanisha", "bashkar"],
  ta: ["tamil", "தமிழ்", "vani", "valluvar"],
  te: ["telugu", "తెలుగు", "geeta", "mohan"],
  kn: ["kannada", "ಕನ್ನಡ", "soumya", "gagan"],
  ml: ["malayalam", "മലയാളം", "sobhana", "midhun"],
  pa: ["punjabi", "ਪੰਜਾਬੀ", "gurmukhi", "raajan"],
  or: ["odia", "oriya", "ଓଡ଼ିଆ"],
};

export const VOICE_NOT_FOUND_MESSAGES = {
  hi: "इस डिवाइस पर हिंदी आवाज़ उपलब्ध नहीं है।",
  mr: "या डिव्हाइसवर मराठी आवाज उपलब्ध नाही.",
  gu: "આ ઉપકરણ પર ગુજરાતી અવાજ ઉપલબ્ધ નથી.",
  bn: "এই ডিভাইসে বাংলা ভয়েস উপলব্ধ নেই।",
  ta: "இந்த சாதனத்தில் தமிழ் குரல் கிடைக்கவில்லை.",
  te: "ఈ పరికరంలో తెలుగు వాయిస్ అందుబాటులో లేదు.",
  kn: "ಈ ಸಾಧನದಲ್ಲಿ ಕನ್ನಡ ಧ್ವನಿ ಲಭ್ಯವಿಲ್ಲ.",
  ml: "ഈ ഉപകരണത്തിൽ മലയാളം ശബ്ദം ലഭ്യമല്ല.",
  pa: "ਇਸ ਡਿਵਾਈਸ ਤੇ ਪੰਜਾਬੀ ਆਵਾਜ਼ ਉਪਲਬਧ ਨਹੀਂ ਹੈ।",
  or: "ଏହି ଡିଭାଇସରେ ଓଡ଼ିଆ ସ୍ୱର ଉପଲବ୍ଧ ନାହିଁ।",
  en: "Voice playback is unavailable on this device.",
};

let currentGlobalAudio = null;

export function stopGlobalAudio() {
  if (currentGlobalAudio) {
    try {
      currentGlobalAudio.pause();
      currentGlobalAudio.currentTime = 0;
      if (currentGlobalAudio.src && currentGlobalAudio.src.startsWith("blob:")) {
        URL.revokeObjectURL(currentGlobalAudio.src);
      }
    } catch {}
    currentGlobalAudio = null;
  }
  if (typeof window !== "undefined") {
    speechManager.stop();
    window.dispatchEvent(new CustomEvent("weathergpt:stop_audio"));
  }
}

export function registerGlobalAudio(audioElement) {
  stopGlobalAudio();
  currentGlobalAudio = audioElement;
}

/**
 * Detect language of an answer based on its text script rather than solely UI context.
 * Devanagari script -> Hindi (or Marathi if user selected Marathi).
 * Latin characters -> English / Hinglish.
 */
export function detectAnswerLanguage(text, fallbackLang = "en") {
  if (!text || typeof text !== "string") return fallbackLang || "en";

  // Check script ranges in answer text
  if (/[\u0900-\u097F]/.test(text)) {
    // Devanagari script (Hindi / Marathi)
    if (fallbackLang === "mr") return "mr";
    return "hi";
  }
  if (/[\u0980-\u09FF]/.test(text)) return "bn";
  if (/[\u0A00-\u0A7F]/.test(text)) return "pa";
  if (/[\u0A80-\u0AFF]/.test(text)) return "gu";
  if (/[\u0B00-\u0B7F]/.test(text)) return "or";
  if (/[\u0B80-\u0BFF]/.test(text)) return "ta";
  if (/[\u0C00-\u0C7F]/.test(text)) return "te";
  if (/[\u0C80-\u0CFF]/.test(text)) return "kn";
  if (/[\u0D00-\u0D7F]/.test(text)) return "ml";

  // Latin characters or no Indic scripts -> fallback or English
  return fallbackLang && fallbackLang !== "hi" ? fallbackLang : "en";
}

/**
 * Phonetically expands weather units and strips markdown, citations, emojis for clean TTS.
 */
export function prepareTTS(text, langCode = "en") {
  if (!text) return "";
  let cleaned = String(text);

  // Remove code blocks and inline code
  cleaned = cleaned.replace(/```[\s\S]*?```/g, " ");
  cleaned = cleaned.replace(/`([^`]+)`/g, "$1");

  // Remove markdown links [text](url) -> text
  cleaned = cleaned.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");

  // Remove bracketed citations like [1], [IMD + Open-Meteo], [source: ...]
  cleaned = cleaned.replace(/\[[^\]]*\]/g, " ");

  // Remove markdown headings, bold, italics, bullets, blockquotes
  cleaned = cleaned.replace(/#{1,6}\s+/g, " ");
  cleaned = cleaned.replace(/[*_~]{1,3}/g, " ");
  cleaned = cleaned.replace(/^\s*[-*•+]\s+/gm, " ");
  cleaned = cleaned.replace(/^\s*>\s+/gm, " ");

  // Remove common emojis
  cleaned = cleaned.replace(
    /([\u2700-\u27BF]|[\uE000-\uF8FF]|\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|[\u2011-\u26FF]|\uD83E[\uDD10-\uDDFF])/g,
    " "
  );

  const lang = (langCode || "en").toLowerCase().split("-")[0];

  if (lang === "hi") {
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°\s*C\b/gi, "$1 डिग्री सेल्सियस");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°/g, "$1 डिग्री");
    cleaned = cleaned.replace(/°C/gi, " डिग्री सेल्सियस ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*%/g, "$1 प्रतिशत");
    cleaned = cleaned.replace(/%/g, " प्रतिशत ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*(?:km\/h|kmph|किमी\/घंटा|किमी प्रति घंटा)/gi, "$1 किलोमीटर प्रति घंटा");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*mm\b/gi, "$1 मिलीमीटर");
    cleaned = cleaned.replace(/[:—–-]/g, ", ");
  } else if (lang === "mr") {
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°\s*C\b/gi, "$1 डिग्री सेल्सिअस");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°/g, "$1 डिग्री");
    cleaned = cleaned.replace(/°C/gi, " डिग्री सेल्सिअस ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*%/g, "$1 टक्के");
    cleaned = cleaned.replace(/%/g, " टक्के ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*(?:km\/h|kmph|किमी\/तास)/gi, "$1 किलोमीटर प्रति तास");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*mm\b/gi, "$1 मिलीमीटर");
    cleaned = cleaned.replace(/[:—–-]/g, ", ");
  } else if (lang === "gu") {
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°\s*C\b/gi, "$1 ડિગ્રી સેલ્સિયસ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°/g, "$1 ડિગ્રી");
    cleaned = cleaned.replace(/°C/gi, " ડિગ્રી સેલ્સિયસ ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*%/g, "$1 ટકા");
    cleaned = cleaned.replace(/%/g, " ટકા ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*(?:km\/h|kmph)/gi, "$1 કિલોમીટર પ્રતિ કલાક");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*mm\b/gi, "$1 મિલીમીટર");
  } else if (lang === "bn") {
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°\s*C\b/gi, "$1 ডিগ্রি সেলসিয়াস");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°/g, "$1 ডিগ্রি");
    cleaned = cleaned.replace(/°C/gi, " ডিগ্রি সেলসিয়াস ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*%/g, "$1 শতাংশ");
    cleaned = cleaned.replace(/%/g, " শতাংশ ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*(?:km\/h|kmph)/gi, "$1 কিলোমিটার প্রতি ঘণ্টা");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*mm\b/gi, "$1 মিলিমিটার");
  } else if (lang === "ta") {
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°\s*C\b/gi, "$1 டிகிரி செல்சியஸ்");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°/g, "$1 டிகிரி");
    cleaned = cleaned.replace(/°C/gi, " டிகிரி செல்சியஸ் ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*%/g, "$1 சதவீதம்");
    cleaned = cleaned.replace(/%/g, " சதவீதம் ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*(?:km\/h|kmph)/gi, "$1 கிலோமீட்டர் மணி");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*mm\b/gi, "$1 மில்லிமீட்டர்");
  } else if (lang === "te") {
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°\s*C\b/gi, "$1 డిగ్రీల సెల్సియస్");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°/g, "$1 డిగ్రీల");
    cleaned = cleaned.replace(/°C/gi, " డిగ్రీల సెల్సియస్ ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*%/g, "$1 శాతం");
    cleaned = cleaned.replace(/%/g, " శాతం ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*(?:km\/h|kmph)/gi, "$1 కిలోమీటర్లు ప్రతి గంట");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*mm\b/gi, "$1 మిల్లీమీటర్లు");
  } else if (lang === "kn") {
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°\s*C\b/gi, "$1 ಡಿಗ್ರಿ ಸೆಲ್ಸಿಯಸ್");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°/g, "$1 ಡಿಗ್ರಿ");
    cleaned = cleaned.replace(/°C/gi, " ಡಿಗ್ರಿ ಸೆಲ್ಸಿಯಸ್ ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*%/g, "$1 ಪ್ರತಿಶತ");
    cleaned = cleaned.replace(/%/g, " ಪ್ರತಿಶತ ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*(?:km\/h|kmph)/gi, "$1 ಕಿಲೋಮೀಟರ್ ಪ್ರತಿ ಗಂಟೆಗೆ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*mm\b/gi, "$1 ಮಿಲಿಮೀಟರ್");
  } else if (lang === "ml") {
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°\s*C\b/gi, "$1 ഡിഗ്രി സെൽഷ്യസ്");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°/g, "$1 ഡിഗ്രി");
    cleaned = cleaned.replace(/°C/gi, " ഡിഗ്രി സെൽഷ്യസ് ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*%/g, "$1 ശതമാനം");
    cleaned = cleaned.replace(/%/g, " ശതമാനം ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*(?:km\/h|kmph)/gi, "$1 കിലോമീറ്റർ പ്രതി മണിക്കൂർ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*mm\b/gi, "$1 മില്ലിമീറ്റർ");
  } else if (lang === "pa") {
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°\s*C\b/gi, "$1 ਡਿਗਰੀ ਸੈਲਸੀਅਸ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°/g, "$1 ਡਿਗਰੀ");
    cleaned = cleaned.replace(/°C/gi, " ਡਿਗਰੀ ਸੈਲਸੀਅਸ ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*%/g, "$1 ਪ੍ਰਤੀਸ਼ਤ");
    cleaned = cleaned.replace(/%/g, " ਪ੍ਰਤੀਸ਼ਤ ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*(?:km\/h|kmph)/gi, "$1 ਕਿਲੋਮੀਟਰ ਪ੍ਰਤੀ ਘੰਟਾ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*mm\b/gi, "$1 ਮਿਲੀਮੀਟਰ");
  } else if (lang === "or") {
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°\s*C\b/gi, "$1 ଡିଗ୍ରୀ ସେଲସିୟସ୍");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°/g, "$1 ଡିଗ୍ରୀ");
    cleaned = cleaned.replace(/°C/gi, " ଡିଗ୍ରୀ ସେଲସିୟସ୍ ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*%/g, "$1 ପ୍ରତିଶତ");
    cleaned = cleaned.replace(/%/g, " ପ୍ରତିଶତ ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*(?:km\/h|kmph)/gi, "$1 କିଲୋମିଟର ପ୍ରତି ଘଣ୍ଟା");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*mm\b/gi, "$1 ମିଲିମିଟର");
  } else {
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°\s*C\b/gi, "$1 degrees Celsius");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*°/g, "$1 degrees");
    cleaned = cleaned.replace(/°C/gi, " degrees Celsius ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*%/g, "$1 percent");
    cleaned = cleaned.replace(/%/g, " percent ");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*(?:km\/h|kmph)/gi, "$1 kilometers per hour");
    cleaned = cleaned.replace(/(\d+(?:\.\d+)?)\s*mm\b/gi, "$1 millimeters");
  }

  return cleaned.replace(/\s+/g, " ").trim();
}

/**
 * Accurately scores a SpeechSynthesisVoice for a target language.
 * Strict Disqualification: Never permits English or foreign voices to speak Hindi / Indic scripts.
 */
export function scoreVoice(voice, langCode = "en") {
  if (!voice) return -1;
  const cleanLang = (langCode || "en").toLowerCase().split("-")[0];
  const voiceLang = (voice.lang || "").toLowerCase().replace("_", "-");
  const voiceName = (voice.name || "").toLowerCase();

  // === HINDI VOICE SCORING ===
  if (cleanLang === "hi") {
    // HARD DISQUALIFICATION: Never speak Hindi with English voices
    if (voiceLang.startsWith("en") || voiceName.includes("english")) return -1;

    // Disqualify foreign languages
    const foreign = [
      "es-", "fr-", "de-", "zh-", "ja-", "ru-", "ar-", "ko-",
      "it-", "pt-", "nl-", "sv-", "pl-", "tr-", "vi-", "id-"
    ];
    if (foreign.some((prefix) => voiceLang.startsWith(prefix))) return -1;

    let score = 0;

    // 1. High-Priority Known Hindi Voices
    if (voiceName.includes("lekha")) {
      score += 1200; // macOS Indian Hindi (Lekha)
    } else if (
      voiceName.includes("google हिन्दी") ||
      (voiceName.includes("google") && voiceName.includes("हिन्दी"))
    ) {
      score += 1100; // Chrome Google हिन्दी
    } else if (voiceName.includes("google hindi")) {
      score += 1050;
    } else if (voiceName.includes("swara")) {
      score += 1000; // Windows / Edge Microsoft Swara Natural
    } else if (voiceName.includes("madhur")) {
      score += 1000; // Windows / Edge Microsoft Madhur Natural
    } else if (voiceName.includes("hemant")) {
      score += 900;
    } else if (voiceName.includes("kalpana")) {
      score += 900;
    } else if (
      voiceName.includes("hindi") ||
      voiceName.includes("हिन्दी") ||
      voiceName.includes("devanagari")
    ) {
      score += 600;
    }

    // 2. Strict Locale Matching
    if (voiceLang === "hi-in") {
      score += 500;
    } else if (voiceLang.startsWith("hi")) {
      score += 400;
    }

    // 3. Quality & Natural Enhancements
    if (voiceName.includes("natural") || voiceName.includes("neural") || voiceName.includes("online")) {
      score += 100;
    }
    if (voiceName.includes("enhanced") || voiceName.includes("premium")) {
      score += 80;
    }
    if (voice.localService) {
      score += 20;
    }

    return score > 0 ? score : -1;
  }

  // === ENGLISH VOICE SCORING ===
  if (cleanLang === "en") {
    // Disqualify non-English voices
    if (!voiceLang.startsWith("en") && !voiceName.includes("english")) return -1;

    let score = 50; // Base English voice
    // Prioritize Indian English voices
    if (voiceName.includes("rishi")) {
      score += 1200; // macOS Rishi
    } else if (voiceName.includes("aman")) {
      score += 1100; // macOS Aman
    } else if (
      voiceName.includes("google") &&
      (voiceName.includes("indian english") || voiceName.includes("en-in"))
    ) {
      score += 1000;
    } else if (
      voiceName.includes("veena") ||
      voiceName.includes("pradeep") ||
      voiceName.includes("neerja")
    ) {
      score += 900;
    } else if (voiceLang === "en-in") {
      score += 600;
    }

    if (voiceName.includes("natural") || voiceName.includes("neural")) score += 50;
    if (voiceName.includes("enhanced")) score += 40;
    return score;
  }

  // === OTHER INDIC LANGUAGES SCORING ===
  // Disqualify English and unrelated foreign languages
  if (voiceLang.startsWith("en") || voiceName.includes("english")) return -1;
  const foreign = ["es-", "fr-", "de-", "zh-", "ja-", "ru-", "ar-", "ko-", "it-", "pt-", "nl-"];
  if (foreign.some((prefix) => voiceLang.startsWith(prefix))) return -1;

  const targetLocales = LOCALE_TARGETS[cleanLang] || [cleanLang];
  const keywords = LANGUAGE_KEYWORDS[cleanLang] || [cleanLang];

  let score = 0;
  for (const target of targetLocales) {
    if (voiceLang === target.toLowerCase()) {
      score += 500;
      break;
    } else if (voiceLang.startsWith(target.toLowerCase().split("-")[0])) {
      score += 300;
      break;
    }
  }

  for (const kw of keywords) {
    if (voiceName.includes(kw.toLowerCase())) {
      score += 400;
      break;
    }
  }

  // Marathi fallback: Lekha natively speaks Devanagari phonemes properly
  if (cleanLang === "mr" && voiceName.includes("lekha")) {
    score += 350;
  }

  return score > 0 ? score : -1;
}

class SpeechManager {
  constructor() {
    this.voices = [];
    this.isSupported = typeof window !== "undefined" && "speechSynthesis" in window;
    this.currentUtterance = null;
    this.isSpeaking = false;
    this.activeCallback = null;

    if (this.isSupported) {
      this.initVoices();
    }
  }

  initVoices() {
    const load = () => {
      try {
        const v = window.speechSynthesis.getVoices();
        if (v && v.length > 0) {
          this.voices = v;
        }
      } catch {}
    };

    load();
    if (typeof window !== "undefined" && window.speechSynthesis) {
      if (typeof window.speechSynthesis.addEventListener === "function") {
        window.speechSynthesis.addEventListener("voiceschanged", load);
      } else {
        window.speechSynthesis.onvoiceschanged = load;
      }
    }
  }

  /**
   * Robust async voice loader that handles Chromium/WebKit empty initial array.
   */
  async getVoicesAsync(timeoutMs = 1200) {
    if (!this.isSupported) return [];

    let current = [];
    try {
      current = window.speechSynthesis.getVoices() || [];
    } catch {}

    if (current && current.length > 0) {
      this.voices = current;
      return current;
    }

    return new Promise((resolve) => {
      let resolved = false;

      const finish = () => {
        if (!resolved) {
          resolved = true;
          try {
            this.voices = window.speechSynthesis.getVoices() || [];
          } catch {
            this.voices = [];
          }
          resolve(this.voices);
        }
      };

      const timer = setTimeout(finish, timeoutMs);

      const handler = () => {
        clearTimeout(timer);
        if (typeof window.speechSynthesis.removeEventListener === "function") {
          window.speechSynthesis.removeEventListener("voiceschanged", handler);
        }
        finish();
      };

      if (typeof window.speechSynthesis.addEventListener === "function") {
        window.speechSynthesis.addEventListener("voiceschanged", handler);
      } else {
        window.speechSynthesis.onvoiceschanged = handler;
      }

      // Interval poll fallback in case voiceschanged was missed
      const poll = setInterval(() => {
        const v = window.speechSynthesis.getVoices();
        if (v && v.length > 0) {
          clearInterval(poll);
          clearTimeout(timer);
          finish();
        }
      }, 50);

      setTimeout(() => clearInterval(poll), timeoutMs);
    });
  }

  /**
   * Finds the best voice for a language using strict scoring.
   * Returns null if no suitable voice exists on device (preventing English fallback for Hindi).
   */
  findBestVoice(voices, langCode = "en") {
    const cleanLang = (langCode || "en").toLowerCase().split("-")[0];
    let list = voices && voices.length > 0 ? voices : this.voices;

    // Direct live query if still empty
    if ((!list || list.length === 0) && typeof window !== "undefined" && window.speechSynthesis) {
      try {
        list = window.speechSynthesis.getVoices() || [];
      } catch {}
    }

    if (!list || list.length === 0) return null;

    let bestVoice = null;
    let highestScore = -1;

    for (const v of list) {
      const s = scoreVoice(v, cleanLang);
      if (s > highestScore) {
        highestScore = s;
        bestVoice = v;
      }
    }

    // If English requested and no voice scored positive, fallback to any English voice or first
    if (!bestVoice && cleanLang === "en") {
      const anyEn = list.find((v) => (v.lang || "").toLowerCase().startsWith("en"));
      return anyEn || list[0] || null;
    }

    return highestScore > 0 ? bestVoice : null;
  }

  async getVoiceInfo(langCode) {
    const voices = await this.getVoicesAsync();
    const v = this.findBestVoice(voices, langCode);
    if (!v) return null;
    return {
      name: v.name,
      lang: v.lang,
      localService: v.localService,
    };
  }

  sanitizeForSpeech(text, langCode = "en") {
    return prepareTTS(text, langCode);
  }

  chunkText(text) {
    if (!text) return [];
    const rawParts = text.split(/([।\.!\?\n]+)/);
    const chunks = [];
    let current = "";

    for (let i = 0; i < rawParts.length; i++) {
      const part = rawParts[i];
      current += part;
      if (/[।\.!\?\n]/.test(part) || current.length > 90) {
        const trimmed = current.trim();
        if (trimmed) chunks.push(trimmed);
        current = "";
      }
    }
    if (current.trim()) {
      chunks.push(current.trim());
    }
    return chunks.length > 0 ? chunks : [text];
  }

  stop() {
    this.isSpeaking = false;
    this.currentUtterance = null;
    if (!this.isSupported) return;
    try {
      window.speechSynthesis.cancel();
    } catch {}
    if (this.activeCallback) {
      const cb = this.activeCallback;
      this.activeCallback = null;
      cb();
    }
  }

  async speak(text, langCode = "en", { onStart, onEnd, onError } = {}) {
    if (!this.isSupported) {
      if (onError) onError("Speech synthesis is not supported in this browser.");
      return;
    }

    this.stop();

    const cleanLang = (langCode || "en").toLowerCase().split("-")[0];
    const cleanText = prepareTTS(text, cleanLang);
    if (!cleanText) {
      if (onEnd) onEnd();
      return;
    }

    const voices = await this.getVoicesAsync();
    const matchedVoice = this.findBestVoice(voices, cleanLang);

    // Strict Hindi & Indic safety: Refuse to speak Hindi with an English voice
    if (!matchedVoice && cleanLang !== "en") {
      const errorMsg =
        VOICE_NOT_FOUND_MESSAGES[cleanLang] ||
        `Voice playback is unavailable for ${cleanLang.toUpperCase()} on this device.`;
      console.warn(
        `[TTS] No genuine voice found for ${cleanLang.toUpperCase()} on this device.\n` +
          `Refusing to speak ${cleanLang.toUpperCase()} with an English voice.\n` +
          `Installed device voices (${voices.length}): ${voices.map((v) => `${v.name} [${v.lang}]`).join(", ")}`
      );
      if (onError) onError(errorMsg);
      return;
    }

    // Required development console log format
    console.log(
      `[TTS]\nProvider: Browser SpeechSynthesis\nLanguage: ${
        matchedVoice ? matchedVoice.lang : cleanLang
      }\nVoice: ${matchedVoice ? matchedVoice.name : "Default"}\nVoice language: ${
        matchedVoice ? matchedVoice.lang : cleanLang
      }\nText: ${cleanText}`
    );

    const chunks = this.chunkText(cleanText);
    this.isSpeaking = true;
    this.activeCallback = onEnd;

    let chunkIndex = 0;

    const speakNext = () => {
      if (!this.isSpeaking || chunkIndex >= chunks.length) {
        this.isSpeaking = false;
        this.currentUtterance = null;
        if (onEnd) onEnd();
        return;
      }

      const chunk = chunks[chunkIndex++];
      try {
        const utterance = new SpeechSynthesisUtterance(chunk);

        if (matchedVoice) {
          utterance.voice = matchedVoice;
          utterance.lang = matchedVoice.lang;
        } else {
          utterance.lang = (LOCALE_TARGETS[cleanLang] && LOCALE_TARGETS[cleanLang][0]) || "en-IN";
        }

        utterance.rate = 0.95;
        utterance.pitch = 1.0;

        utterance.onstart = () => {
          if (chunkIndex === 1 && onStart) onStart();
        };

        utterance.onend = () => {
          if (this.isSpeaking) {
            speakNext();
          }
        };

        utterance.onerror = (e) => {
          this.isSpeaking = false;
          this.currentUtterance = null;
          if (e.error === "interrupted" || e.error === "canceled") {
            if (onEnd) onEnd();
          } else {
            if (onError) onError(`Speech error: ${e.error || "Playback failed"}`);
          }
        };

        this.currentUtterance = utterance;
        window.speechSynthesis.speak(utterance);
      } catch (err) {
        this.isSpeaking = false;
        if (onError) onError(err.message || "Failed to start speech.");
      }
    };

    speakNext();
  }

  /**
   * Diagnostic test function for developer console:
   * window.__testTTS("hi")
   */
  async testTTS(langCode = "hi", customText = null) {
    console.group(`[TTS Diagnostic Test] Testing Language: "${langCode}"`);
    console.log("Querying speech voices from browser...");
    const voices = await this.getVoicesAsync();
    console.log(`Total available voices on device: ${voices.length}`);

    if (console.table && voices.length > 0) {
      console.table(
        voices.map((v) => ({
          name: v.name,
          lang: v.lang,
          default: v.default,
          localService: v.localService,
        }))
      );
    } else {
      console.log(voices.map((v) => `${v.name} (${v.lang})`).join("; "));
    }

    const cleanLang = (langCode || "hi").toLowerCase().split("-")[0];
    const bestVoice = this.findBestVoice(voices, cleanLang);

    console.log(
      `Chosen Voice for "${cleanLang}":`,
      bestVoice ? `${bestVoice.name} (${bestVoice.lang})` : "NONE (No matching voice found)"
    );

    const testText =
      customText ||
      (cleanLang === "hi"
        ? "नमस्ते। आज मौसम सुहावना है।"
        : cleanLang === "mr"
        ? "नमस्कार. आज हवामान छान आहे."
        : "Hello! Today the weather is pleasant.");

    if (!bestVoice && cleanLang !== "en") {
      const msg = VOICE_NOT_FOUND_MESSAGES[cleanLang] || "Voice unavailable on this device.";
      console.warn(`[TTS Test Failed] ${msg}`);
      console.groupEnd();
      return { status: "voice_unavailable", lang: cleanLang, message: msg };
    }

    console.log(`Speaking test text: "${testText}"`);
    console.groupEnd();

    this.speak(testText, cleanLang, {
      onStart: () => console.log("[TTS Test] Audio playback started"),
      onEnd: () => console.log("[TTS Test] Audio playback completed"),
      onError: (err) => console.error("[TTS Test] Error during playback:", err),
    });

    return {
      status: "speaking",
      lang: cleanLang,
      voice: bestVoice ? bestVoice.name : "Default",
      voiceLang: bestVoice ? bestVoice.lang : "en-IN",
      text: testText,
    };
  }
}

export const speechManager = new SpeechManager();

// Register globally in browser for immediate dev testing
if (typeof window !== "undefined") {
  window.__testTTS = (lang = "hi", text = null) => speechManager.testTTS(lang, text);
}

export default speechManager;
