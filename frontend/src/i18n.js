// WeatherGPT (SIH26068) i18n Bridge
// Re-exports 11 Indian languages, LanguageContext, and translation dictionaries.

export {
  SUPPORTED_LANGUAGES,
  SUPPORTED_LANGUAGES as LANGUAGES,
  LanguageProvider,
  useLanguage,
} from './i18n/LanguageContext';

export { translateCondition } from './i18n/conditions';

export const SPEECH_LOCALE = {
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
