import React from "react";
import {
  WeatherConditionIcon,
  IconDroplet,
  IconDroplets,
  IconWind,
  IconThermometer,
  IconShieldCheck,
  IconCompass,
} from "./Icons";
import { useLanguage } from "../i18n/LanguageContext";

export default function WeatherHero({ weather }) {
  const { t, formatCondition } = useLanguage();

  if (!weather || !weather.current) return null;
  const { current, forecast = [], location, source } = weather;
  const today = forecast[0] || {};
  const localizedCondition = formatCondition(current.condition);

  const rainChance = today.rain_probability ?? 0;
  const highTemp = today.temp_max != null ? Math.round(today.temp_max) : Math.round(current.temperature_c);
  const lowTemp = today.temp_min != null ? Math.round(today.temp_min) : Math.round(current.temperature_c - 4);

  return (
    <div className="bg-white rounded-2xl border border-stone-200/90 p-5 sm:p-7 shadow-xs">
      {/* Top Tag & Source Row */}
      <div className="flex items-center justify-between gap-2 pb-4 mb-4 border-b border-stone-100">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-600 animate-pulse"></span>
          <span className="text-xs font-bold uppercase tracking-wider text-emerald-800 bg-emerald-50 px-2.5 py-0.5 rounded-md border border-emerald-200/60">
            {t("liveWeather", "Current Weather")}
          </span>
          <span className="text-xs text-stone-500 font-medium hidden sm:inline">
            {t("verifiedStation", "Verified Station Data")}
          </span>
        </div>

        <div className="flex items-center gap-1.5 text-[11px] text-stone-500 font-medium">
          <IconShieldCheck className="w-3.5 h-3.5 text-emerald-700 shrink-0" />
          <span>{source || "IMD + Open-Meteo"}</span>
        </div>
      </div>

      {/* Main Temperature & Condition Display */}
      <div className="grid grid-cols-1 sm:grid-cols-12 gap-6 items-center">
        {/* Left / Main Temp (7 cols) */}
        <div className="sm:col-span-7 space-y-2">
          <div className="flex items-baseline gap-4">
            <span className="font-serif text-5xl sm:text-6xl font-bold tracking-tight text-stone-900 leading-none">
              {Math.round(current.temperature_c)}°C
            </span>
            <div className="flex items-center gap-1 text-xs text-stone-500 font-medium">
              <span>{t('highLabel', 'H')}: <strong className="text-stone-800">{highTemp}°</strong></span>
              <span className="text-stone-300">•</span>
              <span>{t('lowLabel', 'L')}: <strong className="text-stone-800">{lowTemp}°</strong></span>
            </div>
          </div>

          <div className="flex items-center gap-2.5 pt-1">
            <div className="w-9 h-9 rounded-xl bg-stone-100 flex items-center justify-center text-stone-800 shrink-0">
              <WeatherConditionIcon
                condition={current.condition}
                code={current.weather_code}
                className="w-6 h-6 text-stone-800"
              />
            </div>
            <div>
              <p className="text-base sm:text-lg font-semibold text-stone-900 leading-tight">
                {localizedCondition}
              </p>
              <p className="text-xs text-stone-500 mt-0.5">
                {t("feelsLike", "Feels like")} <span className="font-semibold text-stone-700">{Math.round(current.feels_like_c)}°C</span>
              </p>
            </div>
          </div>
        </div>

        {/* Right / Quick Metrics Grid (5 cols) */}
        <div className="sm:col-span-5 grid grid-cols-3 sm:grid-cols-1 gap-2 sm:gap-2.5">
          {/* Rain Chance */}
          <div className="flex items-center gap-3 p-2.5 rounded-xl bg-stone-50/80 border border-stone-200/50">
            <div className="w-7 h-7 rounded-lg bg-emerald-100/70 text-emerald-800 flex items-center justify-center shrink-0">
              <IconDroplets className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-wider text-stone-500 font-semibold truncate">
                {t("rainChance", "Rain")}
              </p>
              <p className="text-xs sm:text-sm font-bold text-stone-900">
                {rainChance}%
              </p>
            </div>
          </div>

          {/* Humidity */}
          <div className="flex items-center gap-3 p-2.5 rounded-xl bg-stone-50/80 border border-stone-200/50">
            <div className="w-7 h-7 rounded-lg bg-sky-100/70 text-sky-800 flex items-center justify-center shrink-0">
              <IconDroplet className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-wider text-stone-500 font-semibold truncate">
                {t("humidity", "Humidity")}
              </p>
              <p className="text-xs sm:text-sm font-bold text-stone-900">
                {current.humidity_pct}%
              </p>
            </div>
          </div>

          {/* Wind */}
          <div className="flex items-center gap-3 p-2.5 rounded-xl bg-stone-50/80 border border-stone-200/50">
            <div className="w-7 h-7 rounded-lg bg-stone-200/70 text-stone-800 flex items-center justify-center shrink-0">
              <IconWind className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-wider text-stone-500 font-semibold truncate">
                {t("wind", "Wind")}
              </p>
              <p className="text-xs sm:text-sm font-bold text-stone-900">
                {Math.round(current.wind_kmh)} km/h
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
