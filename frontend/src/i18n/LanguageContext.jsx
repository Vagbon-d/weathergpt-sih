import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { translateCondition } from './conditions';
import { speechManager } from '../utils/speechManager';

// Import all 12 locale dictionaries
import en from './locales/en.json';
import hi from './locales/hi.json';
import mr from './locales/mr.json';
import kok from './locales/kok.json';
import gu from './locales/gu.json';
import bn from './locales/bn.json';
import ta from './locales/ta.json';
import te from './locales/te.json';
import kn from './locales/kn.json';
import ml from './locales/ml.json';
import pa from './locales/pa.json';
import or from './locales/or.json';

const DICTIONARIES = { en, hi, mr, kok, gu, bn, ta, te, kn, ml, pa, or };

export const SUPPORTED_LANGUAGES = [
  { code: 'en', name: 'English', nativeName: 'English', voiceLang: 'en-IN' },
  { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी', voiceLang: 'hi-IN' },
  { code: 'mr', name: 'Marathi', nativeName: 'मराठी', voiceLang: 'mr-IN' },
  { code: 'kok', name: 'Konkani', nativeName: 'कोंकणी', voiceLang: 'kok-IN' },
  { code: 'gu', name: 'Gujarati', nativeName: 'ગુજરાતી', voiceLang: 'gu-IN' },
  { code: 'bn', name: 'Bengali', nativeName: 'বাংলা', voiceLang: 'bn-IN' },
  { code: 'ta', name: 'Tamil', nativeName: 'தமிழ்', voiceLang: 'ta-IN' },
  { code: 'te', name: 'Telugu', nativeName: 'తెలుగు', voiceLang: 'te-IN' },
  { code: 'kn', name: 'Kannada', nativeName: 'ಕನ್ನಡ', voiceLang: 'kn-IN' },
  { code: 'ml', name: 'Malayalam', nativeName: 'മലയാളം', voiceLang: 'ml-IN' },
  { code: 'pa', name: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ', voiceLang: 'pa-IN' },
  { code: 'or', name: 'Odia', nativeName: 'ଓଡ଼ିଆ', voiceLang: 'or-IN' },
];

// Map 2-letter language code to standard BCP-47 locale for Intl formatting
const INTL_LOCALE_MAP = {
  en: 'en-IN',
  hi: 'hi-IN',
  mr: 'mr-IN',
  kok: 'kok-IN',
  gu: 'gu-IN',
  bn: 'bn-IN',
  ta: 'ta-IN',
  te: 'te-IN',
  kn: 'kn-IN',
  ml: 'ml-IN',
  pa: 'pa-IN',
  or: 'or-IN',
};

const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(() => {
    try {
      const saved = sessionStorage.getItem('weathergpt_lang');
      if (saved && DICTIONARIES[saved]) {
        return saved;
      }
    } catch {
      // sessionStorage unavailable
    }
    return 'en';
  });

  const setLanguage = useCallback((newLang) => {
    if (DICTIONARIES[newLang]) {
      // Instantly stop any active speech synthesis when language changes
      try {
        speechManager.stop();
      } catch {
        // ignore
      }
      setLanguageState(newLang);
      try {
        sessionStorage.setItem('weathergpt_lang', newLang);
      } catch {
        // ignore
      }
    }
  }, []);

  // Update HTML lang attribute on change
  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = 'ltr';
  }, [language]);

  /**
   * Translate a key with optional fallback. Supports nested keys like 'crops.rice'.
   */
  const t = useCallback((key, fallback) => {
    if (!key) return '';
    const currentDict = DICTIONARIES[language] || DICTIONARIES.en;
    const enDict = DICTIONARIES.en;

    const resolveKey = (dict, path) => {
      const parts = path.split('.');
      let cur = dict;
      for (const part of parts) {
        if (cur && typeof cur === 'object' && part in cur) {
          cur = cur[part];
        } else {
          return undefined;
        }
      }
      return typeof cur === 'string' ? cur : undefined;
    };

    const res = resolveKey(currentDict, key);
    if (res !== undefined) return res;

    const fallbackRes = resolveKey(enDict, key);
    if (fallbackRes !== undefined) return fallbackRes;

    return fallback !== undefined ? fallback : key;
  }, [language]);

  /**
   * Format / translate weather condition string into current language.
   */
  const formatCondition = useCallback((conditionText) => {
    if (!conditionText) return '';
    return translateCondition(conditionText, language);
  }, [language]);

  /**
   * Localize date using Intl.DateTimeFormat with current language locale
   */
  const formatDate = useCallback((dateInput, options = { weekday: 'short', month: 'short', day: 'numeric' }) => {
    if (!dateInput) return '';
    try {
      const date = typeof dateInput === 'string' ? new Date(dateInput) : dateInput;
      if (isNaN(date.getTime())) return String(dateInput);
      const locale = INTL_LOCALE_MAP[language] || 'en-IN';
      return new Intl.DateTimeFormat(locale, options).format(date);
    } catch {
      return String(dateInput);
    }
  }, [language]);

  /**
   * Localize time using Intl.DateTimeFormat with current language locale
   */
  const formatTime = useCallback((dateInput, options = { hour: 'numeric', minute: 'numeric', hour12: true }) => {
    if (!dateInput) return '';
    try {
      const date = typeof dateInput === 'string' ? new Date(dateInput) : dateInput;
      if (isNaN(date.getTime())) return String(dateInput);
      const locale = INTL_LOCALE_MAP[language] || 'en-IN';
      return new Intl.DateTimeFormat(locale, options).format(date);
    } catch {
      return String(dateInput);
    }
  }, [language]);

  const value = useMemo(() => ({
    language,
    setLanguage,
    t,
    formatCondition,
    formatDate,
    formatTime,
    supportedLanguages: SUPPORTED_LANGUAGES,
  }), [language, setLanguage, t, formatCondition, formatDate, formatTime]);

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return ctx;
}
