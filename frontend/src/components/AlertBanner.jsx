import React from "react";
import { IconShieldAlert, IconShieldCheck, IconClock, IconInfo } from "./Icons";
import { useLanguage } from "../i18n/LanguageContext";

const SEVERITY_LEVELS = {
  GREEN: {
    label: "Normal",
    tKey: "severityNormal",
    badge: "bg-emerald-50 text-emerald-800 border-emerald-200",
    border: "border-emerald-200/80",
    bg: "bg-emerald-50/40",
  },
  YELLOW: {
    label: "Watch",
    tKey: "severityWatch",
    badge: "bg-amber-50 text-amber-800 border-amber-200",
    border: "border-amber-200/80",
    bg: "bg-amber-50/40",
  },
  ORANGE: {
    label: "Warning",
    tKey: "severityWarning",
    badge: "bg-orange-50 text-orange-800 border-orange-200",
    border: "border-orange-200/80",
    bg: "bg-orange-50/40",
  },
  RED: {
    label: "Severe",
    tKey: "severitySevere",
    badge: "bg-rose-50 text-rose-800 border-rose-200",
    border: "border-rose-200/80",
    bg: "bg-rose-50/40",
  },
};

export default function AlertBanner({ alerts = [], location }) {
  const { t } = useLanguage();

  if (!alerts || alerts.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-stone-200/90 p-4 sm:p-5 shadow-xs">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center shrink-0 border border-emerald-100">
              <IconShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-bold text-stone-900">
                  {t("alerts", "Weather Alerts & Advisories")}
                </h4>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full border bg-emerald-50 text-emerald-800 border-emerald-200">
                  {t("severityNormal", "Normal")}
                </span>
              </div>
              <p className="text-xs text-stone-500 mt-0.5">
                {t("noAlerts", "No active severe weather warnings for this location.")}
              </p>
            </div>
          </div>
          <span className="text-[11px] text-stone-500 font-medium hidden sm:inline">
            {t("imdAuthority", "IMD Verified")}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-stone-200/90 p-4 sm:p-5 shadow-xs space-y-3">
      <div className="flex items-center justify-between pb-2.5 border-b border-stone-100">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-700 flex items-center justify-center shrink-0 border border-amber-100">
            <IconShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-stone-900">
              {t("alerts", "Weather Alerts & Advisories")}
            </h4>
            <p className="text-[11px] text-stone-500">
              {t("alertSubtitle", "Official meteorological risk alerts and protective guidance")}
            </p>
          </div>
        </div>

        <span className="text-[11px] text-stone-500 font-medium hidden sm:inline">
          {t("imdAuthority", "IMD Verified")}
        </span>
      </div>

      <div className="space-y-2.5">
        {alerts.map((a, idx) => {
          const sevKey = (a.severity || "YELLOW").toUpperCase();
          const sev = SEVERITY_LEVELS[sevKey] || SEVERITY_LEVELS.YELLOW;
          const isOfficial = a.is_official === true;

          return (
            <div
              key={a.id || idx}
              className={`p-3.5 sm:p-4 rounded-xl border ${sev.border} ${sev.bg} space-y-2 transition-colors`}
            >
              {/* Top Hazard & Severity Row */}
              <div className="flex items-start justify-between gap-2">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-bold text-stone-900">
                      {a.hazard || t("officialWarning", "Severe Weather Advisory")}
                    </span>
                    <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${sev.badge}`}>
                      {t(sev.tKey, sev.label)}
                    </span>
                    {!isOfficial && (
                      <span className="text-[10px] bg-stone-100 text-stone-700 font-bold px-2 py-0.5 rounded border border-stone-300">
                        {t("simulationBadge", "SIMULATION")}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-stone-500 font-medium">
                    {a.location || location}
                  </p>
                </div>

                <div className="flex items-center gap-1 text-[11px] text-stone-500 font-medium shrink-0">
                  <IconClock className="w-3.5 h-3.5 text-stone-400" />
                  <span>{a.valid_for || t("valid24h", "Valid: Next 24 hours")}</span>
                </div>
              </div>

              {/* Message */}
              <p className="text-xs sm:text-sm text-stone-800 font-medium leading-relaxed">
                {a.message}
              </p>

              {/* What you should know */}
              <div className="pt-2 border-t border-stone-200/50 flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-[11px] text-stone-600">
                <div className="flex items-center gap-1.5 font-medium text-stone-800">
                  <IconInfo className="w-3.5 h-3.5 text-stone-500 shrink-0" />
                  <span>
                    <strong>{t("whatYouShouldKnow", "What you should know:")}</strong>{" "}
                    {a.advisory || t("generalSafetyGuidance", "Avoid spraying pesticides in rain; protect field drainage.")}
                  </span>
                </div>
                <span className="text-stone-400 text-[10px] shrink-0">
                  {a.source || (isOfficial ? "IMD Official" : "IMD Verified Simulation")}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
