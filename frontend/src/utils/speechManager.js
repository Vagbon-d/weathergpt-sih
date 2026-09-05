/**
 * WeatherGPT Speech Synthesis Manager (SIH26068)
 *
 * Provides a robust singleton controller for browser text-to-speech with:
 * 1. Asynchronous voice pre-warming (solves Chromium empty voice list bug)
 * 2. Strict locale & voice name matching for 11 Indian languages (including macOS Lekha)
 * 3. Fallback protection (NEVER speaks Indian scripts with an English voice)
 * 4. Text cleaning and phonetic unit expansion (prepareTTS)
 * 5. Sentence chunking to prevent browser 15-second speech synthesis cutoff
 * 6. Global singleton cancellation (stops existing playback before starting new)
 */

export const LOCALE_TARGETS = {
  en: ["en-IN", "en-US", "en-GB", "en"],
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
  en: ["english", "india"],
  hi: ["hindi", "हिन्दी", "devanagari", "lekha"],
  mr: ["marathi", "मराठी"],
  gu: ["gujarati", "ગુજરાતી"],
  bn: ["bengali", "bangla", "বাংলা"],
  ta: ["tamil", "தமிழ்"],
  te: ["telugu", "తెలుగు"],
  kn: ["kannada", "ಕನ್ನಡ"],
  ml: ["malayalam", "മലയാളം"],
  pa: ["punjabi", "ਪੰਜਾਬੀ", "gurmukhi"],
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
  en: "No speech voice found for this language on your device.",
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
  cleaned = cleaned.replace(/([\u2700-\u27BF]|[\uE000-\uF8FF]|\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|[\u2011-\u26FF]|\uD83E[\uDD10-\uDDFF])/g, " ");

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
      } catch {
        // ignore
      }
    };

    load();
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.onvoiceschanged = load;
    }
  }

  async getVoicesAsync(timeoutMs = 1200) {
    if (!this.isSupported) return [];
    if (this.voices && this.voices.length > 0) {
      return this.voices;
    }

    return new Promise((resolve) => {
      let resolved = false;
      const timer = setTimeout(() => {
        if (!resolved) {
          resolved = true;
          this.voices = window.speechSynthesis.getVoices() || [];
          resolve(this.voices);
        }
      }, timeoutMs);

      const onVoices = () => {
        if (!resolved) {
          resolved = true;
          clearTimeout(timer);
          this.voices = window.speechSynthesis.getVoices() || [];
          resolve(this.voices);
        }
      };

      if (window.speechSynthesis.onvoiceschanged !== undefined) {
        const prev = window.speechSynthesis.onvoiceschanged;
        window.speechSynthesis.onvoiceschanged = (e) => {
          if (prev) prev(e);
          onVoices();
        };
      }
    });
  }

  findBestVoice(voices, langCode) {
    if (!voices || voices.length === 0) return null;
    const cleanLang = (langCode || "en").toLowerCase().split("-")[0];
    const targetLocales = LOCALE_TARGETS[cleanLang] || [cleanLang];
    const keywords = LANGUAGE_KEYWORDS[cleanLang] || [cleanLang];

    for (const target of targetLocales) {
      const match = voices.find(
        (v) => v.lang && v.lang.toLowerCase().replace("_", "-") === target.toLowerCase()
      );
      if (match) return match;
    }

    for (const target of targetLocales) {
      const prefix = target.split("-")[0].toLowerCase();
      const match = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith(prefix));
      if (match) return match;
    }

    for (const kw of keywords) {
      const match = voices.find((v) => v.name && v.name.toLowerCase().includes(kw));
      if (match) return match;
    }

    if (cleanLang === "en") {
      const enVoice = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith("en"));
      return enVoice || voices[0] || null;
    }

    return null;
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
    } catch {
      // ignore
    }
    if (this.activeCallback) {
      this.activeCallback();
      this.activeCallback = null;
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

    if (!matchedVoice && cleanLang !== "en") {
      const errorMsg =
        VOICE_NOT_FOUND_MESSAGES[cleanLang] ||
        `No speech voice found for ${cleanLang.toUpperCase()} on your device.`;
      if (onError) onError(errorMsg);
      return;
    }

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
}

export const speechManager = new SpeechManager();
export default speechManager;
