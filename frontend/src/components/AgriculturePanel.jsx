import React, { useState } from "react";
import { fetchAdvisory } from "../api";
import {
  IconSprout,
  IconSpray,
  IconDroplet,
  IconWheat,
  IconTractor,
  IconDroplets,
  IconInfo,
} from "./Icons";
import { useLanguage } from "../i18n/LanguageContext";

const CROP_KEYS = [
  "rice",
  "wheat",
  "cotton",
  "tomato",
  "onion",
  "vegetables",
  "fruit crops",
  "general",
];

const STATUS_PILLS = {
  SAFE: {
    tKey: "statusSafe",
    defaultLabel: "Suitable",
    class: "bg-emerald-50 text-emerald-800 border-emerald-200",
  },
  FAVORABLE: {
    tKey: "statusFavorable",
    defaultLabel: "Favorable",
    class: "bg-emerald-50 text-emerald-800 border-emerald-200",
  },
  RECOMMENDED: {
    tKey: "statusSafe",
    defaultLabel: "Suitable",
    class: "bg-emerald-50 text-emerald-800 border-emerald-200",
  },
  CAUTION: {
    tKey: "statusCaution",
    defaultLabel: "Caution",
    class: "bg-amber-50 text-amber-800 border-amber-200",
  },
  POSTPONE: {
    tKey: "statusPostpone",
    defaultLabel: "Postpone",
    class: "bg-rose-50 text-rose-800 border-rose-200",
  },
  UNSAFE: {
    tKey: "statusUnsafe",
    defaultLabel: "Avoid",
    class: "bg-rose-50 text-rose-800 border-rose-200",
  },
  UNFAVORABLE: {
    tKey: "statusUnsafe",
    defaultLabel: "Unfavorable",
    class: "bg-rose-50 text-rose-800 border-rose-200",
  },
};

export default function AgriculturePanel({ location, language: propLang }) {
  const { language: ctxLang, t } = useLanguage();
  const currentLang = propLang || ctxLang;

  const [selectedCrop, setSelectedCrop] = useState("rice");
  const [advisoryResult, setAdvisoryResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const locName =
    typeof location === "object" && location !== null
      ? location.displayName || location.name || "Selected Location"
      : location || "Selected Location";

  const handleGetAdvisory = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetchAdvisory(location, selectedCrop, currentLang);
      setAdvisoryResult(res);
    } catch (err) {
      setError(err.message || "Could not fetch agricultural advisory.");
    } finally {
      setLoading(false);
    }
  };

  const getPill = (status) => {
    const s = String(status || "").toUpperCase();
    const config = STATUS_PILLS[s];
    if (config) {
      return {
        label: t(config.tKey, config.defaultLabel),
        class: config.class,
      };
    }
    return { label: status, class: "bg-stone-50 text-stone-700 border-stone-200" };
  };

  return (
    <div className="bg-white rounded-2xl border border-stone-200/90 p-5 sm:p-6 shadow-xs space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-stone-100">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-800 flex items-center justify-center shrink-0 border border-emerald-100">
            <IconSprout className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-base font-bold text-stone-900 tracking-tight">
              {t("farmConditions", "Farm Conditions & Operations")}
            </h4>
            <p className="text-xs text-stone-500">
              {t("agriThresholds", "Verified agronomic guidance for")}{" "}
              <span className="font-semibold text-stone-800">{locName}</span>
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={handleGetAdvisory}
          disabled={loading}
          className="self-start sm:self-auto bg-stone-900 hover:bg-stone-800 disabled:opacity-50 text-white font-medium text-xs px-3.5 py-2 rounded-xl transition-all shadow-xs flex items-center gap-1.5 cursor-pointer"
        >
          {loading ? (
            <>
              <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
              <span>{t("evaluatingAgri", "Analyzing conditions…")}</span>
            </>
          ) : (
            <>
              <IconTractor className="w-3.5 h-3.5" />
              <span>{t("getAdvisoryBtn", "Analyze Farming Conditions")}</span>
            </>
          )}
        </button>
      </div>

      {/* Crop Selector Pills */}
      <div>
        <label className="block text-xs font-semibold text-stone-700 mb-1.5">
          {t("cropLabel", "Select Crop")}:
        </label>
        <div className="flex flex-wrap gap-1.5">
          {CROP_KEYS.map((cropId) => {
            const cropLabel = t(`crops.${cropId}`, cropId.charAt(0).toUpperCase() + cropId.slice(1));
            const isSelected = selectedCrop === cropId;
            return (
              <button
                key={cropId}
                type="button"
                onClick={() => {
                  setSelectedCrop(cropId);
                  setAdvisoryResult(null);
                }}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                  isSelected
                    ? "bg-emerald-800 text-white shadow-xs font-semibold"
                    : "bg-stone-100/80 text-stone-600 hover:bg-stone-100 hover:text-stone-900"
                }`}
              >
                {cropLabel}
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="p-3 bg-rose-50 text-rose-800 text-xs rounded-xl border border-rose-200">
          {error}
        </div>
      )}

      {/* Operations Grid: Spraying, Irrigation, Sowing, Harvesting, Rainfall Outlook */}
      {advisoryResult?.operations && (
        <div className="space-y-3 pt-2">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {/* Spraying */}
            {advisoryResult.operations.spray && (
              <OperationCard
                title={t("opSpray", "Chemical Spraying")}
                icon={<IconSpray className="w-4 h-4 text-stone-700" />}
                data={advisoryResult.operations.spray}
                pill={getPill(advisoryResult.operations.spray.status)}
              />
            )}

            {/* Irrigation */}
            {advisoryResult.operations.irrigation && (
              <OperationCard
                title={t("opIrrigation", "Field Irrigation")}
                icon={<IconDroplet className="w-4 h-4 text-sky-700" />}
                data={advisoryResult.operations.irrigation}
                pill={getPill(advisoryResult.operations.irrigation.status)}
              />
            )}

            {/* Sowing */}
            {advisoryResult.operations.sowing && (
              <OperationCard
                title={t("opSowing", "Sowing & Field Prep")}
                icon={<IconSprout className="w-4 h-4 text-emerald-700" />}
                data={advisoryResult.operations.sowing}
                pill={getPill(advisoryResult.operations.sowing.status)}
              />
            )}

            {/* Harvesting */}
            {advisoryResult.operations.harvest && (
              <OperationCard
                title={t("opHarvest", "Crop Harvesting")}
                icon={<IconWheat className="w-4 h-4 text-amber-700" />}
                data={advisoryResult.operations.harvest}
                pill={getPill(advisoryResult.operations.harvest.status)}
              />
            )}
          </div>

          {/* Natural Language Synthesis Guidance */}
          {advisoryResult.answer && (
            <div className="p-3.5 rounded-xl bg-stone-50 border border-stone-200/60 text-xs text-stone-800 leading-relaxed space-y-1">
              <span className="font-bold text-stone-900 block">
                {t("detailedGuidance", "Agronomic Assessment:")}
              </span>
              <p className="whitespace-pre-wrap">{advisoryResult.answer}</p>
            </div>
          )}
        </div>
      )}

      {/* Verification Notice */}
      <div className="pt-2 border-t border-stone-100 flex items-center gap-1.5 text-[11px] text-stone-500">
        <IconInfo className="w-3.5 h-3.5 text-stone-400 shrink-0" />
        <span>
          {t(
            "agriDisclaimer",
            "Farm recommendations are evaluated deterministically in Python against verified weather conditions."
          )}
        </span>
      </div>
    </div>
  );
}

function OperationCard({ title, icon, data, pill }) {
  return (
    <div className="p-3.5 rounded-xl bg-stone-50/70 border border-stone-200/60 space-y-1.5">
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-xs font-bold text-stone-900">{title}</span>
        </div>
        <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${pill.class}`}>
          {pill.label}
        </span>
      </div>

      <p className="text-xs text-stone-700 font-medium leading-snug">
        {data.recommendation}
      </p>

      {data.reasons?.[0] && (
        <p className="text-[11px] text-stone-500 pt-1 border-t border-stone-200/40">
          {data.reasons[0]}
        </p>
      )}
    </div>
  );
}
