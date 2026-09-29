/**
 * IVRSimulator.jsx — Feature-Phone / IVR-SMS Demo Simulator Panel
 *
 * Visually consistent with the existing WeatherGPT panel set (AlertBanner,
 * AgriculturePanel, ChatPanel, etc.) — same white card, same stone/green
 * colour palette, same rounded-2xl / shadow-xs treatment.
 *
 * Four sub-modes:
 *   1. SMS Simulator     — type a regional-language message, see the ≤160-char
 *                          grounded reply + RAG trace from the real pipeline.
 *   2. Voice Call Sim    — simulate the call-in → SMS-out flow: type a spoken
 *                          transcript, see the SMS that would be dispatched and
 *                          the RAG grounding trace. CLEARLY LABELED AS SIMULATOR.
 *   3. Register Caller   — register a phone number → home location profile.
 *   4. Proactive Push    — simulate an IMD cyclone/rain alert broadcast.
 *
 * "Real mode" always calls the live backend with actual weather data.
 * "Demo mode" returns clearly-labeled synthetic data for offline showcases.
 *
 * NO credentials, Twilio SIDs, or auth tokens are ever stored here.
 * The simulator reads only the public /webhook/sms/simulate endpoint.
 */

import React, { useState, useRef, useEffect } from 'react'
import { simulateSMS, registerCallerProfile, triggerProactivePush, synthesizeSpeech } from '../api'
import {
  IconPhone,
  IconAlertTriangle,
  IconShieldCheck,
} from './Icons'

// ---------------------------------------------------------------------------
// Language options matching the existing LanguageSelector
// ---------------------------------------------------------------------------
const LANG_OPTIONS = [
  { code: 'hi', label: 'हिन्दी (Hindi)' },
  { code: 'hi-Latn', label: 'Hinglish (Roman Hindi)' },
  { code: 'or', label: 'ଓଡ଼ିଆ (Odia)' },
  { code: 'bn', label: 'বাংলা (Bengali)' },
  { code: 'mr', label: 'मराठी (Marathi)' },
  { code: 'gu', label: 'ગુજરાતી (Gujarati)' },
  { code: 'ta', label: 'தமிழ் (Tamil)' },
  { code: 'te', label: 'తెలుగు (Telugu)' },
  { code: 'kn', label: 'ಕನ್ನಡ (Kannada)' },
  { code: 'en', label: 'English' },
]

const SAMPLE_MESSAGES = {
  hi: 'क्या आज धान पर कीटनाशक छिड़काव सुरक्षित है?',
  'hi-Latn': 'Aaj dhan par keetnashak chhidkaw theek hai kya?',
  or: 'ଆଜି ଧାନ ଉପରେ କୀଟନାଶକ ସ୍ପ୍ରେ ନିରାପଦ କି?',
  bn: 'আজ ধানে কীটনাশক স্প্রে করা কি নিরাপদ?',
  mr: 'आज भात शेतावर कीटकनाशक फवारणी सुरक्षित आहे का?',
  gu: 'આજ ડાંગર પર જંતુનાશક છંટકાવ સુરક્ષિત છે?',
  ta: 'இன்று நெல்லில் பூச்சிக்கொல்லி தெளிப்பது பாதுகாப்பானதா?',
  te: 'ఈరోజు వరి పంటపై పురుగుమందు స్ప్రే చేయడం సురక్షితమా?',
  kn: 'ಇಂದು ಭತ್ತದ ಮೇಲೆ ಕೀಟನಾಶಕ ಸಿಂಪಡಿಸುವುದು ಸುರಕ್ಷಿತವೇ?',
  en: 'Is it safe to spray pesticide on paddy today?',
}

const IVR_SAMPLE_SCENARIOS = [
  { label: 'Cyclone Alert Simulation', district: 'Balasore', state: 'Odisha', dryRun: true },
  { label: 'Heavy Rain Push — Coastal Maharashtra', district: 'Ratnagiri', state: 'Maharashtra', dryRun: true },
  { label: 'Farmer Irrigation Advisory SMS', district: 'Guntur', state: 'Andhra Pradesh', dryRun: true },
]

// ---------------------------------------------------------------------------
// Small sub-components
// ---------------------------------------------------------------------------

function SectionTab({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
        active
          ? 'bg-[#1E5631] text-white shadow-sm'
          : 'text-stone-500 hover:text-stone-800 hover:bg-stone-100'
      }`}
    >
      {children}
    </button>
  )
}

function Field({ label, children }) {
  return (
    <div className="space-y-1">
      <label className="text-[11px] font-semibold text-stone-500 uppercase tracking-wide">{label}</label>
      {children}
    </div>
  )
}

function PhoneDisplay({ message, reply, loading, demoMode }) {
  return (
    <div className="bg-stone-900 rounded-2xl p-3 space-y-3 min-h-[140px] border border-stone-700">
      <div className="flex items-center gap-2 border-b border-stone-700 pb-2">
        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-[10px] font-mono text-stone-400">+91 XXXX-XXX-XXX → WeatherGPT</span>
        {demoMode && (
          <span className="ml-auto text-[9px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">
            DEMO DATA
          </span>
        )}
      </div>

      {message && (
        <div className="flex justify-end">
          <div className="bg-blue-600 text-white text-xs px-3 py-2 rounded-2xl rounded-tr-sm max-w-[80%] font-medium">
            {message}
          </div>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-stone-400 text-[11px]">
          <div className="w-4 h-4 border-2 border-stone-600 border-t-emerald-400 rounded-full animate-spin" />
          <span>Processing grounded pipeline…</span>
        </div>
      )}

      {reply && !loading && (
        <div className="flex justify-start">
          <div className={`text-xs px-3 py-2 rounded-2xl rounded-tl-sm max-w-[90%] ${
            demoMode
              ? 'bg-amber-900/40 text-amber-200 border border-amber-700/40'
              : 'bg-stone-700 text-stone-100'
          }`}>
            {reply}
          </div>
        </div>
      )}
    </div>
  )
}

function RagTrace({ trace, sources, asOf }) {
  if (!trace) return null
  return (
    <div className="bg-stone-50 border border-stone-200 rounded-xl p-3 space-y-2 text-[11px]">
      <div className="font-semibold text-stone-700 flex items-center gap-1.5">
        <IconShieldCheck className="w-3.5 h-3.5 text-[#1E5631]" />
        RAG Grounding Trace
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-stone-600">
        {trace.intent && <><span className="font-medium">Intent:</span><span className="font-mono">{trace.intent}</span></>}
        {trace.domain && <><span className="font-medium">Domain:</span><span className="font-mono">{trace.domain}</span></>}
        {trace.rag_count !== undefined && <><span className="font-medium">RAG docs:</span><span className="font-mono">{trace.rag_count}</span></>}
        {trace.response_time_ms && <><span className="font-medium">Latency:</span><span className="font-mono">{trace.response_time_ms} ms</span></>}
      </div>
      {trace.operations && (
        <div className="space-y-1 border-t border-stone-200 pt-2">
          <div className="font-medium text-stone-700">Ag Operations (Python Rules):</div>
          {Object.entries(trace.operations).map(([op, val]) => (
            <div key={op} className="flex items-center gap-2">
              <span className="capitalize text-stone-500">{op}:</span>
              <span className={`font-bold px-1.5 py-0.5 rounded text-[10px] ${
                ['SAFE', 'RECOMMENDED', 'FAVORABLE'].includes(val?.status)
                  ? 'bg-emerald-100 text-emerald-800'
                  : val?.status === 'CAUTION'
                  ? 'bg-amber-100 text-amber-800'
                  : 'bg-red-100 text-red-800'
              }`}>{val?.status}</span>
            </div>
          ))}
        </div>
      )}
      {sources && sources.length > 0 && (
        <div className="border-t border-stone-200 pt-2 text-stone-500">
          <span className="font-medium">Sources: </span>{sources.join(', ')}
          {asOf && <span className="ml-2 text-stone-400">as of {asOf}</span>}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function IVRSimulator({ selectedLocation, language: appLanguage = 'hi' }) {
  const [isOpen, setIsOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('sms')

  // SMS Simulator state
  const [smsLang, setSmsLang] = useState(appLanguage || 'hi')
  const [smsMessage, setSmsMessage] = useState('')
  const [smsHomeLocation, setSmsHomeLocation] = useState('')
  const [smsDemoMode, setSmsDemoMode] = useState(false)
  const [smsLoading, setSmsLoading] = useState(false)
  const [smsResult, setSmsResult] = useState(null)
  const [smsError, setSmsError] = useState('')

  // Voice Call Simulator state
  const [voiceLang, setVoiceLang] = useState(appLanguage || 'hi')
  const [voiceTranscript, setVoiceTranscript] = useState('')
  const [voiceHomeLocation, setVoiceHomeLocation] = useState('')
  const [voiceLoading, setVoiceLoading] = useState(false)
  const [voiceResult, setVoiceResult] = useState(null)
  const [voiceError, setVoiceError] = useState('')

  // Registration state
  const [regPhone, setRegPhone] = useState('+919999999999')
  const [regLocation, setRegLocation] = useState('')
  const [regLat, setRegLat] = useState(null)
  const [regLon, setRegLon] = useState(null)
  const [locDetecting, setLocDetecting] = useState(false)
  const [regLang, setRegLang] = useState('hi')
  const [regLoading, setRegLoading] = useState(false)
  const [regResult, setRegResult] = useState(null)

  // Proactive push state
  const [pushScenario, setPushScenario] = useState(0)
  const [pushLoading, setPushLoading] = useState(false)
  const [pushResult, setPushResult] = useState(null)

  // IVR audio playback
  const audioRef = useRef(null)
  const [ivrAudioBase64, setIvrAudioBase64] = useState(null)
  const [ivrAudioLoading, setIvrAudioLoading] = useState(false)

  // Sync language to app language when panel opens
  useEffect(() => {
    if (appLanguage && appLanguage !== smsLang) {
      setSmsLang(appLanguage)
      setSmsMessage(SAMPLE_MESSAGES[appLanguage] || SAMPLE_MESSAGES['hi'])
    }
    if (appLanguage && appLanguage !== voiceLang) {
      setVoiceLang(appLanguage)
      setVoiceTranscript(SAMPLE_MESSAGES[appLanguage] || SAMPLE_MESSAGES['hi'])
    }
  }, [appLanguage])

  useEffect(() => {
    if (selectedLocation) {
      const locName = selectedLocation.label || selectedLocation.displayName || selectedLocation.name || ''
      setSmsHomeLocation(locName)
      setRegLocation(locName)
      setVoiceHomeLocation(locName)
    }
  }, [selectedLocation])

  // Set a sample message when language changes (SMS)
  const handleLangChange = (lang) => {
    setSmsLang(lang)
    if (!smsMessage || Object.values(SAMPLE_MESSAGES).includes(smsMessage)) {
      setSmsMessage(SAMPLE_MESSAGES[lang] || '')
    }
  }

  // Set a sample transcript when language changes (Voice)
  const handleVoiceLangChange = (lang) => {
    setVoiceLang(lang)
    if (!voiceTranscript || Object.values(SAMPLE_MESSAGES).includes(voiceTranscript)) {
      setVoiceTranscript(SAMPLE_MESSAGES[lang] || '')
    }
  }

  const handleSmsSend = async () => {
    if (!smsMessage.trim()) return
    setSmsLoading(true)
    setSmsError('')
    setSmsResult(null)
    try {
      const res = await simulateSMS({
        message: smsMessage,
        language: smsLang,
        homeLocation: smsHomeLocation || (selectedLocation?.label || null),
        latitude: selectedLocation?.latitude ?? null,
        longitude: selectedLocation?.longitude ?? null,
        demoMode: smsDemoMode,
      })
      setSmsResult(res)
    } catch (err) {
      setSmsError(err.message || 'Failed to simulate SMS.')
    } finally {
      setSmsLoading(false)
    }
  }

  /**
   * Voice Call Simulator — simulates the call-in → SMS-out pipeline.
   * The user types what they would have SPOKEN; the backend runs
   * generate_grounded_advisory(channel="sms") and returns the SMS text
   * that would be dispatched to the caller's phone.
   * This reuses /webhook/sms/simulate so no new backend endpoint is needed.
   */
  const handleVoiceSimulate = async () => {
    if (!voiceTranscript.trim()) return
    setVoiceLoading(true)
    setVoiceError('')
    setVoiceResult(null)
    try {
      // Reuse the simulate endpoint: transcript is treated as the inbound message,
      // and the backend pipeline runs with channel="sms" (same as the real voice/process route).
      const res = await simulateSMS({
        message: voiceTranscript,
        language: voiceLang,
        homeLocation: voiceHomeLocation || (selectedLocation?.label || null),
        latitude: selectedLocation?.latitude ?? null,
        longitude: selectedLocation?.longitude ?? null,
        demoMode: false, // Voice Call Sim always uses the real pipeline
      })
      setVoiceResult(res)
    } catch (err) {
      setVoiceError(err.message || 'Failed to simulate voice call.')
    } finally {
      setVoiceLoading(false)
    }
  }

  const handleIVRAudio = async () => {
    if (!smsResult?.sms_reply) return
    setIvrAudioLoading(true)
    setIvrAudioBase64(null)
    try {
      const ttsRes = await synthesizeSpeech(smsResult.sms_reply, smsLang)
      if (ttsRes?.audio_base64) {
        setIvrAudioBase64(ttsRes.audio_base64)
        // Play in browser
        setTimeout(() => {
          if (audioRef.current) audioRef.current.play()
        }, 100)
      }
    } catch (err) {
      // Silently degrade — audio preview is optional
    } finally {
      setIvrAudioLoading(false)
    }
  }

  const handleDetectCurrentLocation = () => {
    if (!navigator.geolocation) {
      alert('Geolocation is not supported by your browser.')
      return
    }
    setLocDetecting(true)
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const lat = pos.coords.latitude
        const lon = pos.coords.longitude
        setRegLat(lat)
        setRegLon(lon)
        try {
          const res = await fetch(`https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${lat}&longitude=${lon}&localityLanguage=en`)
          const data = await res.json()
          const locality = data.city || data.locality || ''
          const district = data.localityInfo?.administrative?.find(a => a.description?.toLowerCase().includes('district'))?.name || ''
          const state = data.principalSubdivision || ''
          const name = [locality, district, state].filter(Boolean).join(', ') || `${lat.toFixed(4)}, ${lon.toFixed(4)}`
          setRegLocation(name)
        } catch {
          setRegLocation(`${lat.toFixed(4)}, ${lon.toFixed(4)}`)
        } finally {
          setLocDetecting(false)
        }
      },
      (err) => {
        setLocDetecting(false)
        alert('Could not detect location: ' + err.message)
      },
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }

  const handleRegister = async () => {
    if (!regPhone || !regLocation) return
    setRegLoading(true)
    setRegResult(null)
    try {
      const res = await registerCallerProfile({
        phone: regPhone,
        homeLocation: regLocation,
        language: regLang,
        latitude: regLat,
        longitude: regLon,
      })
      setRegResult({ ok: true, msg: `Registered: ${res.canonical_location} (${res.latitude.toFixed(4)}, ${res.longitude.toFixed(4)})` })
    } catch (err) {
      setRegResult({ ok: false, msg: err.message })
    } finally {
      setRegLoading(false)
    }
  }

  const handleProactivePush = async () => {
    const scenario = IVR_SAMPLE_SCENARIOS[pushScenario]
    setPushLoading(true)
    setPushResult(null)
    try {
      const res = await triggerProactivePush({
        district: scenario.district,
        state: scenario.state,
        dryRun: scenario.dryRun,
      })
      setPushResult(res)
    } catch (err) {
      setPushResult({ status: 'error', reason: err.message })
    } finally {
      setPushLoading(false)
    }
  }

  // ---------------------------------------------------------------------------
  // Collapsed pill button
  // ---------------------------------------------------------------------------
  if (!isOpen) {
    return (
      <div id="section-ivr-simulator" className="bg-white rounded-2xl border border-stone-200/90 shadow-xs">
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="w-full flex items-center justify-between px-4 py-3.5 cursor-pointer group"
        >
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-stone-900 text-white flex items-center justify-center shrink-0">
              <IconPhone className="w-4 h-4" />
            </div>
            <div className="text-left">
              <div className="text-sm font-semibold text-stone-900 flex items-center gap-2">
                Feature-Phone / IVR–SMS Demo
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-stone-100 text-stone-500 border border-stone-200">
                  SIH26068
                </span>
              </div>
              <div className="text-[11px] text-stone-500 mt-0.5">
                Simulate SMS advisory &amp; IVR voice for rural feature-phone users
              </div>
            </div>
          </div>
          <span className="text-xs text-stone-400 group-hover:text-stone-600 transition-colors">Open →</span>
        </button>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Expanded panel
  // ---------------------------------------------------------------------------
  return (
    <div id="section-ivr-simulator" className="bg-white rounded-2xl border border-stone-200/90 shadow-xs overflow-hidden">
      {/* Header */}
      <div className="bg-stone-900 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-white/10 text-white flex items-center justify-center shrink-0">
            <IconPhone className="w-3.5 h-3.5" />
          </div>
          <div>
            <div className="text-sm font-semibold text-white">Feature-Phone / IVR–SMS Demo Simulator</div>
            <div className="text-[11px] text-stone-400">
              Same grounded pipeline as the web app — zero extra hallucination risk
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setIsOpen(false)}
          className="text-stone-400 hover:text-white text-xs transition-colors cursor-pointer px-2 py-1 rounded-lg hover:bg-white/10"
        >
          Close ✕
        </button>
      </div>

      {/* Tab Bar */}
      <div className="px-4 pt-3 pb-1">
        <div className="flex gap-1 bg-stone-100 p-1 rounded-xl flex-wrap">
          <SectionTab active={activeTab === 'sms'} onClick={() => setActiveTab('sms')}>
            📱 SMS Simulator
          </SectionTab>
          <SectionTab active={activeTab === 'voice'} onClick={() => setActiveTab('voice')}>
            📞 Voice Call Sim
          </SectionTab>
          <SectionTab active={activeTab === 'register'} onClick={() => setActiveTab('register')}>
            👤 Register Caller
          </SectionTab>
          <SectionTab active={activeTab === 'push'} onClick={() => setActiveTab('push')}>
            🔔 Proactive Push
          </SectionTab>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* ================================================================
            TAB 1: SMS Simulator
        ================================================================ */}
        {activeTab === 'sms' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Query Language">
                <select
                  value={smsLang}
                  onChange={e => handleLangChange(e.target.value)}
                  className="w-full text-xs border border-stone-200 rounded-lg px-2.5 py-2 bg-white text-stone-800 focus:outline-none focus:ring-2 focus:ring-[#1E5631]/30"
                >
                  {LANG_OPTIONS.map(l => (
                    <option key={l.code} value={l.code}>{l.label}</option>
                  ))}
                </select>
              </Field>

              <Field label="Home Location (optional)">
                <input
                  type="text"
                  value={smsHomeLocation}
                  onChange={e => setSmsHomeLocation(e.target.value)}
                  placeholder="e.g. Balasore, Odisha"
                  className="w-full text-xs border border-stone-200 rounded-lg px-2.5 py-2 bg-white text-stone-800 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-[#1E5631]/30"
                />
              </Field>
            </div>

            <Field label="SMS Message">
              <div className="relative">
                <textarea
                  value={smsMessage}
                  onChange={e => setSmsMessage(e.target.value)}
                  placeholder={SAMPLE_MESSAGES[smsLang] || 'Type your message here…'}
                  rows={2}
                  maxLength={320}
                  className="w-full text-xs border border-stone-200 rounded-lg px-2.5 py-2 bg-white text-stone-800 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-[#1E5631]/30 resize-none"
                />
                <button
                  type="button"
                  onClick={() => setSmsMessage(SAMPLE_MESSAGES[smsLang] || '')}
                  className="absolute top-2 right-2 text-[10px] text-stone-400 hover:text-[#1E5631] transition-colors cursor-pointer"
                  title="Fill sample message"
                >
                  Sample
                </button>
              </div>
            </Field>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={smsDemoMode}
                  onChange={e => setSmsDemoMode(e.target.checked)}
                  className="w-3.5 h-3.5 accent-amber-500"
                />
                <span className="text-xs text-stone-600">
                  Demo mode <span className="text-amber-600 font-semibold">(synthetic data, clearly labeled)</span>
                </span>
              </label>

              <button
                type="button"
                onClick={handleSmsSend}
                disabled={smsLoading || !smsMessage.trim()}
                className="flex items-center gap-1.5 bg-stone-900 hover:bg-stone-800 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors cursor-pointer"
              >
                {smsLoading ? (
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : '→'}
                Send SMS
              </button>
            </div>

            {smsError && (
              <div className="flex items-center gap-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                <IconAlertTriangle className="w-4 h-4 shrink-0" />
                {smsError}
              </div>
            )}

            {/* Phone display */}
            <PhoneDisplay
              message={smsMessage}
              reply={smsResult?.sms_reply}
              loading={smsLoading}
              demoMode={smsResult?.mode === 'demo'}
            />

            {smsResult && (
              <>
                {/* Character count */}
                <div className="flex items-center justify-between text-[11px] text-stone-500">
                  <span>Reply length: <strong>{smsResult.sms_reply?.length ?? 0}</strong> / 160 chars</span>
                  {smsResult.sms_reply && smsResult.sms_reply.length <= 160 && (
                    <span className="text-emerald-700 font-semibold">✓ Single SMS segment</span>
                  )}
                </div>

                {/* IVR audio playback */}
                {smsResult.mode !== 'demo' && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleIVRAudio}
                      disabled={ivrAudioLoading}
                      className="flex items-center gap-1.5 text-xs border border-stone-200 hover:border-stone-300 bg-stone-50 hover:bg-stone-100 text-stone-700 font-medium px-3 py-1.5 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
                    >
                      {ivrAudioLoading ? (
                        <span className="w-3 h-3 border-2 border-stone-400 border-t-stone-700 rounded-full animate-spin" />
                      ) : '🔊'}
                      Play IVR Audio
                    </button>
                    <span className="text-[10px] text-stone-400">(Synthesizes via Bhashini TTS)</span>
                  </div>
                )}

                {/* Hidden audio element */}
                {ivrAudioBase64 && (
                  <audio
                    ref={audioRef}
                    src={`data:audio/wav;base64,${ivrAudioBase64}`}
                    controls
                    className="w-full h-8 mt-1"
                  />
                )}

                {/* RAG trace */}
                <RagTrace
                  trace={smsResult.rag_trace}
                  sources={smsResult.sources}
                  asOf={smsResult.as_of}
                />

                {smsResult.stale_feed && (
                  <div className="flex items-center gap-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                    <IconAlertTriangle className="w-4 h-4 shrink-0" />
                    Weather feed was stale or unavailable. No fabricated data was sent.
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ================================================================
            TAB 2: Voice Call Simulator (call-in → SMS-out)
        ================================================================ */}
        {activeTab === 'voice' && (
          <div className="space-y-4">
            {/* Simulator header notice */}
            <div className="bg-blue-50 border border-blue-200 rounded-xl px-3 py-2 text-[11px] text-blue-800 flex items-start gap-2">
              <IconPhone className="w-4 h-4 shrink-0 mt-0.5 text-blue-600" />
              <span>
                <strong>Call-In → SMS-Out Simulator.</strong> Type the question the caller would have spoken
                (simulating Twilio ASR output). The backend runs the same zero-hallucination pipeline as a real
                IVR call, and returns the SMS text that would be dispatched to the caller's phone.
                The call itself hangs up with a short spoken confirmation — the answer arrives by SMS only.
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Spoken Language">
                <select
                  value={voiceLang}
                  onChange={e => handleVoiceLangChange(e.target.value)}
                  className="w-full text-xs border border-stone-200 rounded-lg px-2.5 py-2 bg-white text-stone-800 focus:outline-none focus:ring-2 focus:ring-[#1E5631]/30"
                >
                  {LANG_OPTIONS.map(l => (
                    <option key={l.code} value={l.code}>{l.label}</option>
                  ))}
                </select>
              </Field>

              <Field label="Caller's Home Location (optional)">
                <input
                  type="text"
                  value={voiceHomeLocation}
                  onChange={e => setVoiceHomeLocation(e.target.value)}
                  placeholder="e.g. Balasore, Odisha"
                  className="w-full text-xs border border-stone-200 rounded-lg px-2.5 py-2 bg-white text-stone-800 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-[#1E5631]/30"
                />
              </Field>
            </div>

            <Field label="Spoken Transcript (what Twilio ASR would return)">
              <div className="relative">
                <textarea
                  value={voiceTranscript}
                  onChange={e => setVoiceTranscript(e.target.value)}
                  placeholder={SAMPLE_MESSAGES[voiceLang] || 'Type the spoken question here…'}
                  rows={2}
                  maxLength={320}
                  className="w-full text-xs border border-stone-200 rounded-lg px-2.5 py-2 bg-white text-stone-800 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-[#1E5631]/30 resize-none"
                />
                <button
                  type="button"
                  onClick={() => setVoiceTranscript(SAMPLE_MESSAGES[voiceLang] || '')}
                  className="absolute top-2 right-2 text-[10px] text-stone-400 hover:text-[#1E5631] transition-colors cursor-pointer"
                  title="Fill sample transcript"
                >
                  Sample
                </button>
              </div>
            </Field>

            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleVoiceSimulate}
                disabled={voiceLoading || !voiceTranscript.trim()}
                className="flex items-center gap-1.5 bg-stone-900 hover:bg-stone-800 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors cursor-pointer"
              >
                {voiceLoading ? (
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : '📞'}
                Simulate Voice Call
              </button>
            </div>

            {voiceError && (
              <div className="flex items-center gap-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                <IconAlertTriangle className="w-4 h-4 shrink-0" />
                {voiceError}
              </div>
            )}

            {voiceLoading && (
              <div className="bg-stone-900 rounded-2xl p-3 space-y-3 min-h-[80px] border border-stone-700 flex items-center gap-3">
                <div className="w-4 h-4 border-2 border-stone-600 border-t-emerald-400 rounded-full animate-spin" />
                <span className="text-stone-400 text-[11px]">Running grounded pipeline → generating SMS…</span>
              </div>
            )}

            {voiceResult && !voiceLoading && (
              <div className="space-y-3">
                {/* Call timeline */}
                <div className="bg-stone-900 rounded-2xl p-3 space-y-2 border border-stone-700">
                  <div className="flex items-center gap-2 border-b border-stone-700 pb-2">
                    <div className="w-2 h-2 rounded-full bg-blue-400" />
                    <span className="text-[10px] font-mono text-stone-400">Caller speaks → Twilio ASR → Backend pipeline</span>
                  </div>

                  {/* Spoken question */}
                  <div className="flex justify-end">
                    <div className="bg-blue-600 text-white text-xs px-3 py-2 rounded-2xl rounded-tr-sm max-w-[80%] font-medium">
                      🎤 "{voiceTranscript}"
                    </div>
                  </div>

                  {/* Spoken confirmation (what caller hears on the call) */}
                  <div className="flex justify-start">
                    <div className="bg-stone-700 text-stone-200 text-[10px] px-3 py-1.5 rounded-xl italic max-w-[85%]">
                      📢 <em>(Caller hears on the call)</em>: "Thank you. Your weather advisory has been sent as a text message to your phone. Goodbye."
                    </div>
                  </div>

                  {/* SMS delivered */}
                  <div className="pt-1 border-t border-stone-700">
                    <div className="text-[9px] font-mono text-stone-500 mb-1">📨 SMS DISPATCHED TO CALLER'S PHONE:</div>
                    <div className="bg-stone-600 text-stone-100 text-xs px-3 py-2 rounded-xl">
                      {voiceResult.sms_reply}
                    </div>
                  </div>
                </div>

                {/* Character count */}
                <div className="flex items-center justify-between text-[11px] text-stone-500">
                  <span>SMS length: <strong>{voiceResult.sms_reply?.length ?? 0}</strong> / 160 chars</span>
                  {voiceResult.sms_reply && voiceResult.sms_reply.length <= 160 && (
                    <span className="text-emerald-700 font-semibold">✓ Single SMS segment</span>
                  )}
                </div>

                {/* RAG trace */}
                <RagTrace
                  trace={voiceResult.rag_trace}
                  sources={voiceResult.sources}
                  asOf={voiceResult.as_of}
                />

                {voiceResult.stale_feed && (
                  <div className="flex items-center gap-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                    <IconAlertTriangle className="w-4 h-4 shrink-0" />
                    Weather feed was stale or unavailable. An error SMS (not a fabricated answer) would have been dispatched.
                  </div>
                )}
              </div>
            )}

            <div className="bg-stone-50 border border-stone-200 rounded-xl p-3 text-[11px] text-stone-600 space-y-1">
              <div className="font-semibold text-stone-700">How the real flow works:</div>
              <div>• Caller dials the Twilio number → hears IVR greeting in their language.</div>
              <div>• Caller speaks their question → Twilio ASR converts to text → POST /webhook/voice/process.</div>
              <div>• Backend: detect language → resolve location → run grounded pipeline (channel=sms).</div>
              <div>• Outbound SMS sent to caller's phone number via Twilio REST API.</div>
              <div>• Caller hears a short spoken confirmation on the call, then the call hangs up.</div>
            </div>
          </div>
        )}

        {/* ================================================================
            TAB 3: Register Caller
        ================================================================ */}
        {activeTab === 'register' && (
          <div className="space-y-4">
            <p className="text-[11px] text-stone-500 leading-relaxed">
              Register a feature-phone number with a home location so they receive proactive IMD alerts
              without needing to spell their district on every call.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Phone Number (E.164)">
                <input
                  type="text"
                  value={regPhone}
                  onChange={e => setRegPhone(e.target.value)}
                  placeholder="+919876543210"
                  className="w-full text-xs border border-stone-200 rounded-lg px-2.5 py-2 bg-white text-stone-800 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-[#1E5631]/30"
                />
              </Field>

              <Field label="Preferred Language">
                <select
                  value={regLang}
                  onChange={e => setRegLang(e.target.value)}
                  className="w-full text-xs border border-stone-200 rounded-lg px-2.5 py-2 bg-white text-stone-800 focus:outline-none focus:ring-2 focus:ring-[#1E5631]/30"
                >
                  {LANG_OPTIONS.map(l => (
                    <option key={l.code} value={l.code}>{l.label}</option>
                  ))}
                </select>
              </Field>
            </div>

            <Field label="Home / Farm Location">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={regLocation}
                  onChange={e => setRegLocation(e.target.value)}
                  placeholder="e.g. Panjim, Goa"
                  className="flex-1 text-xs border border-stone-200 rounded-lg px-2.5 py-2 bg-white text-stone-800 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-[#1E5631]/30"
                />
                <button
                  type="button"
                  onClick={handleDetectCurrentLocation}
                  disabled={locDetecting}
                  className="px-3 py-2 bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 text-white rounded-lg text-xs font-medium flex items-center gap-1 transition-colors whitespace-nowrap cursor-pointer shadow-sm"
                  title="Detect farmer's current live location using device GPS or network"
                >
                  {locDetecting ? '📍 Detecting…' : '📍 Take Current Location'}
                </button>
              </div>
              {regLat && regLon && (
                <div className="text-[10px] text-emerald-700 mt-1 font-mono">
                  ✓ Live Coordinates Locked: {regLat.toFixed(4)}, {regLon.toFixed(4)}
                </div>
              )}
            </Field>

            <button
              type="button"
              onClick={handleRegister}
              disabled={regLoading || !regPhone || !regLocation}
              className="w-full bg-[#1E5631] hover:bg-[#174426] disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold px-4 py-2.5 rounded-lg transition-colors cursor-pointer"
            >
              {regLoading ? 'Registering…' : 'Register Caller Profile'}
            </button>

            {regResult && (
              <div className={`text-xs px-3 py-2 rounded-lg border ${
                regResult.ok
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                  : 'bg-red-50 text-red-800 border-red-200'
              }`}>
                {regResult.ok ? '✓ ' : '✗ '}{regResult.msg}
              </div>
            )}

            <div className="bg-stone-50 border border-stone-200 rounded-xl p-3 text-[11px] text-stone-600 space-y-1">
              <div className="font-semibold text-stone-700">How this works in production:</div>
              <div>• Callers SMS "MY LOCATION: &lt;village/district&gt;" to register automatically.</div>
              <div>• Or dial the IVR number; the system asks for their village/district on first call.</div>
              <div>• Profiles are stored in a local SQLite DB — no cloud dependency.</div>
            </div>
          </div>
        )}

        {/* ================================================================
            TAB 3: Proactive Push Simulator
        ================================================================ */}
        {activeTab === 'push' && (
          <div className="space-y-4">
            <div className="bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 text-[11px] text-amber-800 flex items-start gap-2">
              <IconAlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
              <span>
                Proactive push fires <strong>only</strong> when the IMD bulletin repository contains a
                genuine active warning (severity RED/ORANGE/YELLOW) for the selected district.
                If no real warning is found, the push is blocked and logged. No fabricated alerts.
              </span>
            </div>

            <Field label="Select Demo Scenario">
              <select
                value={pushScenario}
                onChange={e => setPushScenario(Number(e.target.value))}
                className="w-full text-xs border border-stone-200 rounded-lg px-2.5 py-2 bg-white text-stone-800 focus:outline-none focus:ring-2 focus:ring-[#1E5631]/30"
              >
                {IVR_SAMPLE_SCENARIOS.map((s, i) => (
                  <option key={i} value={i}>{s.label}</option>
                ))}
              </select>
            </Field>

            <div className="bg-stone-50 border border-stone-200 rounded-xl p-3 text-[11px] text-stone-600 space-y-1">
              {(() => {
                const s = IVR_SAMPLE_SCENARIOS[pushScenario]
                return (
                  <>
                    <div><span className="font-medium">District:</span> {s.district}</div>
                    <div><span className="font-medium">State:</span> {s.state}</div>
                    <div>
                      <span className="font-medium">Mode:</span>{' '}
                      <span className="text-amber-700 font-semibold">Dry-run (log only, no real Twilio calls)</span>
                    </div>
                  </>
                )
              })()}
            </div>

            <button
              type="button"
              onClick={handleProactivePush}
              disabled={pushLoading}
              className="w-full bg-stone-900 hover:bg-stone-800 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold px-4 py-2.5 rounded-lg transition-colors cursor-pointer flex items-center justify-center gap-2"
            >
              {pushLoading
                ? <><span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Checking IMD repository…</>
                : '🔔 Trigger Proactive Push (Dry-run)'}
            </button>

            {pushResult && (
              <div className="space-y-2">
                <div className={`text-xs px-3 py-2 rounded-lg border flex items-center gap-2 ${
                  pushResult.status === 'dispatched' || pushResult.status === 'no_action'
                    ? 'bg-stone-50 border-stone-200 text-stone-700'
                    : 'bg-red-50 border-red-200 text-red-800'
                }`}>
                  {pushResult.status === 'dispatched' && '✓ '}
                  {pushResult.status === 'no_action' && 'ℹ '}
                  {pushResult.status === 'error' && '✗ '}
                  <span>
                    {pushResult.reason || `${pushResult.warnings_fired ?? 0} IMD warning(s) found — would notify ${pushResult.callers_dispatched ?? 0} registered caller(s).`}
                  </span>
                </div>

                {pushResult.top_warning_preview && (
                  <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-[11px] space-y-1">
                    <div className="font-semibold text-red-800">IMD Warning (Retrieved from live crawler):</div>
                    <div className="text-red-700">{pushResult.top_warning_preview}</div>
                    <div className="text-red-500">Severity: {pushResult.top_warning_severity} — {pushResult.as_of}</div>
                  </div>
                )}
              </div>
            )}

            <div className="bg-stone-50 border border-stone-200 rounded-xl p-3 text-[11px] text-stone-600 space-y-1">
              <div className="font-semibold text-stone-700">In production:</div>
              <div>• This endpoint is called by an NDMA/IMD webhook or a scheduled cron every 30 min.</div>
              <div>• With Twilio credentials configured, it dispatches real outbound SMS / IVR callbacks.</div>
              <div>• Caller replies in their regional language are handled by /webhook/sms.</div>
            </div>
          </div>
        )}

        {/* Footer — zero hallucination notice */}
        <div className="flex items-start gap-2 bg-stone-50 border border-stone-200 rounded-xl px-3 py-2 text-[11px] text-stone-600">
          <IconShieldCheck className="w-4 h-4 text-[#1E5631] shrink-0 mt-0.5" />
          <span>
            All responses in real mode are produced by the same zero-hallucination pipeline as the web app.
            IMD warnings, weather values, and agricultural verdicts come exclusively from retrieved data + Python rules.
          </span>
        </div>
      </div>
    </div>
  )
}
