import React, { useEffect, useState, useRef } from 'react';
import WeatherHero from './components/WeatherHero';
import ForecastStrip from './components/ForecastStrip';
import WeatherChart from './components/WeatherChart';
import AlertBanner from './components/AlertBanner';
import AgriculturePanel from './components/AgriculturePanel';
import QuickSuggestions from './components/QuickSuggestions';
import ChatPanel from './components/ChatPanel';
import LanguageSelector from './components/LanguageSelector';
import LocationModal, { normalizeLocation } from './components/LocationModal';
import ActionRecommendations from './components/ActionRecommendations';
import IVRSimulator from './components/IVRSimulator';
import HelplineBanner from './components/HelplineBanner';
import CallActivityFeed from './components/CallActivityFeed';
import {
  IconCloudSun,
  IconMapPin,
  IconNavigation,
  IconSearch,
  IconAlertTriangle,
  IconShieldCheck,
} from './components/Icons';
import { fetchWeather, fetchAlerts, sendChat } from './api';
import { LanguageProvider, useLanguage } from './i18n/LanguageContext';
import { stopGlobalAudio } from './utils/speechManager';

function MainApp() {
  const { language, setLanguage, t } = useLanguage();

  // Canonical selected location state: null until user selects via GPS or Search
  const [selectedLocation, setSelectedLocation] = useState(() => {
    try {
      const stored = sessionStorage.getItem('weathergpt_location');
      if (stored) {
        const parsed = JSON.parse(stored);
        return normalizeLocation(parsed) || parsed;
      }
      return null;
    } catch {
      return null;
    }
  });

  // Show modal immediately on first load if no location stored
  const [showLocationModal, setShowLocationModal] = useState(!selectedLocation);
  const [weather, setWeather] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [isWaitingChat, setIsWaitingChat] = useState(false);
  const [error, setError] = useState('');

  // Initial welcome greeting tracking
  const hasUserMessaged = useRef(false);
  const sendingLockRef = useRef(false);

  useEffect(() => {
    stopGlobalAudio();
    if (!hasUserMessaged.current) {
      setMessages([
        {
          id: 'welcome-msg',
          role: 'assistant',
          text: t('welcomeGreeting', "Namaste! I'm WeatherGPT, your personal assistant for weather forecasts, IMD warnings, and agricultural guidance. Ask me anything in your preferred language!"),
          language,
        },
      ]);
    }
  }, [language, t]);

  // Fetch weather and alerts whenever selectedLocation changes (NEVER on language change alone)
  useEffect(() => {
    if (!selectedLocation) {
      setWeather(null);
      setAlerts([]);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError('');

    fetchWeather(selectedLocation, controller.signal)
      .then((w) => {
        if (controller.signal.aborted) return;
        setWeather(w);
        return fetchAlerts(selectedLocation, controller.signal);
      })
      .then((a) => {
        if (controller.signal.aborted || !a) return;
        setAlerts(a.alerts || []);
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err.message || 'Failed to load weather data.');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [selectedLocation]);

  // Handler when user chooses location in LocationModal
  const handleSelectLocation = (loc) => {
    const canonical = normalizeLocation(loc) || loc;
    setSelectedLocation(canonical);
    setShowLocationModal(false);
    try {
      sessionStorage.setItem('weathergpt_location', JSON.stringify(canonical));
    } catch (e) {
      console.warn('Could not save location to sessionStorage:', e);
    }
  };

  // Smooth scroll helper for top navigation anchors
  const scrollToSection = (id) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  // Handle sending chat messages
  const handleSend = async (text) => {
    const trimmed = (text || '').trim();
    if (!trimmed || isWaitingChat || sendingLockRef.current) return;
    stopGlobalAudio();
    sendingLockRef.current = true;
    hasUserMessaged.current = true;
    const reqId = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    setMessages((prev) => [...prev, { id: `u-${reqId}`, role: 'user', text: trimmed }]);
    setIsWaitingChat(true);

    const recentHistory = messages
      .slice(-6)
      .map((m) => ({ role: m.role, content: m.text }));

    try {
      const res = await sendChat({
        query: trimmed,
        location: selectedLocation
          ? {
              name: selectedLocation.name,
              label: selectedLocation.label,
              displayName: selectedLocation.displayName,
              latitude: selectedLocation.latitude,
              longitude: selectedLocation.longitude,
              city: selectedLocation.city,
              district: selectedLocation.district,
              state: selectedLocation.state,
              country: selectedLocation.country,
              postcode: selectedLocation.postcode,
              weather_location: selectedLocation.weather_location,
              admin_label: selectedLocation.admin_label,
            }
          : null,
        language,
        latitude: selectedLocation?.latitude ?? null,
        longitude: selectedLocation?.longitude ?? null,
        history: recentHistory,
      });

      const answerText = res.answer || "I couldn't generate a response from the available weather data.";
      const sourceInfo = res.weather?.source || (res.weather_used ? weather?.source : undefined);

      setMessages((prev) => [
        ...prev,
        {
          id: `a-${reqId}`,
          role: 'assistant',
          text: answerText,
          source: sourceInfo,
          sources: res.sources || (sourceInfo ? [sourceInfo] : ['Open-Meteo']),
          language: res.language || language,
          location_required: res.location_required === true,
        },
      ]);

      // If backend returns new weather data for application location, sync it.
      // Do NOT overwrite app weather when query asked about an explicit query-specific location (e.g. Panjim).
      if (res.weather?.current && selectedLocation && res.location_source !== 'query') {
        setWeather((prev) => ({
          ...prev,
          current: res.weather.current,
          forecast: res.weather.forecast || prev?.forecast,
          source: res.weather.source || prev?.source,
        }));
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${reqId}`,
          role: 'assistant',
          text: `Notice: ${err.message || 'Could not retrieve answer. Please try again.'}`,
          language,
        },
      ]);
    } finally {
      setIsWaitingChat(false);
      sendingLockRef.current = false;
    }
  };

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#1C2024] antialiased">
      {/* Location Selection Modal */}
      <LocationModal
        isOpen={showLocationModal}
        canClose={Boolean(selectedLocation)}
        onClose={() => setShowLocationModal(false)}
        onSelectLocation={handleSelectLocation}
      />

      {/* Top Header Bar with Navigation: WeatherGPT, Weather, Farm, Alerts, Insights, Language */}
      <header className="bg-[#1C2024] text-white sticky top-0 z-30 shadow-xs border-b border-stone-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-2.5 flex items-center justify-between gap-4">
          {/* Brand Logo & Title */}
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#1E5631] text-white flex items-center justify-center shrink-0">
              <IconCloudSun className="w-4 h-4" />
            </div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-base sm:text-lg tracking-tight text-white leading-none">
                WeatherGPT
              </span>
              <span className="text-[10px] bg-stone-800 text-stone-300 font-medium px-1.5 py-0.5 rounded border border-stone-700">
                SIH26068
              </span>
            </div>
          </div>

          {/* Desktop Navigation Links: Weather, Farm, Alerts, Insights */}
          <nav className="hidden md:flex items-center gap-1 text-xs font-medium text-stone-300">
            <button
              type="button"
              onClick={() => scrollToSection('section-weather')}
              className="px-3 py-1.5 rounded-lg hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            >
              {t('navWeather', 'Weather')}
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('section-farm')}
              className="px-3 py-1.5 rounded-lg hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            >
              {t('navFarm', 'Farm')}
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('section-alerts')}
              className="px-3 py-1.5 rounded-lg hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            >
              {t('navAlerts', 'Alerts')}
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('section-insights')}
              className="px-3 py-1.5 rounded-lg hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            >
              {t('navInsights', 'Insights')}
            </button>
          </nav>

          {/* Location Badge + Change Button & Language Selector */}
          <div className="flex items-center gap-2.5">
            {selectedLocation ? (
              <div className="flex items-center gap-1.5 bg-white/10 border border-white/15 rounded-full px-3 py-1 text-xs text-white">
                <IconMapPin className="w-3.5 h-3.5 text-stone-300" />
                <span className="font-semibold max-w-[130px] sm:max-w-[180px] truncate" title={selectedLocation.displayName || selectedLocation.label}>
                  {selectedLocation.short_label || (selectedLocation.state && !selectedLocation.name.toLowerCase().includes(selectedLocation.state.toLowerCase()) ? `${selectedLocation.name}, ${selectedLocation.state}` : (selectedLocation.label || selectedLocation.name))}
                </span>
                {selectedLocation.postcode && (
                  <span className="text-[10px] text-white/80 bg-white/15 px-1.5 py-0.5 rounded font-mono hidden xs:inline" title={`PIN: ${selectedLocation.postcode}`}>
                    {selectedLocation.postcode}
                  </span>
                )}
                {selectedLocation.source === 'gps' && (
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse ml-0.5" title="GPS Verified"></span>
                )}
                <button
                  type="button"
                  onClick={() => setShowLocationModal(true)}
                  className="ml-1 bg-[#1E5631] hover:bg-[#174426] text-white font-semibold text-[11px] px-2.5 py-0.5 rounded-full transition-colors cursor-pointer"
                >
                  {t('changeLocation', 'Change')}
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setShowLocationModal(true)}
                className="flex items-center gap-1.5 bg-[#1E5631] hover:bg-[#174426] text-white font-medium text-xs px-3 py-1.5 rounded-full transition-all cursor-pointer"
              >
                <IconMapPin className="w-3.5 h-3.5" />
                <span>{t('useLocation', 'Select Location')}</span>
              </button>
            )}

            <LanguageSelector language={language} onChange={setLanguage} />
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        {/* Helpline Banner — always visible, above the content grid */}
        <HelplineBanner />
        {/* If no location is set yet, show an inviting landing banner */}
        {!selectedLocation && (
          <div className="mb-8 p-8 sm:p-12 bg-white border border-stone-200 rounded-3xl shadow-xs text-center space-y-6 max-w-2xl mx-auto animate-fade-in">
            <div className="w-14 h-14 rounded-2xl bg-[#1E5631]/10 text-[#1E5631] flex items-center justify-center mx-auto" aria-hidden="true">
              <IconMapPin className="w-7 h-7" />
            </div>
            <div className="space-y-2">
              <h2 className="text-2xl sm:text-3xl font-semibold text-[#1C2024] tracking-tight">
                WeatherGPT
              </h2>
              <p className="text-base sm:text-lg font-medium text-stone-600 max-w-md mx-auto">
                {t('whereWouldYouLike', 'Where would you like to get weather information?')}
              </p>
            </div>
            <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3.5">
              <button
                type="button"
                onClick={() => setShowLocationModal(true)}
                className="w-full sm:w-auto bg-[#1E5631] hover:bg-[#174426] text-white font-medium text-sm px-6 py-3 rounded-xl shadow-xs transition-all cursor-pointer inline-flex items-center justify-center gap-2"
              >
                <IconNavigation className="w-4 h-4 text-white" />
                <span>{t('useLocation', 'Use Current Location')}</span>
              </button>

              <span className="text-xs font-semibold text-stone-400 uppercase tracking-widest px-2">
                {t('orDivider', 'OR')}
              </span>

              <button
                type="button"
                onClick={() => setShowLocationModal(true)}
                className="w-full sm:w-auto bg-white border border-stone-200 hover:border-stone-300 text-[#1C2024] font-medium text-sm px-6 py-3 rounded-xl shadow-2xs transition-all cursor-pointer inline-flex items-center justify-center gap-2"
              >
                <IconSearch className="w-4 h-4 text-stone-500" />
                <span>{t('orSearch', 'Search your village, town or city')}</span>
              </button>
            </div>
            <p className="text-xs text-stone-500 pt-2">
              {t('sessionNotice', 'No default city is assumed. Your location is saved only for this session in your browser.')}
            </p>
          </div>
        )}

        {/* Loading Spinner */}
        {loading && (
          <div className="py-16 text-center space-y-3 animate-pulse">
            <div className="w-10 h-10 border-3 border-[#1E5631]/30 border-t-[#1E5631] rounded-full animate-spin mx-auto"></div>
            <p className="text-sm font-medium text-stone-600">
              {t('loadingWeather', 'Fetching verified meteorology from IMD and Open-Meteo…')}
            </p>
          </div>
        )}

        {/* Error Banner */}
        {error && !loading && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 text-red-800 text-sm rounded-2xl flex items-center justify-between">
            <div className="flex items-center gap-2">
              <IconAlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
              <span>{error}</span>
            </div>
            <button
              onClick={() => setShowLocationModal(true)}
              className="text-xs font-semibold bg-red-100 hover:bg-red-200 text-red-900 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
            >
              {t('tryAgain', 'Choose another location')}
            </button>
          </div>
        )}

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: Weather & Agricultural Guidance (7 cols) */}
          <div className="lg:col-span-7 space-y-6">
            {selectedLocation && weather && !loading && (
              <>
                {/* Weather Section Anchor */}
                <div id="section-weather" className="space-y-6">
                  {/* Current Weather Hero */}
                  <WeatherHero weather={weather} />

                  {/* What should I do today? Action Recommendations */}
                  <ActionRecommendations
                    actions={weather.action_recommendations}
                    onActionClick={(title) =>
                      handleSend(
                        language === 'hi'
                          ? `${title} के बारे में और बताएं`
                          : `Tell me more about: ${title}`
                      )
                    }
                  />

                  {/* 7-Day & 24-Hour Forecast */}
                  <ForecastStrip forecast={weather.forecast} hourly={weather.hourly} />
                </div>

                {/* Insights / Trends Section: 24-Hour Hourly Chart */}
                <div id="section-insights">
                  <WeatherChart hourly={weather.hourly} />
                </div>

                {/* Farm Section: Agricultural Decision Engine */}
                <div id="section-farm">
                  <AgriculturePanel location={selectedLocation} />
                </div>

                {/* Alerts Section: IMD Official & Simulated Warnings */}
                <div id="section-alerts">
                  <AlertBanner alerts={alerts} location={weather?.location || selectedLocation?.label || selectedLocation?.displayName} />
                </div>

                {/* Feature-Phone / IVR-SMS Demo Simulator */}
                <IVRSimulator
                  selectedLocation={selectedLocation}
                  language={language}
                />
              </>
            )}

            {!selectedLocation && (
              <div className="p-8 rounded-2xl border border-dashed border-stone-300 text-center text-stone-500 space-y-2 bg-white/50">
                <p className="text-sm font-medium">
                  {t('emptyForecast', 'Weather and agricultural intelligence will appear here once you select your location.')}
                </p>
              </div>
            )}
          </div>

          {/* Right Column: Conversational AI Panel (5 cols) */}
          <div className="lg:col-span-5 space-y-4 flex flex-col h-full sticky top-16">
            {/* Quick Chips */}
            <QuickSuggestions onPick={handleSend} disabled={isWaitingChat} />

            {/* Chat Panel */}
            <div className="flex-1">
              <ChatPanel
                messages={messages}
                onSend={handleSend}
                isWaiting={isWaitingChat}
                onRequestLocation={() => setShowLocationModal(true)}
              />
            </div>

            {/* Transparency Notice */}
            <div className="p-3.5 bg-white border border-stone-200/90 rounded-2xl text-[11px] text-stone-600 leading-relaxed shadow-2xs">
              <div className="flex items-center gap-1.5 font-semibold text-[#1C2024] text-[11px] mb-1">
                <IconShieldCheck className="w-4 h-4 text-[#1E5631]" />
                <span>{t('safetyTitle', 'SIH26068 Safety Architecture:')}</span>
              </div>
              <p>
                {t('safetyDesc', 'Authoritative IMD warnings take precedence over generic models. Every weather and agricultural metric is calculated in Python before language generation. The LLM never invents numeric facts.')}
              </p>
            </div>

            {/* Live Call Activity Feed — demo/observability layer */}
            <CallActivityFeed />
          </div>
        </div>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <LanguageProvider>
      <MainApp />
    </LanguageProvider>
  );
}
