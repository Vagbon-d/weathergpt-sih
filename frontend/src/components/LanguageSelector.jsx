import React from 'react';
import { useLanguage } from '../i18n/LanguageContext';
import { IconGlobe, IconChevronDown } from './Icons';

export default function LanguageSelector({ language: propLanguage, onChange: propOnChange, variant = 'nav' }) {
  const { language: ctxLanguage, setLanguage: ctxSetLanguage, supportedLanguages } = useLanguage();
  const currentLang = propLanguage || ctxLanguage;
  const handleChange = (e) => {
    const val = e.target.value;
    if (propOnChange) propOnChange(val);
    if (ctxSetLanguage) ctxSetLanguage(val);
  };

  return (
    <div className="relative inline-flex items-center">
      <IconGlobe className="w-3.5 h-3.5 absolute left-2.5 pointer-events-none text-stone-500" />
      <select
        value={currentLang}
        onChange={handleChange}
        className="appearance-none bg-white text-stone-800 font-medium text-xs sm:text-sm pl-8 pr-7 py-1.5 rounded-full border border-stone-200 shadow-2xs outline-none cursor-pointer transition-all hover:border-stone-300 focus:ring-2 focus:ring-[#1E5631]/20 focus:border-[#1E5631]"
        aria-label="Select Language"
      >
        {supportedLanguages.map((l) => (
          <option key={l.code} value={l.code} className="text-stone-900 bg-white">
            {l.nativeName} ({l.name})
          </option>
        ))}
      </select>
      <IconChevronDown className="w-3 h-3 absolute right-2.5 pointer-events-none text-stone-500" />
    </div>
  );
}
