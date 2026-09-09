import React, { useEffect, useRef, useState } from 'react';
import {
  IconMic,
  IconSend,
  IconBot,
  IconMapPin,
  IconCopy,
  IconCheck,
  IconAlertTriangle,
} from './Icons';
import { SPEECH_LOCALE } from '../i18n';
import ReadAloudButton from './ReadAloudButton';
import { useLanguage } from '../i18n/LanguageContext';

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    if (!text) return;
    navigator.clipboard?.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex items-center gap-1 text-[11px] font-medium text-stone-500 hover:text-stone-800 transition-colors cursor-pointer py-1 px-2 rounded-lg hover:bg-stone-100"
      title={copied ? 'Copied' : 'Copy answer'}
    >
      {copied ? <IconCheck className="w-3.5 h-3.5 text-[#1E5631]" /> : <IconCopy className="w-3.5 h-3.5" />}
      <span>{copied ? 'Copied' : 'Copy'}</span>
    </button>
  );
}

export default function ChatPanel({ messages, onSend, isWaiting, onRequestLocation }) {
  const { language, t } = useLanguage();
  const [input, setInput] = useState('');
  const [listening, setListening] = useState(false);
  const [micNote, setMicNote] = useState('');
  const recognitionRef = useRef(null);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const isSubmittingRef = useRef(false);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, isWaiting]);

  const submit = (text) => {
    if (isWaiting || isSubmittingRef.current) return;
    const value = (text ?? input).trim();
    if (!value) return;
    isSubmittingRef.current = true;
    onSend(value);
    setInput('');
    setTimeout(() => {
      isSubmittingRef.current = false;
    }, 400);
  };

  const handleKeyDown = (e) => {
    if (e.nativeEvent?.isComposing || e.isComposing) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  const toggleVoice = () => {
    if (isWaiting) return;
    if (listening) {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch {
          // ignore
        }
      }
      setListening(false);
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setMicNote(t('micUnsupported', 'Voice input not supported in this browser -- try Chrome or type instead.'));
      return;
    }
    setMicNote('');
    try {
      const recognition = new SpeechRecognition();
      recognition.lang = SPEECH_LOCALE[language] || 'en-IN';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => setListening(true);
      recognition.onend = () => setListening(false);
      recognition.onerror = (e) => {
        setListening(false);
        if (e.error !== 'no-speech' && e.error !== 'aborted') {
          setMicNote(t('micUnsupported', 'Voice input failed.'));
        }
      };
      recognition.onresult = (event) => {
        const transcript = event.results?.[0]?.[0]?.transcript;
        if (transcript) {
          setInput(transcript);
          setMicNote(t('transcriptReady', 'Voice input recognized. Review your question and press Send.'));
          if (inputRef.current) {
            inputRef.current.focus();
          }
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch {
      setListening(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white border border-stone-200/90 rounded-2xl shadow-xs overflow-hidden">
      {/* Header bar of Chat */}
      <div className="px-5 py-3.5 border-b border-stone-200 bg-stone-50/90 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#1E5631]/10 flex items-center justify-center text-[#1E5631]">
            <IconBot className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-xs text-[#1C2024]">
                {t('chatTitle', 'WeatherGPT — Your weather & farm assistant')}
              </span>
              <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" title="Online"></span>
            </div>
            <span className="text-[10px] text-stone-500 font-medium">
              {t('chatSubtitle', 'Bhashini & IMD Grounded')}
            </span>
          </div>
        </div>
      </div>

      {/* Messages list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3.5 min-h-[380px] max-h-[calc(100vh-14rem)]">
        {messages.map((m, i) => (
          <div key={m.id || i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[92%] sm:max-w-[88%] px-4 py-3 rounded-2xl text-xs sm:text-sm leading-relaxed ${
                m.role === 'user'
                  ? 'bg-[#1C2024] text-white rounded-br-xs shadow-xs'
                  : 'bg-white text-[#1C2024] border border-stone-200 rounded-bl-xs shadow-xs'
              }`}
            >
              {m.role !== 'user' && (
                <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-[#1E5631] mb-1.5">
                  <IconBot className="w-3 h-3" />
                  <span>WeatherGPT</span>
                </div>
              )}
              {/* Natural language response only - NEVER raw JSON */}
              <p className="whitespace-pre-wrap">{m.text}</p>

              {m.location_required && onRequestLocation && (
                <button
                  type="button"
                  onClick={onRequestLocation}
                  className="mt-2.5 inline-flex items-center gap-1.5 bg-[#1E5631] hover:bg-[#174426] text-white text-xs font-semibold px-3 py-1.5 rounded-xl shadow-xs transition-all cursor-pointer"
                >
                  <IconMapPin className="w-3.5 h-3.5" />
                  <span>{t('useLocation', 'Select Location')}</span>
                </button>
              )}

              {m.role !== 'user' && (
                <div className="mt-2.5 pt-2 border-t border-stone-100 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <ReadAloudButton text={m.text} language={m.language} />
                    <CopyButton text={m.text} />
                  </div>
                  <div className="text-[10px] text-stone-500 flex items-center gap-1.5 ml-auto">
                    <span>{t('sourcesAttribution', 'Sources: Open-Meteo · IMD')}</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Live waiting indicator */}
        {isWaiting && (
          <div className="flex justify-start">
            <div className="bg-stone-50 border border-stone-200 rounded-2xl rounded-bl-xs px-4 py-3 text-xs text-stone-600 flex items-center gap-2.5 shadow-xs">
              <span className="w-3.5 h-3.5 border-2 border-[#1E5631]/30 border-t-[#1E5631] rounded-full animate-spin"></span>
              <span className="font-medium text-[#1C2024]">{t('checkingWeather', 'Checking live weather data...')}</span>
            </div>
          </div>
        )}
      </div>

      {/* Mic/Voice notes */}
      {micNote && (
        <div className="text-xs text-amber-800 px-4 py-2 bg-amber-50 border-t border-amber-200 flex items-center gap-1.5">
          <IconAlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
          <span>{micNote}</span>
        </div>
      )}
      {listening && (
        <div className="text-xs text-[#1E5631] font-medium px-4 py-1.5 bg-[#1E5631]/5 border-t border-[#1E5631]/10 animate-pulse">
          {t('listening', 'Listening…')}
        </div>
      )}

      {/* Input controls */}
      <div className="p-3 border-t border-stone-200 bg-stone-50/50 flex items-center gap-2">
        <button
          type="button"
          onClick={toggleVoice}
          disabled={isWaiting}
          className={`w-10 h-10 shrink-0 rounded-full flex items-center justify-center transition-all cursor-pointer ${
            listening
              ? 'bg-amber-600 text-white shadow-md animate-pulse'
              : 'bg-stone-100 text-stone-700 hover:bg-stone-200 disabled:opacity-50'
          }`}
          aria-label={listening ? t('stopAudio', 'Stop') : t('askByVoice', 'Speak your question')}
          title={listening ? t('stopAudio', 'Stop listening') : t('askByVoice', 'Speak your question')}
        >
          <IconMic className="w-4 h-4" />
        </button>

        <textarea
          ref={inputRef}
          rows="1"
          value={input}
          disabled={isWaiting}
          onChange={(e) => {
            setInput(e.target.value);
            if (micNote) setMicNote('');
          }}
          onKeyDown={handleKeyDown}
          placeholder={t('chatPlaceholder', 'Ask WeatherGPT anything about weather, farming, or travel…')}
          className="flex-1 bg-white border border-stone-200 rounded-xl px-3.5 py-2.5 text-xs sm:text-sm text-[#1C2024] outline-none focus:ring-2 focus:ring-[#1E5631]/20 focus:border-[#1E5631] resize-none min-h-[40px] max-h-[100px] disabled:opacity-60"
        />

        <button
          type="button"
          onClick={() => submit()}
          disabled={isWaiting || !input.trim()}
          className="w-10 h-10 shrink-0 rounded-full bg-[#1E5631] text-white flex items-center justify-center hover:bg-[#174426] disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-xs cursor-pointer"
          aria-label={t('send', 'Send')}
        >
          <IconSend className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
