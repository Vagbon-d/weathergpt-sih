import React, { useState, useRef } from "react";
import { IconSparkles, IconSprout, IconSun, IconUser } from "./Icons";
import { useLanguage } from "../i18n/LanguageContext";

export default function QuickSuggestions({ onPick, disabled = false }) {
  const [activeTab, setActiveTab] = useState("all");
  const { t } = useLanguage();
  const isClickingRef = useRef(false);

  const handlePick = (c) => {
    if (disabled || isClickingRef.current) return;
    isClickingRef.current = true;
    onPick(c);
    setTimeout(() => {
      isClickingRef.current = false;
    }, 400);
  };

  const suggestions = {
    weather: [
      t("quickWeather", "Weather today"),
      t("quickRain", "Will it rain tomorrow?"),
      t("quickCompare", "Is tomorrow hotter than today?"),
      t("quickWeekend", "What will the weather be this weekend?"),
    ],
    farming: [
      t("quickFarmer", "Should I spray pesticides tomorrow?"),
      t("quickIrrigate", "Should I irrigate the crops today?"),
      t("quickHarvest", "Is the weather safe for harvesting?"),
    ],
    daily: [
      t("quickPicnic", "Is tomorrow good for outdoor work?"),
      t("quickAlerts", "Are there any weather alerts?"),
    ],
  };

  const allChips = [
    t("quickWeather", "Weather today"),
    t("quickRain", "Will it rain tomorrow?"),
    t("quickFarmer", "Should I spray pesticides tomorrow?"),
    t("quickIrrigate", "Should I irrigate the crops today?"),
    t("quickHarvest", "Is the weather safe for harvesting?"),
    t("quickCompare", "Is tomorrow hotter than today?"),
    t("quickAlerts", "Are there any weather alerts?"),
    t("quickWeekend", "What will the weather be this weekend?"),
  ];

  const activeChips = activeTab === "all" ? allChips : suggestions[activeTab] || allChips;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-stone-600">
            <IconSparkles className="w-3.5 h-3.5 text-amber-700" />
            <span>{t("suggestions", "Suggested Inquiries")}</span>
          </div>

          <div className="inline-flex rounded-lg bg-stone-100 p-0.5 border border-stone-200/60 text-[10px]">
            <button
              type="button"
              onClick={() => setActiveTab("all")}
              className={`px-2 py-0.5 rounded-md transition-all ${
                activeTab === "all" ? "bg-white shadow-xs font-bold text-stone-900" : "text-stone-600 hover:text-stone-900"
              }`}
            >
              {t("tabAll", "All")}
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("farming")}
              className={`flex items-center gap-1 px-2 py-0.5 rounded-md transition-all ${
                activeTab === "farming" ? "bg-white shadow-xs font-bold text-emerald-800" : "text-stone-600 hover:text-stone-900"
              }`}
            >
              <IconSprout className="w-2.5 h-2.5" />
              <span>{t("tabFarming", "Farming")}</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("weather")}
              className={`flex items-center gap-1 px-2 py-0.5 rounded-md transition-all ${
                activeTab === "weather" ? "bg-white shadow-xs font-bold text-amber-800" : "text-stone-600 hover:text-stone-900"
              }`}
            >
              <IconSun className="w-2.5 h-2.5" />
              <span>{t("tabWeather", "Weather")}</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("daily")}
              className={`flex items-center gap-1 px-2 py-0.5 rounded-md transition-all ${
                activeTab === "daily" ? "bg-white shadow-xs font-bold text-stone-900" : "text-stone-600 hover:text-stone-900"
              }`}
            >
              <IconUser className="w-2.5 h-2.5" />
              <span>{t("tabLife", "Activities")}</span>
            </button>
          </div>
        </div>
      </div>

      <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-thin">
        {activeChips.map((c, i) => (
          <button
            key={i}
            type="button"
            disabled={disabled}
            onClick={() => handlePick(c)}
            className="whitespace-nowrap text-xs bg-white hover:bg-stone-900 hover:text-white border border-stone-200 text-stone-700 font-medium px-3 py-1.5 rounded-full transition-all shadow-xs disabled:opacity-50 disabled:pointer-events-none active:scale-95 cursor-pointer"
          >
            {c}
          </button>
        ))}
      </div>
    </div>
  );
}
