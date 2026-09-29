/**
 * HelplineBanner.jsx — Persistent, slim helpline invitation banner.
 *
 * Design contract (must not be violated):
 *   - Visually consistent with the existing WeatherGPT panel set:
 *     same bg-white / border-stone-200 / rounded-2xl / shadow-xs treatment,
 *     same stone/green colour palette.
 *   - No new gradients or heavy animations beyond what already exists in the app.
 *   - The displayed number comes from VITE_HELPLINE_NUMBER (import.meta.env)
 *     so it is NEVER hard-coded across multiple source files.
 *   - Dismissible for the current session (sessionStorage). Re-appears on refresh
 *     if the user didn't explicitly dismiss it.
 *   - Mobile-first: single-column stacking on small screens, row on md+.
 *   - Accessibility: role="banner", aria-label, tel: link with descriptive text.
 *
 * Where it is rendered:
 *   App.jsx — top of <main>, above the 12-col grid, always visible regardless
 *   of whether a location has been selected.
 */

import React, { useState } from 'react';
import { IconPhone } from './Icons';

const DISMISS_KEY = 'weathergpt_helpline_dismissed';

// Read from Vite env; fall back to a generic placeholder that is still
// recognisable as a placeholder, never a wrong real number.
const RAW_NUMBER = import.meta.env.VITE_HELPLINE_NUMBER || '';

/** Format E.164 (+917447651611) for display: +91 74476 51611 */
function formatForDisplay(num) {
  if (!num) return 'our helpline';
  // Strip leading + if present, then format Indian numbers nicely
  const digits = num.replace(/^\+/, '');
  if (digits.startsWith('91') && digits.length === 12) {
    return `+91 ${digits.slice(2, 7)} ${digits.slice(7)}`;
  }
  return num;
}

const DISPLAY_NUMBER = formatForDisplay(RAW_NUMBER);
const TEL_HREF = RAW_NUMBER ? `tel:${RAW_NUMBER}` : '#';

export default function HelplineBanner() {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return sessionStorage.getItem(DISMISS_KEY) === '1';
    } catch {
      return false;
    }
  });

  if (dismissed) return null;

  const handleDismiss = () => {
    try {
      sessionStorage.setItem(DISMISS_KEY, '1');
    } catch {
      // ignore storage errors
    }
    setDismissed(true);
  };

  return (
    <div
      role="banner"
      aria-label="WeatherGPT Helpline"
      className="mb-5 bg-white border border-stone-200 rounded-2xl shadow-xs px-4 py-3 flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-4"
    >
      {/* Icon */}
      <div
        className="w-9 h-9 rounded-xl bg-[#1E5631]/10 text-[#1E5631] flex items-center justify-center shrink-0"
        aria-hidden="true"
      >
        <IconPhone className="w-4 h-4" />
      </div>

      {/* Text */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-[#1C2024] leading-snug">
          No internet in the field?{' '}
          <a
            href={TEL_HREF}
            className="text-[#1E5631] underline underline-offset-2 hover:text-[#174426] transition-colors font-bold"
            aria-label={`Call WeatherGPT helpline at ${DISPLAY_NUMBER}`}
          >
            {DISPLAY_NUMBER}
          </a>
          {' '}— call and speak in your language.
        </p>
        <p className="text-xs text-stone-500 mt-0.5 leading-relaxed">
          Ask any weather or farming question. You'll receive an SMS advisory in your language — works on basic feature phones too.
        </p>
      </div>

      {/* Dismiss button */}
      <button
        type="button"
        onClick={handleDismiss}
        aria-label="Dismiss helpline banner"
        className="shrink-0 text-[11px] font-medium text-stone-400 hover:text-stone-600 bg-stone-100 hover:bg-stone-200 px-2.5 py-1 rounded-lg transition-colors cursor-pointer self-start sm:self-center"
      >
        Dismiss
      </button>
    </div>
  );
}
