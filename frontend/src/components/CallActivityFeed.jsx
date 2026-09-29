/**
 * CallActivityFeed.jsx — Live Call-Status Demo Feed
 *
 * PURPOSE: Demo/observability panel for the SIH26068 hackathon presentation.
 *          Shows pipeline stage events (call_received → sms_dispatched) as
 *          real calls flow through the WeatherGPT IVR → SMS pipeline.
 *
 * SAFETY RULES (must not be violated):
 *   - NEVER displays full phone numbers. Only the masked form (**1234) received
 *     from the backend is shown.
 *   - NEVER displays transcript content. Only stage name, language, location.
 *   - WebSocket connection failure is handled silently — the panel shows a
 *     "connecting…" or "offline" badge without crashing or spamming the console.
 *   - The WebSocket URL comes from VITE_WS_BASE_URL env var (import.meta.env),
 *     never hard-coded across files.
 *   - This component is PURELY observational. Nothing it does affects the backend
 *     advisory or SMS pipeline.
 *
 * RECONNECT STRATEGY:
 *   Exponential back-off starting at 2 s, capping at 30 s.
 *   Reconnect is cancelled if the component unmounts.
 *
 * Where it is rendered:
 *   App.jsx — bottom of the right column, below the Safety Notice.
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';

// WebSocket base URL — default to localhost for dev
const WS_BASE = (import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000').replace(/\/$/, '');
const WS_URL = `${WS_BASE}/ws/call-status`;

// Maximum number of events to display in the feed (newest at top)
const MAX_EVENTS = 8;

// Human-readable stage labels and their Tailwind colour classes
const STAGE_META = {
  connected:          { label: 'Connected',            dot: 'bg-emerald-400' },
  call_received:      { label: 'Call Received',         dot: 'bg-blue-400' },
  language_detected:  { label: 'Language Detected',     dot: 'bg-indigo-400' },
  location_resolved:  { label: 'Location Resolved',     dot: 'bg-cyan-400' },
  advisory_generated: { label: 'Advisory Generated',    dot: 'bg-amber-400' },
  sms_dispatched:     { label: 'SMS Dispatched',        dot: 'bg-emerald-500' },
  location_prompt_sent:{ label: 'Location Prompt Sent', dot: 'bg-orange-400' },
  pipeline_failed:    { label: 'Pipeline Failed',       dot: 'bg-red-400' },
  ping:               { label: 'Heartbeat',             dot: 'bg-stone-300' },
};

const TIER_LABEL = {
  spoken:  'Spoken entity',
  profile: 'Saved profile',
  telecom: 'Telecom circle',
};

/** Custom hook: manages WebSocket lifecycle with reconnect back-off */
function useCallStatus(url) {
  const [events, setEvents] = useState([]);
  const [wsState, setWsState] = useState('connecting'); // connecting | open | closed
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const mountedRef = useRef(true);
  const backoffMs = useRef(2000);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    setWsState('connecting');
    let ws;
    try {
      ws = new WebSocket(url);
    } catch {
      setWsState('closed');
      return;
    }

    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return; }
      setWsState('open');
      backoffMs.current = 2000; // reset back-off on successful connect
    };

    ws.onmessage = (evt) => {
      if (!mountedRef.current) return;
      try {
        const data = JSON.parse(evt.data);
        // Silently skip ping frames — they are keepalives, not user-visible events
        if (data.stage === 'ping') return;

        const event = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          timestamp: data.timestamp || new Date().toISOString(),
          ...data,
        };
        setEvents((prev) => [event, ...prev].slice(0, MAX_EVENTS));
      } catch {
        // Malformed JSON — silently skip
      }
    };

    ws.onerror = () => {
      // Error is always followed by onclose; handle there
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setWsState('closed');
      // Exponential back-off reconnect (capped at 30 s)
      const delay = Math.min(backoffMs.current, 30000);
      backoffMs.current = Math.min(backoffMs.current * 1.5, 30000);
      reconnectTimer.current = setTimeout(connect, delay);
    };
  }, [url]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { events, wsState };
}

/** Format an ISO timestamp as HH:MM:SS IST */
function fmtTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString('en-IN', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      timeZone: 'Asia/Kolkata', hour12: false,
    });
  } catch {
    return '';
  }
}

/** Single event row */
function EventRow({ event }) {
  const meta = STAGE_META[event.stage] || { label: event.stage, dot: 'bg-stone-400' };
  return (
    <div className="flex items-start gap-2.5 py-2 border-b border-stone-100 last:border-0 text-xs">
      {/* Stage dot */}
      <div className={`mt-0.5 w-2 h-2 rounded-full shrink-0 ${meta.dot}`} aria-hidden="true" />

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-semibold text-stone-800">{meta.label}</span>
          {event.phone_masked && (
            <span className="text-stone-400 font-mono">{event.phone_masked}</span>
          )}
          {event.language && event.stage !== 'connected' && (
            <span className="bg-indigo-50 text-indigo-700 border border-indigo-100 px-1.5 py-0.5 rounded font-medium">
              {event.language}
            </span>
          )}
          {event.location && (
            <span className="bg-cyan-50 text-cyan-700 border border-cyan-100 px-1.5 py-0.5 rounded font-medium truncate max-w-[120px]" title={event.location}>
              {event.location}
            </span>
          )}
          {event.location_tier && (
            <span className="text-[10px] text-stone-400 italic">
              via {TIER_LABEL[event.location_tier] || event.location_tier}
            </span>
          )}
        </div>
      </div>

      {/* Timestamp */}
      <span className="shrink-0 text-[10px] text-stone-400 font-mono pt-0.5">
        {fmtTime(event.timestamp)}
      </span>
    </div>
  );
}

export default function CallActivityFeed() {
  const { events, wsState } = useCallStatus(WS_URL);

  const statusBadge = {
    connecting: { cls: 'bg-amber-50 text-amber-700 border-amber-200', label: 'Connecting…' },
    open:       { cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'Live' },
    closed:     { cls: 'bg-stone-100 text-stone-500 border-stone-200', label: 'Offline' },
  }[wsState];

  return (
    <div className="bg-white border border-stone-200/90 rounded-2xl shadow-xs p-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-stone-100 text-stone-600 flex items-center justify-center shrink-0">
            {/* Pulse dot icon */}
            <span
              className={`w-2.5 h-2.5 rounded-full ${wsState === 'open' ? 'bg-emerald-500 animate-pulse' : 'bg-stone-400'}`}
              aria-hidden="true"
            />
          </div>
          <div>
            <h4 className="text-xs font-bold text-stone-900 leading-none">Live Call Activity</h4>
            <p className="text-[10px] text-stone-500 mt-0.5 leading-none">Demo / Observability Feed</p>
          </div>
        </div>
        <span
          className={`text-[10px] font-semibold border px-2 py-0.5 rounded-full ${statusBadge.cls}`}
          aria-live="polite"
          aria-label={`WebSocket status: ${statusBadge.label}`}
        >
          {statusBadge.label}
        </span>
      </div>

      {/* Disclaimer */}
      <p className="text-[10px] text-stone-400 leading-relaxed mb-2 italic">
        Shows pipeline stages as calls arrive. Masked numbers only — no transcripts, no credentials.
        This feed is display-only and never affects the advisory pipeline.
      </p>

      {/* Event list */}
      <div className="min-h-[80px]" aria-live="polite" aria-label="Call pipeline events">
        {events.length === 0 ? (
          <div className="flex items-center justify-center h-16 text-xs text-stone-400">
            {wsState === 'open' ? 'Waiting for incoming calls…' : 'No events yet'}
          </div>
        ) : (
          <div>
            {events.map((evt) => (
              <EventRow key={evt.id} event={evt} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
