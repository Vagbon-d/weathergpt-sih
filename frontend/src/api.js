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
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error('Could not connect to WeatherGPT backend. Please ensure the backend is running at http://localhost:8000.')
    }
    throw err
  }
}

/**
 * Search locations using Photon OpenStreetMap API biased toward India.
 */
export async function searchLocations(query) {
  if (!query || !query.trim()) return { results: [] }
  return request(`${BASE_URL}/location/search?q=${encodeURIComponent(query.trim())}`)
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
export async function fetchWeather(locationOrCoords) {
  if (!locationOrCoords) {
    throw new Error('Please select a location to view weather information.')
  }

  if (typeof locationOrCoords === 'object' && locationOrCoords !== null) {
    const { latitude, longitude, location, displayName, name } = locationOrCoords
    if (latitude !== undefined && latitude !== null && longitude !== undefined && longitude !== null) {
      return request(`${BASE_URL}/weather?latitude=${encodeURIComponent(latitude)}&longitude=${encodeURIComponent(longitude)}`)
    }
    const locName = displayName || name || location
    if (locName) {
      return request(`${BASE_URL}/weather?location=${encodeURIComponent(locName)}`)
    }
  }

  if (typeof locationOrCoords === 'string' && locationOrCoords.trim()) {
    return request(`${BASE_URL}/weather?location=${encodeURIComponent(locationOrCoords.trim())}`)
  }

  throw new Error('Please select a location to view weather information.')
}

/**
 * Fetch active weather alerts and warnings.
 */
export async function fetchAlerts(locationOrCoords = null) {
  if (!locationOrCoords) {
    return request(`${BASE_URL}/alerts`)
  }

  if (typeof locationOrCoords === 'object' && locationOrCoords !== null) {
    const { latitude, longitude, location, displayName } = locationOrCoords
    if (latitude !== undefined && latitude !== null && longitude !== undefined && longitude !== null) {
      return request(`${BASE_URL}/alerts?latitude=${encodeURIComponent(latitude)}&longitude=${encodeURIComponent(longitude)}&location=${encodeURIComponent(displayName || location || '')}`)
    }
    const locName = displayName || location || ''
    return request(`${BASE_URL}/alerts?location=${encodeURIComponent(locName)}`)
  }

  return request(`${BASE_URL}/alerts?location=${encodeURIComponent(locationOrCoords)}`)
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

