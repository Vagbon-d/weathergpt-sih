import React, { useState } from "react";
import { WeatherConditionIcon, IconDroplets, IconCalendar, IconClock } from "./Icons";
import { useLanguage } from "../i18n/LanguageContext";

export default function ForecastStrip({ forecast = [], hourly = [] }) {
  const [activeTab, setActiveTab] = useState("daily"); // "daily" | "hourly"
  const { t, formatCondition, formatDate, formatTime } = useLanguage();

  if (!forecast?.length && !hourly?.length) return null;

  return (
    <div className="bg-white rounded-2xl border border-stone-200/90 p-4 sm:p-5 shadow-xs">
      {/* Header with View Toggle */}
      <div className="flex items-center justify-between gap-3 pb-3 mb-3 border-b border-stone-100">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setActiveTab("daily")}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
              activeTab === "daily"
                ? "bg-stone-900 text-white shadow-xs"
                : "text-stone-600 hover:text-stone-900 bg-stone-100"
            }`}
          >
            <IconCalendar className="w-3.5 h-3.5" />
            <span>{t("forecast", "7-Day Forecast")}</span>
          </button>
          {hourly?.length > 0 && (
            <button
              type="button"
              onClick={() => setActiveTab("hourly")}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                activeTab === "hourly"
                  ? "bg-stone-900 text-white shadow-xs"
                  : "text-stone-600 hover:text-stone-900 bg-stone-100"
              }`}
            >
              <IconClock className="w-3.5 h-3.5" />
              <span>{t("hourlyForecast", "24-Hour Forecast")}</span>
            </button>
          )}
        </div>

        <span className="text-[11px] text-stone-500 font-medium hidden sm:inline">
          {activeTab === "daily" ? t("highResModel", "7-Day Meteorological Outlook") : t("next24Hours", "Next 24 Hours")}
        </span>
      </div>

      {/* Daily 7-Day View */}
      {activeTab === "daily" ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
          {forecast.slice(0, 7).map((day, idx) => {
            const weekday =
              idx === 0
                ? t("today", "Today")
                : idx === 1
                ? t("tomorrow", "Tomorrow")
                : formatDate(day.date, { weekday: "short" });

            const dateFormatted = formatDate(day.date, {
              month: "short",
              day: "numeric",
            });
            const localizedCond = formatCondition(day.condition);

            return (
              <div
                key={day.date || idx}
                className="p-3 rounded-xl bg-stone-50/60 hover:bg-stone-50 border border-stone-200/60 flex flex-col justify-between transition-colors min-h-[135px]"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-stone-900">{weekday}</span>
                    <span className="text-[10px] text-stone-500 font-medium">{dateFormatted}</span>
                  </div>

                  <div className="flex flex-col items-center my-2">
                    <WeatherConditionIcon
                      condition={day.condition}
                      code={day.weather_code}
                      className="w-7 h-7 text-stone-800"
                    />
                    <p
                      className="text-[11px] font-medium text-stone-700 mt-1 text-center line-clamp-1"
                      title={localizedCond}
                    >
                      {localizedCond}
                    </p>
                  </div>
                </div>

                <div className="pt-2 border-t border-stone-200/60 flex items-center justify-between text-xs">
                  <div>
                    <span className="font-bold text-stone-900">
                      {Math.round(day.temp_max)}°
                    </span>
                    <span className="text-stone-500 text-[10px] ml-0.5">
                      /{Math.round(day.temp_min)}°
                    </span>
                  </div>
                  <div className="flex items-center gap-0.5 text-[10px] text-emerald-800 font-semibold bg-emerald-100/70 px-1.5 py-0.5 rounded">
                    <IconDroplets className="w-2.5 h-2.5" />
                    <span>{day.rain_probability ?? 0}%</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Hourly 24-Hour View */
        <div className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-thin">
          {hourly.slice(0, 24).map((h, i) => {
            const timeLabel = formatTime(h.time, {
              hour: "numeric",
              hour12: true,
            });
            const localizedCond = formatCondition(h.condition);

            return (
              <div
                key={h.time || i}
                className="shrink-0 bg-stone-50/80 border border-stone-200/60 rounded-xl p-2.5 text-center min-w-[85px] flex flex-col justify-between"
              >
                <div className="text-[11px] font-bold text-stone-900">{timeLabel}</div>
                <div className="my-1 flex justify-center">
                  <WeatherConditionIcon
                    condition={h.condition}
                    code={h.weather_code}
                    className="w-6 h-6 text-stone-800"
                  />
                </div>
                <div className="text-xs font-bold text-stone-900">{Math.round(h.temperature_c)}°C</div>
                <div className="text-[10px] text-emerald-800 font-semibold mt-0.5 flex items-center justify-center gap-0.5">
                  <IconDroplets className="w-2.5 h-2.5" />
                  <span>{h.rain_probability ?? 0}%</span>
                </div>
                <div className="text-[9px] text-stone-500 mt-0.5">{Math.round(h.wind_kmh)} km/h</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
