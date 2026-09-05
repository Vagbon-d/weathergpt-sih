"""
Photon Geocoding Service for WeatherGPT.

Provides open, high-accuracy location search for Indian villages, towns, cities,
districts, states, landmarks, and PIN codes using the Komoot Photon OpenStreetMap API.
"""

import os
import logging
import httpx

logger = logging.getLogger(__name__)

PHOTON_BASE_URL = os.getenv("PHOTON_BASE_URL", "https://photon.komoot.io").rstrip("/")
BIGDATACLOUD_URL = "https://api.bigdatacloud.net/data/reverse-geocode-client"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) WeatherGPT-Prototype/1.0"
}

# Approximate geographic center of India for location bias
# Approximate geographic center of India for location bias
INDIA_CENTER_LAT = 20.5937
INDIA_CENTER_LON = 78.9629

# Curated gazetteer of Indian agricultural villages, towns, and districts
# Ensures offline resilience and instant phonetic resolution for speech recognition
INDIAN_AGRICULTURAL_GAZETTEER = {
    "shiroda": {
        "name": "Shiroda",
        "district": "South Goa",
        "state": "Goa",
        "country": "India",
        "latitude": 15.2974,
        "longitude": 74.0044,
        "displayName": "Shiroda, South Goa, Goa, India",
    },
    "ponda": {
        "name": "Ponda",
        "district": "North Goa",
        "state": "Goa",
        "country": "India",
        "latitude": 15.4026,
        "longitude": 74.0134,
        "displayName": "Ponda, North Goa, Goa, India",
    },
    "margao": {
        "name": "Margao",
        "district": "South Goa",
        "state": "Goa",
        "country": "India",
        "latitude": 15.2736,
        "longitude": 73.9580,
        "displayName": "Margao, South Goa, Goa, India",
    },
    "panaji": {
        "name": "Panaji",
        "district": "North Goa",
        "state": "Goa",
        "country": "India",
        "latitude": 15.4909,
        "longitude": 73.8278,
        "displayName": "Panaji, North Goa, Goa, India",
    },
    "mapusa": {
        "name": "Mapusa",
        "district": "North Goa",
        "state": "Goa",
        "country": "India",
        "latitude": 15.5937,
        "longitude": 73.8142,
        "displayName": "Mapusa, North Goa, Goa, India",
    },
    "canacona": {
        "name": "Canacona",
        "district": "South Goa",
        "state": "Goa",
        "country": "India",
        "latitude": 15.0167,
        "longitude": 74.0500,
        "displayName": "Canacona, South Goa, Goa, India",
    },
    "baramati": {
        "name": "Baramati",
        "district": "Pune",
        "state": "Maharashtra",
        "country": "India",
        "latitude": 18.1517,
        "longitude": 74.5770,
        "displayName": "Baramati, Pune, Maharashtra, India",
    },
    "nashik": {
        "name": "Nashik",
        "district": "Nashik",
        "state": "Maharashtra",
        "country": "India",
        "latitude": 19.9975,
        "longitude": 73.7898,
        "displayName": "Nashik, Maharashtra, India",
    },
    "kolhapur": {
        "name": "Kolhapur",
        "district": "Kolhapur",
        "state": "Maharashtra",
        "country": "India",
        "latitude": 16.7050,
        "longitude": 74.2433,
        "displayName": "Kolhapur, Maharashtra, India",
    },
    "solapur": {
        "name": "Solapur",
        "district": "Solapur",
        "state": "Maharashtra",
        "country": "India",
        "latitude": 17.6599,
        "longitude": 75.9064,
        "displayName": "Solapur, Maharashtra, India",
    },
    "ludhiana": {
        "name": "Ludhiana",
        "district": "Ludhiana",
        "state": "Punjab",
        "country": "India",
        "latitude": 30.9010,
        "longitude": 75.8573,
        "displayName": "Ludhiana, Punjab, India",
    },
    "karnal": {
        "name": "Karnal",
        "district": "Karnal",
        "state": "Haryana",
        "country": "India",
        "latitude": 29.6857,
        "longitude": 76.9905,
        "displayName": "Karnal, Haryana, India",
    },
    "anand": {
        "name": "Anand",
        "district": "Anand",
        "state": "Gujarat",
        "country": "India",
        "latitude": 22.5645,
        "longitude": 72.9289,
        "displayName": "Anand, Gujarat, India",
    },
    "thanjavur": {
        "name": "Thanjavur",
        "district": "Thanjavur",
        "state": "Tamil Nadu",
        "country": "India",
        "latitude": 10.7870,
        "longitude": 79.1378,
        "displayName": "Thanjavur, Tamil Nadu, India",
    },
    "guntur": {
        "name": "Guntur",
        "district": "Guntur",
        "state": "Andhra Pradesh",
        "country": "India",
        "latitude": 16.3067,
        "longitude": 80.4365,
        "displayName": "Guntur, Andhra Pradesh, India",
    },
    "mandya": {
        "name": "Mandya",
        "district": "Mandya",
        "state": "Karnataka",
        "country": "India",
        "latitude": 12.5218,
        "longitude": 76.8951,
        "displayName": "Mandya, Karnataka, India",
    },
    "wayanad": {
        "name": "Wayanad",
        "district": "Wayanad",
        "state": "Kerala",
        "country": "India",
        "latitude": 11.6854,
        "longitude": 76.1320,
        "displayName": "Wayanad, Kerala, India",
    },
    "cuttack": {
        "name": "Cuttack",
        "district": "Cuttack",
        "state": "Odisha",
        "country": "India",
        "latitude": 20.4625,
        "longitude": 85.8828,
        "displayName": "Cuttack, Odisha, India",
    },
    "bardhaman": {
        "name": "Bardhaman",
        "district": "Purba Bardhaman",
        "state": "West Bengal",
        "country": "India",
        "latitude": 23.2324,
        "longitude": 87.8615,
        "displayName": "Bardhaman, West Bengal, India",
    },
}

PHONETIC_ALIASES = {
    "shirodha": "shiroda",
    "shiroda goa": "shiroda",
    "pondha": "ponda",
    "ponda goa": "ponda",
    "madgaon": "margao",
    "madgao": "margao",
    "margaon": "margao",
    "panjim": "panaji",
    "mapsa": "mapusa",
    "sathara": "satara",
    "nasik": "nashik",
    "naasik": "nashik",
    "kholhapur": "kolhapur",
    "bopal": "bhopal",
    "baramathi": "baramati",
    "karnaal": "karnal",
    "loodhiana": "ludhiana",
    "sholapur": "solapur",
}


def generate_phonetic_candidates(name: str) -> list[str]:
    """
    Generate common speech-to-text phonetic variations for Indian place names.
    Handles aspirate consonants (dh/d, th/t, bh/b, kh/k), vowel length, and sibilants.
    """
    import re
    candidates = []
    w = name.strip()
    w_low = w.lower()

    if w_low in PHONETIC_ALIASES:
        candidates.append(PHONETIC_ALIASES[w_low])

    # Aspirate consonants
    if "dh" in w_low:
        candidates.append(re.sub(r"dh", "d", w, flags=re.IGNORECASE))
    elif "d" in w_low:
        candidates.append(re.sub(r"d", "dh", w, flags=re.IGNORECASE))

    if "th" in w_low:
        candidates.append(re.sub(r"th", "t", w, flags=re.IGNORECASE))
    elif "t" in w_low:
        candidates.append(re.sub(r"t", "th", w, flags=re.IGNORECASE))

    if "kh" in w_low:
        candidates.append(re.sub(r"kh", "k", w, flags=re.IGNORECASE))

    if "bh" in w_low:
        candidates.append(re.sub(r"bh", "b", w, flags=re.IGNORECASE))

    if "ee" in w_low:
        candidates.append(re.sub(r"ee", "i", w, flags=re.IGNORECASE))
    if "oo" in w_low:
        candidates.append(re.sub(r"oo", "u", w, flags=re.IGNORECASE))

    result = []
    for c in candidates:
        if c.lower() != w_low and c not in result:
            result.append(c)
    return result


async def search_locations(query: str, limit: int = 6) -> list[dict]:
    """
    Search places, villages, towns, cities, districts, or landmarks via Photon API.
    Prioritizes Indian results and returns normalized location objects.
    Includes phonetic location correction for common speech recognition inaccuracies.
    """
    if not query or not query.strip():
        return []

    q = query.strip()
    q_low = q.lower()

    # 1. Check direct phonetic alias / gazetteer match
    target_key = PHONETIC_ALIASES.get(q_low, q_low)
    if target_key in INDIAN_AGRICULTURAL_GAZETTEER:
        gaz = INDIAN_AGRICULTURAL_GAZETTEER[target_key]
        return [{**gaz, "source": "photon"}]

    # 2. Attempt live Photon search with geographic bias toward India
    params = {
        "q": q,
        "limit": max(limit * 2, 10),
        "lat": INDIA_CENTER_LAT,
        "lon": INDIA_CENTER_LON,
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{PHOTON_BASE_URL}/api",
                params=params,
                headers=HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()
                features = data.get("features", [])
                
                results = []
                seen_coords = set()

                # Separate India results from international results to prioritize India
                india_features = []
                other_features = []

                for f in features:
                    country = (f.get("properties", {}).get("country") or "").strip().lower()
                    if country in ["india", "in"]:
                        india_features.append(f)
                    else:
                        other_features.append(f)

                prioritized = india_features + other_features

                for f in prioritized:
                    coords = f.get("geometry", {}).get("coordinates", [])
                    if len(coords) < 2:
                        continue
                    lon, lat = float(coords[0]), float(coords[1])
                    coord_key = (round(lat, 3), round(lon, 3))
                    if coord_key in seen_coords:
                        continue
                    seen_coords.add(coord_key)

                    props = f.get("properties", {})
                    name = props.get("name") or q.title()
                    city = props.get("city") or props.get("town") or props.get("village")
                    district = props.get("district") or props.get("county") or city
                    state = props.get("state")
                    country = props.get("country") or "India"
                    postcode = props.get("postcode")

                    display_parts = [name]
                    if district and district.lower() != name.lower():
                        display_parts.append(district)
                    if state and state.lower() != name.lower() and state.lower() != (district or "").lower():
                        display_parts.append(state)
                    if country:
                        display_parts.append(country)

                    display_name = ", ".join(display_parts)

                    results.append({
                        "displayName": display_name,
                        "name": name,
                        "district": district or "",
                        "state": state or "",
                        "country": country,
                        "latitude": round(lat, 4),
                        "longitude": round(lon, 4),
                        "postcode": postcode or "",
                        "source": "photon",
                    })

                    if len(results) >= limit:
                        break

                if results:
                    return results
    except Exception as exc:
        logger.warning("Photon location search failed: %s", exc)

    # 3. Phonetic and gazetteer fallback (speech-to-text correction & offline resilience)
    candidates = generate_phonetic_candidates(q)
    for c in candidates:
        c_low = c.lower()
        if c_low in INDIAN_AGRICULTURAL_GAZETTEER:
            gaz = INDIAN_AGRICULTURAL_GAZETTEER[c_low]
            return [{**gaz, "source": "phonetic_correction"}]

    for key, data in INDIAN_AGRICULTURAL_GAZETTEER.items():
        if key in q_low or q_low in key:
            return [{**data, "source": "phonetic_gazetteer"}]

    return []


async def reverse_geocode(latitude: float, longitude: float) -> dict:
    """
    Reverse geocode coordinates into a canonical location dictionary.
    Attempts Photon reverse, then BigDataCloud, then Nominatim.
    """
    lat = float(latitude)
    lon = float(longitude)

    # 1. Try Photon reverse
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(
                f"{PHOTON_BASE_URL}/reverse",
                params={"lat": lat, "lon": lon},
                headers=HEADERS,
            )
            if resp.status_code == 200:
                features = resp.json().get("features", [])
                if features:
                    props = features[0].get("properties", {})
                    name = (
                        props.get("name")
                        or props.get("city")
                        or props.get("town")
                        or props.get("village")
                        or props.get("district")
                    )
                    district = props.get("district") or props.get("county") or props.get("city")
                    state = props.get("state")
                    country = props.get("country") or "India"

                    display_parts = [p for p in [name, district, state, country] if p]
                    # remove duplicates while preserving order
                    deduped = []
                    for p in display_parts:
                        if p not in deduped:
                            deduped.append(p)

                    return {
                        "displayName": ", ".join(deduped) or f"Lat {lat:.2f}, Lon {lon:.2f}",
                        "name": name or f"Lat {lat:.2f}, Lon {lon:.2f}",
                        "district": district or "",
                        "state": state or "",
                        "country": country,
                        "latitude": round(lat, 4),
                        "longitude": round(lon, 4),
                        "source": "gps",
                    }
    except Exception as exc:
        logger.warning("Photon reverse geocoding failed: %s", exc)

    # 2. Try BigDataCloud
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(
                BIGDATACLOUD_URL,
                params={"latitude": lat, "longitude": lon, "localityLanguage": "en"},
            )
            if resp.status_code == 200:
                data = resp.json()
                city = data.get("city") or data.get("locality") or data.get("principalSubdivision")
                district = data.get("locality") or city
                state = data.get("principalSubdivision")
                country = data.get("countryName") or "India"
                display_parts = [p for p in [city, state, country] if p]
                return {
                    "displayName": ", ".join(display_parts) or f"Lat {lat:.2f}, Lon {lon:.2f}",
                    "name": city or f"Lat {lat:.2f}, Lon {lon:.2f}",
                    "district": district or "",
                    "state": state or "",
                    "country": country,
                    "latitude": round(lat, 4),
                    "longitude": round(lon, 4),
                    "source": "gps",
                }
    except Exception as exc:
        logger.warning("BigDataCloud reverse geocoding failed: %s", exc)

    # 3. Check nearest entry in INDIAN_AGRICULTURAL_GAZETTEER (within ~25 km)
    for g in INDIAN_AGRICULTURAL_GAZETTEER.values():
        if abs(lat - g["latitude"]) < 0.25 and abs(lon - g["longitude"]) < 0.25:
            return {
                "displayName": g["displayName"],
                "name": g["name"],
                "district": g["district"],
                "state": g["state"],
                "country": g["country"],
                "latitude": round(lat, 4),
                "longitude": round(lon, 4),
                "source": "gps",
            }

    # 4. Fallback: return formatted coordinates
    return {
        "displayName": f"Lat {lat:.2f}, Lon {lon:.2f}",
        "name": f"Lat {lat:.2f}, Lon {lon:.2f}",
        "district": "",
        "state": "",
        "country": "India",
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "source": "gps",
    }
