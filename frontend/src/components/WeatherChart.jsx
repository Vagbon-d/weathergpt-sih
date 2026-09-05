import React, { useState } from "react";
import { IconTrendingUp, IconDroplets, IconThermometer } from "./Icons";
import { useLanguage } from "../i18n/LanguageContext";

export default function WeatherChart({ hourly = [] }) {
  const { t, formatTime, formatCondition } = useLanguage();
  const [metric, setMetric] = useState("temp"); // "temp" | "rain"
  const [hoveredIndex, setHoveredIndex] = useState(null);

  if (!hourly || hourly.length === 0) return null;

  // Take the next 24 hours
  const data = hourly.slice(0, 24);
  if (data.length < 2) return null;

  const values = data.map((h) =>
    metric === "temp" ? Math.round(h.temperature_c ?? 25) : Math.round(h.rain_probability ?? 0)
  );

  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const padding = metric === "temp" ? 2 : 5;
  const chartMin = Math.max(0, minVal - padding);
  const chartMax = maxVal + padding === chartMin ? chartMin + 10 : maxVal + padding;
  const valRange = chartMax - chartMin || 1;

  // SVG dimensions
  const svgWidth = 720;
  const svgHeight = 160;
  const margin = { top: 20, right: 20, bottom: 30, left: 36 };
  const innerWidth = svgWidth - margin.left - margin.right;
  const innerHeight = svgHeight - margin.top - margin.bottom;

  // Calculate points
  const points = data.map((d, i) => {
    const x = margin.left + (i / (data.length - 1)) * innerWidth;
    const val = metric === "temp" ? Math.round(d.temperature_c ?? 25) : Math.round(d.rain_probability ?? 0);
    const y = margin.top + innerHeight - ((val - chartMin) / valRange) * innerHeight;
    return { x, y, val, item: d, index: i };
  });

  // Generate SVG path for smooth line
  const linePath = points.reduce((acc, p, i, arr) => {
    if (i === 0) return `M ${p.x},${p.y}`;
    const prev = arr[i - 1];
    const cpx1 = prev.x + (p.x - prev.x) / 2;
    const cpy1 = prev.y;
    const cpx2 = prev.x + (p.x - prev.x) / 2;
    const cpy2 = p.y;
    return `${acc} C ${cpx1},${cpy1} ${cpx2},${cpy2} ${p.x},${p.y}`;
  }, "");

  // Area path
  const areaPath = `${linePath} L ${points[points.length - 1].x},${margin.top + innerHeight} L ${points[0].x},${margin.top + innerHeight} Z`;

  // Selected or hovered point
  const activePoint = hoveredIndex !== null ? points[hoveredIndex] : points[0];

  const strokeColor = metric === "temp" ? "#C68B59" : "#266D3E";
  const fillColor = metric === "temp" ? "#FDF6EE" : "#EBF4ED";

  return (
    <div className="bg-white rounded-2xl border border-stone-200/90 p-4 sm:p-5 shadow-xs">
      {/* Header with Metric Toggle */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-stone-100 flex items-center justify-center text-stone-700">
            <IconTrendingUp className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-stone-900 tracking-tight">
              {t("weatherTrend", "24-Hour Weather Trend")}
            </h4>
            <p className="text-[11px] text-stone-500">
              {metric === "temp"
                ? t("tempTrendDesc", "Hourly temperature curve across day & night")
                : t("rainTrendDesc", "Hourly rainfall probability distribution")}
            </p>
          </div>
        </div>

        {/* Pill selector */}
        <div className="inline-flex rounded-lg bg-stone-100 p-0.5 self-start sm:self-auto border border-stone-200/60">
          <button
            type="button"
            onClick={() => setMetric("temp")}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-all ${
              metric === "temp"
                ? "bg-white text-stone-900 shadow-xs font-semibold"
                : "text-stone-600 hover:text-stone-900"
            }`}
          >
            <IconThermometer className="w-3.5 h-3.5 text-amber-700" />
            <span>{t("temperature", "Temperature")}</span>
          </button>
          <button
            type="button"
            onClick={() => setMetric("rain")}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-all ${
              metric === "rain"
                ? "bg-white text-stone-900 shadow-xs font-semibold"
                : "text-stone-600 hover:text-stone-900"
            }`}
          >
            <IconDroplets className="w-3.5 h-3.5 text-emerald-700" />
            <span>{t("rainChance", "Rain Probability")}</span>
          </button>
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="relative">
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full h-36 sm:h-44 overflow-visible"
        >
          <defs>
            <linearGradient id={`chart-grad-${metric}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={strokeColor} stopOpacity="0.25" />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line
            x1={margin.left}
            y1={margin.top}
            x2={margin.left + innerWidth}
            y2={margin.top}
            stroke="#E5E0D8"
            strokeDasharray="3 3"
            strokeWidth="0.8"
          />
          <line
            x1={margin.left}
            y1={margin.top + innerHeight / 2}
            x2={margin.left + innerWidth}
            y2={margin.top + innerHeight / 2}
            stroke="#E5E0D8"
            strokeDasharray="3 3"
            strokeWidth="0.8"
          />
          <line
            x1={margin.left}
            y1={margin.top + innerHeight}
            x2={margin.left + innerWidth}
            y2={margin.top + innerHeight}
            stroke="#E5E0D8"
            strokeWidth="1"
          />

          {/* Y-axis Labels */}
          <text
            x={margin.left - 8}
            y={margin.top + 4}
            fontSize="10"
            fill="#8C827A"
            textAnchor="end"
            fontFamily="sans-serif"
          >
            {chartMax}{metric === "temp" ? "°" : "%"}
          </text>
          <text
            x={margin.left - 8}
            y={margin.top + innerHeight / 2 + 4}
            fontSize="10"
            fill="#8C827A"
            textAnchor="end"
            fontFamily="sans-serif"
          >
            {Math.round(chartMin + valRange / 2)}{metric === "temp" ? "°" : "%"}
          </text>
          <text
            x={margin.left - 8}
            y={margin.top + innerHeight}
            fontSize="10"
            fill="#8C827A"
            textAnchor="end"
            fontFamily="sans-serif"
          >
            {chartMin}{metric === "temp" ? "°" : "%"}
          </text>

          {/* Area & Line */}
          <path d={areaPath} fill={`url(#chart-grad-${metric})`} />
          <path
            d={linePath}
            fill="none"
            stroke={strokeColor}
            strokeWidth="2.2"
            strokeLinecap="round"
          />

          {/* Points & Interactive Nodes */}
          {points.map((p, idx) => {
            const isHovered = hoveredIndex === idx;
            // Only draw circles on every 3rd point or hovered
            const showPoint = isHovered || idx % 3 === 0 || idx === points.length - 1;

            return (
              <g key={idx}>
                {showPoint && (
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r={isHovered ? 5 : 3}
                    fill="#FFFFFF"
                    stroke={strokeColor}
                    strokeWidth={isHovered ? 2.5 : 1.75}
                    className="transition-all duration-150"
                  />
                )}
                {/* Invisible wider hit area for touch/mouse */}
                <rect
                  x={p.x - innerWidth / (data.length * 2)}
                  y={margin.top}
                  width={innerWidth / data.length}
                  height={innerHeight + margin.bottom}
                  fill="transparent"
                  className="cursor-pointer"
                  onMouseEnter={() => setHoveredIndex(idx)}
                  onMouseLeave={() => setHoveredIndex(null)}
                />
              </g>
            );
          })}

          {/* X-axis Time Labels */}
          {points
            .filter((_, idx) => idx % 4 === 0 || idx === points.length - 1)
            .map((p, idx) => {
              const label = formatTime(p.item.time, { hour: "numeric", hour12: true });
              return (
                <text
                  key={idx}
                  x={p.x}
                  y={margin.top + innerHeight + 16}
                  fontSize="10"
                  fill="#78716C"
                  textAnchor="middle"
                  fontFamily="sans-serif"
                  fontWeight="500"
                >
                  {label}
                </text>
              );
            })}
        </svg>

        {/* Tooltip / Active Point Summary */}
        {activePoint && (
          <div className="mt-2.5 pt-2.5 border-t border-stone-100 flex items-center justify-between text-xs text-stone-600">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-stone-900">
                {formatTime(activePoint.item.time, { hour: "numeric", minute: "numeric", hour12: true })}:
              </span>
              <span>{formatCondition(activePoint.item.condition)}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="font-bold text-stone-900">
                {Math.round(activePoint.item.temperature_c)}°C
              </span>
              <span className="text-emerald-700 font-medium">
                {activePoint.item.rain_probability}% {t("rain", "rain")}
              </span>
              <span className="text-stone-500 text-[11px]">
                {Math.round(activePoint.item.wind_kmh)} km/h
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
