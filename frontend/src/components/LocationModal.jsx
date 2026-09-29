import React, { useState, useEffect, useRef } from 'react';
import { searchLocations, reverseGeocodeLocation } from '../api';
import { useLanguage } from '../i18n/LanguageContext';
import {
  IconMapPin,
  IconNavigation,
  IconSearch,
  IconAlertTriangle,
  IconX,
  IconChevronRight,
} from './Icons';

export function normalizeLocation(item, source = 'search') {
  if (!item) return null;
  const lat = parseFloat(item.latitude ?? item.lat);
  const lon = parseFloat(item.longitude ?? item.lon);
  if (isNaN(lat) || isNaN(lon)) return null;

  const postcode = (item.postcode || '').toString().trim();
  let name = (item.name || '').toString().trim();
  const label = (item.label || '').toString().trim();
  const displayName = (item.displayName || '').toString().trim();
  const adminLabel = (item.admin_label || item.weather_location || '').toString().trim();

  // If name is pure digits (PIN code), derive geographic name from city/district/state or label
  if (/^\d{4,6}$/.test(name)) {
    const geoParts = [item.city, item.district, item.state].filter(
      (p) => p && typeof p === 'string' && !/^\d{4,6}$/.test(p.trim())
    );
    name = geoParts.length > 0 ? geoParts[0].trim() : (label.split(',')[0].trim() || 'Selected Area');
  }

  // Canonical clean geographic label (never standalone PIN)
  let resolvedLabel = label && !/^\d{4,6}$/.test(label)
    ? label
    : (adminLabel && !/^\d{4,6}$/.test(adminLabel) ? adminLabel : (name || `${lat.toFixed(3)}°N, ${lon.toFixed(3)}°E`));

  if (/^\d{4,6}$/.test(resolvedLabel.trim())) {
    resolvedLabel = `${lat.toFixed(3)}°N, ${lon.toFixed(3)}°E`;
  }

  const resolvedDisplayName = displayName && !/^\d{4,6}$/.test(displayName)
    ? displayName
    : (postcode && !resolvedLabel.includes(postcode) ? `${resolvedLabel} (${postcode})` : resolvedLabel);

  const state = item.state || '';
  const shortLabel = item.short_label || (state && !name.toLowerCase().includes(state.toLowerCase())
    ? `${name}, ${state}`
    : name);

  return {
    id: `${lat.toFixed(4)},${lon.toFixed(4)}`,
    latitude: lat,
    longitude: lon,
    lat: lat,
    lon: lon,
    name: name || resolvedLabel.split(',')[0].trim(),
    short_label: shortLabel,
    label: resolvedLabel,
    displayName: resolvedDisplayName,
    weather_location: adminLabel && !/^\d{4,6}$/.test(adminLabel) ? adminLabel : resolvedLabel,
    admin_label: adminLabel && !/^\d{4,6}$/.test(adminLabel) ? adminLabel : resolvedLabel,
    city: item.city || '',
    district: item.district || '',
    state: state,
    country: item.country || 'India',
    postcode: postcode,
    source: source,
  };
}

export default function LocationModal({ isOpen, onSelectLocation, onClose, canClose }) {
  const { t } = useLanguage();

  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isGpsLoading, setIsGpsLoading] = useState(false);
  const [gpsError, setGpsError] = useState('');
  const searchTimeoutRef = useRef(null);
  const abortControllerRef = useRef(null);
  const activeQueryRef = useRef('');
  const inputRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setResults([]);
      setGpsError('');
      activeQueryRef.current = '';
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [isOpen]);

  // Debounced Photon location search with stale request cancellation (350ms)
  useEffect(() => {
    const trimmed = query.trim();
    activeQueryRef.current = trimmed;

    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    if (!trimmed || trimmed.length < 2) {
      setResults([]);
      setIsSearching(false);
      return;
    }

    setIsSearching(true);
    const controller = new AbortController();
    abortControllerRef.current = controller;

    searchTimeoutRef.current = setTimeout(async () => {
      try {
        const data = await searchLocations(trimmed, controller.signal);
        if (activeQueryRef.current === trimmed) {
          setResults(data?.results || []);
        }
      } catch (err) {
        if (activeQueryRef.current === trimmed) {
          console.warn('Search locations failed:', err);
          setResults([]);
        }
      } finally {
        if (activeQueryRef.current === trimmed) {
          setIsSearching(false);
        }
      }
    }, 350);

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [query]);

  // GPS Current Location Handler
  const handleUseGps = () => {
    if (!navigator.geolocation) {
      setGpsError('Geolocation is not supported by your browser.');
      return;
    }

    setIsGpsLoading(true);
    setGpsError('');

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const lat = pos.coords.latitude;
          const lon = pos.coords.longitude;
          const rev = await reverseGeocodeLocation(lat, lon);
          const canonicalLocation = normalizeLocation({ ...rev, latitude: lat, longitude: lon }, 'gps');

          setIsGpsLoading(false);
          if (canonicalLocation) {
            onSelectLocation(canonicalLocation);
          }
        } catch (err) {
          console.warn('Reverse geocode failed:', err);
          // Fallback to raw coords
          const fallbackLocation = normalizeLocation({
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
            name: 'Current Location',
          }, 'gps');
          setIsGpsLoading(false);
          if (fallbackLocation) {
            onSelectLocation(fallbackLocation);
          }
        }
      },
      (err) => {
        setIsGpsLoading(false);
        console.warn('GPS position error:', err);
        setGpsError(t('locationError', 'GPS access denied. Please search for your village, town, or city below.'));
      },
      { timeout: 10000, enableHighAccuracy: true }
    );
  };

  const handleSelectResult = (item) => {
    const canonical = normalizeLocation(item, 'search');
    if (canonical) {
      onSelectLocation(canonical);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-stone-900/60 backdrop-blur-sm animate-fade-in">
      <div className="bg-white text-[#1C2024] w-full max-w-lg rounded-2xl shadow-xl border border-stone-200 overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-6 pb-4 bg-stone-50 border-b border-stone-200 flex items-start justify-between">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#1E5631]/10 text-[#1E5631] text-xs font-semibold mb-2">
              <IconMapPin className="w-3.5 h-3.5" />
              <span>WeatherGPT</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-semibold text-[#1C2024]">
              {t('whereAreYou', 'Where are you today?')}
            </h2>
            <p className="text-xs text-stone-600 mt-1 leading-relaxed">
              {t('locationModalSubtitle', 'Select your location to receive verified forecasts, official IMD alerts, and agricultural guidance.')}
            </p>
          </div>
          {canClose && (
            <button
              onClick={onClose}
              className="text-stone-400 hover:text-stone-700 w-8 h-8 rounded-full flex items-center justify-center hover:bg-stone-200/60 transition-colors"
              title="Close"
            >
              <IconX className="w-4 h-4" />
            </button>
          )}
        </div>

        <div className="p-6 space-y-5 overflow-y-auto flex-1">
          {/* Option 1: Use Current Location */}
          <div>
            <button
              type="button"
              onClick={handleUseGps}
              disabled={isGpsLoading}
              className="w-full bg-[#1E5631] hover:bg-[#174426] text-white font-semibold py-3.5 px-5 rounded-xl shadow-xs flex items-center justify-between transition-all group disabled:opacity-75 cursor-pointer"
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-white/20 flex items-center justify-center shrink-0">
                  {isGpsLoading ? (
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                  ) : (
                    <IconNavigation className="w-4 h-4 text-white" />
                  )}
                </div>
                <div className="text-left">
                  <div className="text-sm font-semibold leading-tight">
                    {isGpsLoading ? t('locating', 'Detecting location…') : t('useLocation', 'Use Current Location')}
                  </div>
                  <div className="text-[11px] text-white/80 font-normal">
                    {t('gpsDetect', 'GPS automatic detection')}
                  </div>
                </div>
              </div>
              <IconChevronRight className="w-4 h-4 text-white/70 group-hover:translate-x-0.5 transition-transform" />
            </button>

            {gpsError && (
              <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-xl p-2.5 mt-2 flex items-center gap-2">
                <IconAlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                <span>{gpsError}</span>
              </p>
            )}
          </div>

          {/* Divider */}
          <div className="relative flex items-center justify-center">
            <div className="border-t border-stone-200 w-full"></div>
            <span className="bg-white px-3 text-[11px] font-semibold tracking-wider text-stone-500 uppercase shrink-0">
              {t('orSearch', 'OR SEARCH LOCATION')}
            </span>
          </div>

          {/* Option 2: Search Box */}
          <div className="space-y-3">
            <div className="relative">
              <IconSearch className="w-4 h-4 absolute left-3.5 top-3.5 text-stone-400 pointer-events-none" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t('searchPlaceholder', 'Search village, town, city, district, PIN code…')}
                className="w-full bg-stone-50 border border-stone-200 text-[#1C2024] text-sm rounded-xl pl-10 pr-10 py-2.5 outline-none focus:ring-2 focus:ring-[#1E5631]/20 focus:border-[#1E5631] transition-all"
              />
              {isSearching && (
                <span className="absolute right-3.5 top-3.5 w-4 h-4 border-2 border-[#1E5631] border-t-transparent rounded-full animate-spin"></span>
              )}
            </div>

            {/* Results List */}
            <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
              {isSearching ? (
                <div className="text-center py-6 text-stone-500 text-xs flex items-center justify-center gap-2">
                  <span className="w-3.5 h-3.5 border-2 border-[#1E5631] border-t-transparent rounded-full animate-spin"></span>
                  <span>{t('searching', 'Searching...')}</span>
                </div>
              ) : results.length > 0 ? (
                results.map((item, idx) => (
                  <button
                    key={`${item.latitude || item.lat}-${item.longitude || item.lon}-${idx}`}
                    type="button"
                    onClick={() => handleSelectResult(item)}
                    className="w-full text-left p-3 rounded-xl hover:bg-stone-100 border border-transparent hover:border-stone-200 transition-all flex items-center justify-between group cursor-pointer"
                  >
                    <div>
                      <div className="text-sm font-semibold text-[#1C2024] group-hover:text-[#1E5631]">
                        {item.name}
                      </div>
                      <div className="text-xs text-stone-500">
                        {[item.city, item.district, item.state, item.country]
                          .filter(Boolean)
                          .filter((val, i, arr) => arr.indexOf(val) === i && val.toLowerCase() !== (item.name || '').toLowerCase())
                          .join(', ') || item.country || 'India'}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] text-stone-400 font-mono">
                        {(item.latitude ?? item.lat)?.toFixed(2)}°, {(item.longitude ?? item.lon)?.toFixed(2)}°
                      </div>
                    </div>
                  </button>
                ))
              ) : query.trim().length >= 2 ? (
                <div className="text-center py-6 text-stone-500 text-xs">
                  {t('noLocationsFound', "Couldn't find that location. Try a city, village, district, or PIN code.")}
                </div>
              ) : (
                <div className="text-center py-4 text-[11px] text-stone-500">
                  {t('searchDisclaimer', 'Search across Indian villages, towns, mandals, districts, and cities via OpenStreetMap Photon API.')}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 bg-stone-50 border-t border-stone-200 text-center text-[11px] text-stone-500">
          {t('sessionNotice', 'No default city is assumed. Your location is saved only for this session in your browser.')}
        </div>
      </div>
    </div>
  );
}
