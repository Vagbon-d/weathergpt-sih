import React from 'react';
import { useLanguage } from '../i18n/LanguageContext';
import {
  IconUmbrella,
  IconSpray,
  IconDroplets,
  IconSun,
  IconWind,
  IconThermometer,
  IconSparkles,
  IconCheckCircle,
} from './Icons';

const ACTION_I18N_MAP = {
  umbrella_yes: { titleKey: 'actUmbrellaTitle', descKey: 'actUmbrellaDesc' },
  umbrella_no: { titleKey: 'actNoUmbrellaTitle', descKey: 'actNoUmbrellaDesc' },
  spray_ok: { titleKey: 'actSprayOkTitle', descKey: 'actSprayOkDesc' },
  spray_delay: { titleKey: 'actSprayDelayTitle', descKey: 'actSprayDelayDesc' },
  irrigation_ok: { titleKey: 'actIrrigateOkTitle', descKey: 'actIrrigateOkDesc' },
  irrigation_delay: { titleKey: 'actIrrigateDelayTitle', descKey: 'actIrrigateDelayDesc' },
  outdoor_good: { titleKey: 'actOutdoorTitle', descKey: 'actOutdoorDesc' },
  outdoor_morning: { titleKey: 'actOutdoorEarlyTitle', descKey: 'actOutdoorEarlyDesc' },
  drying_ok: { titleKey: 'actDryingOkTitle', descKey: 'actDryingOkDesc' },
  drying_cover: { titleKey: 'actDryingCoverTitle', descKey: 'actDryingCoverDesc' },
  heat_caution: { titleKey: 'actHeatCautionTitle', descKey: 'actHeatCautionDesc' },
};

function getActionIcon(id, className = 'w-4 h-4') {
  if (id.startsWith('umbrella')) return <IconUmbrella className={className} />;
  if (id.startsWith('spray')) return <IconSpray className={className} />;
  if (id.startsWith('irrigation')) return <IconDroplets className={className} />;
  if (id.startsWith('outdoor')) return <IconSun className={className} />;
  if (id.startsWith('drying')) return <IconWind className={className} />;
  if (id.startsWith('heat')) return <IconThermometer className={className} />;
  return <IconCheckCircle className={className} />;
}

export default function ActionRecommendations({ actions = [], onActionClick }) {
  const { t } = useLanguage();

  if (!actions || actions.length === 0) return null;

  const getStatusLabel = (status) => {
    const s = String(status || '').toUpperCase();
    if (s === 'SAFE') return t('statusSafe', 'SAFE');
    if (s === 'FAVORABLE') return t('statusFavorable', 'FAVORABLE');
    if (s === 'CAUTION') return t('statusCaution', 'CAUTION');
    if (s === 'POSTPONE') return t('statusPostpone', 'POSTPONE');
    if (s === 'UNSAFE') return t('statusUnsafe', 'UNSAFE');
    return status;
  };

  return (
    <div className="bg-white rounded-2xl p-5 border border-stone-200/90 shadow-xs">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-stone-100 flex items-center justify-center text-stone-700">
            <IconSparkles className="w-4 h-4 text-[#1E5631]" />
          </div>
          <h3 className="text-sm sm:text-base font-semibold text-[#1C2024]">
            {t('whatShouldIDoToday', 'What should I do today?')}
          </h3>
        </div>
        <span className="text-[11px] font-medium text-stone-600 bg-stone-100 px-2.5 py-0.5 rounded-full border border-stone-200">
          {t('liveDecisionAids', 'Live Decision Aids')}
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {actions.map((act) => {
          const isSafe = act.status === 'SAFE' || act.status === 'FAVORABLE';
          const mapping = ACTION_I18N_MAP[act.id];
          const title = mapping ? t(mapping.titleKey, act.title) : act.title;
          const desc = mapping ? t(mapping.descKey, act.desc) : act.desc;

          return (
            <div
              key={act.id}
              onClick={() => onActionClick && onActionClick(title)}
              className={`p-3.5 rounded-xl border transition-all cursor-pointer hover:shadow-xs ${
                isSafe
                  ? 'bg-emerald-50/40 border-emerald-200/70 hover:border-emerald-300'
                  : 'bg-amber-50/40 border-amber-200/70 hover:border-amber-300'
              }`}
            >
              <div className="flex items-start gap-3">
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${
                    isSafe ? 'bg-emerald-100/70 text-emerald-800' : 'bg-amber-100/70 text-amber-800'
                  }`}
                >
                  {getActionIcon(act.id, 'w-4 h-4')}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1.5">
                    <h4 className="text-xs sm:text-sm font-semibold text-[#1C2024] truncate">
                      {title}
                    </h4>
                    <span
                      className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-sm shrink-0 border ${
                        isSafe
                          ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
                          : 'bg-amber-100 text-amber-800 border-amber-300'
                      }`}
                    >
                      {getStatusLabel(act.status)}
                    </span>
                  </div>
                  <p className="text-xs text-stone-600 mt-1 line-clamp-2 leading-relaxed">
                    {desc}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
