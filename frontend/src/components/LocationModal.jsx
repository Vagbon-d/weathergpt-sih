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

export default function LocationModal({ isOpen, onSelectLocation, onClose, canClose }) {
  const { t } = useLanguage();

  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isGpsLoading, setIsGpsLoading] = useState(false);
  const [gpsError, setGpsError] = useState('');
  const searchTimeoutRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setResults([]);
      setGpsError('');
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [isOpen]);

  // Debounced Photon location search
  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed || trimmed.length < 2) {
      setResults([]);
      setIsSearching(false);
      return;
    }

    setIsSearching(true);
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    searchTimeoutRef.current = setTimeout(async () => {
      try {
        const data = await searchLocations(trimmed);
        setResults(data?.results || []);
      } catch (err) {
        console.warn('Search locations failed:', err);
        setResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 300);

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

          const canonicalLocation = {
            latitude: lat,
            longitude: lon,
            displayName: rev?.displayName || `${lat.toFixed(3)}°N, ${lon.toFixed(3)}°E`,
            name: rev?.name || 'Current Location',
            district: rev?.district || '',
            state: rev?.state || '',
            country: rev?.country || 'India',
            source: 'gps',
          };

          setIsGpsLoading(false);
          onSelectLocation(canonicalLocation);
        } catch (err) {
          console.warn('Reverse geocode failed:', err);
          // Fallback to raw coords
          const canonicalLocation = {
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
            displayName: `GPS: ${pos.coords.latitude.toFixed(3)}°N, ${pos.coords.longitude.toFixed(3)}°E`,
            name: 'Current Location',
            district: '',
            state: '',
            country: 'India',
            source: 'gps',
          };
          setIsGpsLoading(false);
          onSelectLocation(canonicalLocation);
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
    const canonical = {
      latitude: item.latitude,
      longitude: item.longitude,
      displayName: item.displayName || item.name,
      name: item.name,
      district: item.district || '',
      state: item.state || '',
      country: item.country || 'India',
      source: 'search',
    };
    onSelectLocation(canonical);
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
              {results.length > 0 ? (
                results.map((item, idx) => (
                  <button
                    key={`${item.latitude}-${item.longitude}-${idx}`}
                    type="button"
                    onClick={() => handleSelectResult(item)}
                    className="w-full text-left p-3 rounded-xl hover:bg-stone-100 border border-transparent hover:border-stone-200 transition-all flex items-center justify-between group cursor-pointer"
                  >
                    <div>
                      <div className="text-sm font-semibold text-[#1C2024] group-hover:text-[#1E5631]">
                        {item.name}
                      </div>
                      <div className="text-xs text-stone-500">
                        {[item.district, item.state, item.country].filter(Boolean).join(', ')}
                      </div>
                    </div>
                    <div className="text-right">
                      {item.type && (
                        <span className="text-[10px] bg-stone-100 text-stone-600 px-2 py-0.5 rounded-full capitalize border border-stone-200">
                          {item.type}
                        </span>
                      )}
                      <div className="text-[10px] text-stone-400 mt-0.5">
                        {item.latitude.toFixed(2)}°, {item.longitude.toFixed(2)}°
                      </div>
                    </div>
                  </button>
                ))
              ) : query.trim().length >= 2 && !isSearching ? (
                <div className="text-center py-6 text-stone-500 text-xs">
                  {t('noLocationsFound', 'No locations found. Try searching by district, town, or city name.')}
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
