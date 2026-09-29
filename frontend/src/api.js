/**
 * Centralized API client for WeatherGPT.
 * Points to FastAPI backend on http://localhost:8000.
 * Handles 400, 404, 422, 500, 503, and network errors gracefully.
 * 
 * NO DEFAULT LOCATIONS: Requires explicit user location or coordinates.
 */

const BASE_URL = 'http://localhost:8000'

async function request(url, options = {}) {
  try {
    const res = await fetch(url, options)
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      const detail = body.detail || ''

      if (res.status === 404) {
        throw new Error(detail || 'Location not found. Please choose or search for your village, town, or city.')
      } else if (res.status === 503) {
        throw new Error(detail || 'Weather service is temporarily unavailable. Please try again in a moment.')
      } else if (res.status === 400 || res.status === 422) {
        throw new Error(detail || 'Invalid request parameters. Please verify your query.')
      } else if (res.status === 500) {
        throw new Error(detail || 'The server encountered an issue processing your request.')
      } else {
        throw new Error(detail || `Request failed with status code ${res.status}.`)
      }
    }
    return await res.json()
  } catch (err) {
    if (err.name === 'AbortError') {
      return { success: true, results: [] }
    }
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error('Could not connect to WeatherGPT backend. Please ensure the backend is running at http://localhost:8000.')
    }
    throw err
  }
}

/**
 * Search locations using Photon OpenStreetMap API biased toward India.
 */
export async function searchLocations(query, signal) {
  if (!query || !query.trim()) return { success: true, results: [] }
  return request(`${BASE_URL}/location/search?q=${encodeURIComponent(query.trim())}`, { signal })
}

/**
 * Reverse geocode coordinates to get canonical location details.
 */
export async function reverseGeocodeLocation(latitude, longitude) {
  return request(`${BASE_URL}/location/reverse?lat=${encodeURIComponent(latitude)}&lon=${encodeURIComponent(longitude)}`)
}

/**
 * Fetch current weather and 7-day forecast.
 * Requires explicit location object or coordinates.
 */
export async function fetchWeather(locationOrCoords, signal) {
  if (!locationOrCoords) {
    throw new Error('Please select a location to view weather information.')
  }

  if (typeof locationOrCoords === 'object' && locationOrCoords !== null) {
    const { latitude, longitude, label, admin_label, weather_location, displayName, name } = locationOrCoords
    const candidates = [label, admin_label, weather_location, displayName, name]
    let locName = ''
    for (const c of candidates) {
      if (c && typeof c === 'string' && !/^\d{4,6}$/.test(c.trim())) {
        locName = c.trim()
        break
      }
    }

    if (latitude !== undefined && latitude !== null && longitude !== undefined && longitude !== null) {
      const url = locName
        ? `${BASE_URL}/weather?latitude=${encodeURIComponent(latitude)}&longitude=${encodeURIComponent(longitude)}&location=${encodeURIComponent(locName)}`
        : `${BASE_URL}/weather?latitude=${encodeURIComponent(latitude)}&longitude=${encodeURIComponent(longitude)}`
      return request(url, { signal })
    }
    if (locName) {
      return request(`${BASE_URL}/weather?location=${encodeURIComponent(locName)}`, { signal })
    }
  }

  if (typeof locationOrCoords === 'string' && locationOrCoords.trim()) {
    return request(`${BASE_URL}/weather?location=${encodeURIComponent(locationOrCoords.trim())}`, { signal })
  }

  throw new Error('Please select a location to view weather information.')
}

/**
 * Fetch active weather alerts and warnings.
 */
export async function fetchAlerts(locationOrCoords = null, signal) {
  if (!locationOrCoords) {
    return request(`${BASE_URL}/alerts`, { signal })
  }

  if (typeof locationOrCoords === 'object' && locationOrCoords !== null) {
    const { latitude, longitude, label, admin_label, weather_location, displayName, name } = locationOrCoords
    const candidates = [label, admin_label, weather_location, displayName, name]
    let locName = ''
    for (const c of candidates) {
      if (c && typeof c === 'string' && !/^\d{4,6}$/.test(c.trim())) {
        locName = c.trim()
        break
      }
    }

    if (latitude !== undefined && latitude !== null && longitude !== undefined && longitude !== null) {
      const url = locName
        ? `${BASE_URL}/alerts?latitude=${encodeURIComponent(latitude)}&longitude=${encodeURIComponent(longitude)}&location=${encodeURIComponent(locName)}`
        : `${BASE_URL}/alerts?latitude=${encodeURIComponent(latitude)}&longitude=${encodeURIComponent(longitude)}`
      return request(url, { signal })
    }
    return request(`${BASE_URL}/alerts?location=${encodeURIComponent(locName)}`, { signal })
  }

  return request(`${BASE_URL}/alerts?location=${encodeURIComponent(locationOrCoords)}`, { signal })
}

/**
 * Send chat message to WeatherGPT conversational engine.
 */
export async function sendChat(payloadOrQuery, location = null, language = 'en') {
  let body = {}
  if (typeof payloadOrQuery === 'object' && payloadOrQuery !== null) {
    body = payloadOrQuery
  } else {
    body = { query: payloadOrQuery, location, language }
  }

  return request(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/**
 * Fetch agricultural advisory and agronomic operation safety checks.
 */
export async function fetchAdvisory(locationOrCoords, crop = 'rice', language = 'en') {
  let body = { crop, language }

  if (typeof locationOrCoords === 'object' && locationOrCoords !== null) {
    const { latitude, longitude, location, displayName, name } = locationOrCoords
    if (latitude !== undefined && latitude !== null && longitude !== undefined && longitude !== null) {
      body.latitude = latitude
      body.longitude = longitude
    }
    body.location = displayName || name || location || null
  } else if (typeof locationOrCoords === 'string' && locationOrCoords.trim()) {
    body.location = locationOrCoords.trim()
  }

  return request(`${BASE_URL}/advisory`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/**
 * Request speech audio from backend Bhashini TTS service.
 */
export async function synthesizeSpeech(text, language = 'en') {
  return request(`${BASE_URL}/language/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, language }),
  })
}

// ============================================================
// IVR / SMS Simulator API helpers (new)
// ============================================================

/**
 * Simulate an inbound SMS through the grounded advisory pipeline.
 * demoMode=true returns clearly-labeled synthetic data for offline demos.
 */
export async function simulateSMS({
  phone = '+919999999999',
  message,
  language = 'hi',
  homeLocation = null,
  latitude = null,
  longitude = null,
  demoMode = false,
}) {
  return request(`${BASE_URL}/webhook/sms/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      phone,
      message,
      language,
      home_location: homeLocation,
      latitude,
      longitude,
      demo_mode: demoMode,
    }),
  })
}

/**
 * Register a caller profile so they can receive proactive alerts.
 */
export async function registerCallerProfile({ phone, homeLocation, language = 'hi', userType = 'farmer', name = null, crop = 'Wheat', latitude = null, longitude = null }) {
  return request(`${BASE_URL}/webhook/sms/register-caller`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      phone,
      home_location: homeLocation,
      language,
      user_type: userType,
      name,
      crop,
      latitude,
      longitude,
    }),
  })
}

/**
 * Trigger a proactive alert push to registered callers in a district.
 * dryRun=true logs only, makes no real Twilio API calls.
 */
export async function triggerProactivePush({ district, state, location, dryRun = true }) {
  return request(`${BASE_URL}/alerts/proactive-push`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ district, state, location, dry_run: dryRun }),
  })
}
