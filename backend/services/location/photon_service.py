"""
Photon Geocoding Service for WeatherGPT.

Provides open, high-accuracy location search for Indian villages, towns, cities,
districts, states, landmarks, and PIN codes using the Komoot Photon OpenStreetMap API.
"""

import os
import sys
import re
import urllib.parse
import logging
from typing import Any
import httpx

# Ensure UTF-8 stdout encoding on Windows consoles to prevent cp1252 charmap crashes
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logger = logging.getLogger(__name__)

# Sanitize PHOTON_BASE_URL (remove any trailing slashes or URL query parameters)
_RAW_PHOTON_BASE = os.getenv("PHOTON_BASE_URL", "https://photon.komoot.io").strip()
PHOTON_BASE_URL = _RAW_PHOTON_BASE.split("?")[0].rstrip("/")
PHOTON_API_URL = f"{PHOTON_BASE_URL}/api/"
PHOTON_REVERSE_URL = f"{PHOTON_BASE_URL}/reverse/"

BIGDATACLOUD_URL = "https://api.bigdatacloud.net/data/reverse-geocode-client"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

# Standard non-spoofed User-Agent for OpenStreetMap / Komoot API compliance
HEADERS = {
    "User-Agent": "WeatherGPT/1.0 (Indian Weather Prototype; OpenStreetMap Geocoder)",
    "Accept": "application/json",
}

# Strict whitelist of allowed query parameters by Komoot Photon API
# Note: Never send utm_source, utm_medium, utm_campaign, or browser analytics parameters
ALLOWED_PHOTON_PARAMS = {
    "q", "limit", "lat", "lon", "lang", "osm_tag", "bbox",
    "countrycode", "location_bias_scale", "zoom", "layer",
    "dedupe", "include", "exclude", "geometry", "suggest_addresses", "debug",
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
    "panjim": {
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
    "pondha": "ponda",
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


def sanitize_location_query(query: str) -> str:
    """
    Strips whitespace, tracking parameters, URL components, and invalid characters
    from a location search string.
    """
    if not query:
        return ""
    q = query.strip()

    # If query contains URL parameters or fragments, extract search text
    if "?" in q or "http://" in q or "https://" in q:
        try:
            parsed = urllib.parse.urlparse(q)
            params = urllib.parse.parse_qs(parsed.query)
            if "q" in params and params["q"]:
                q = params["q"][0]
            elif parsed.path:
                q = parsed.path.split("/")[-1]
            else:
                q = q.split("?")[0]
        except Exception:
            q = q.split("?")[0]

    # Remove any tracking parameters matching utm_source, utm_medium, etc.
    q = re.sub(r"\butm_[a-z0-9_]+=[^\s&]+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"\b(?:utm_source|utm_medium|utm_campaign|utm_content|utm_term)\b", "", q, flags=re.IGNORECASE)

    # Clean punctuation and multiple spaces
    q = " ".join(q.split())
    return q


POI_INDICATORS = (
    "health centre", "health center", "primary health centre", "hospital", "clinic",
    "dispensary", "school", "college", "university", "institute", "resort", "hotel",
    "restaurant", "temple", "church", "mosque", "bank", "atm", "studio", "hair studio",
    "shop", "store", "office", "panchayat", "rainwater harvesting", "harvesting",
    "railway station", "bus stand", "bus stop",
)


def _build_location_dict(
    name: str,
    lat: float,
    lon: float,
    city: str | None = None,
    district: str | None = None,
    state: str | None = None,
    country: str = "India",
    postcode: str | None = None,
    source: str = "photon",
) -> dict[str, Any]:
    """
    Standardizes location records into canonical format required by Section 4 & Section 7.
    Distinguishes POI name from the authoritative administrative weather location.
    Ensures postal PIN codes never become the primary location name.
    """
    str_name = str(name or "").strip()
    is_numeric_pin = bool(re.match(r"^\d{4,6}$", str_name))
    if is_numeric_pin and not postcode:
        postcode = str_name

    # Derive geographic administrative base name
    admin_name_candidates = [city, district, state]
    geo_name = None
    for cand in admin_name_candidates:
        if cand and str(cand).strip() and not re.match(r"^\d{4,6}$", str(cand).strip()):
            geo_name = str(cand).strip()
            break

    if is_numeric_pin:
        primary_name = geo_name or "Local Area"
    else:
        primary_name = str_name or geo_name or f"Lat {lat:.2f}, Lon {lon:.2f}"

    name_lower = primary_name.lower()
    is_poi = any(poi_term in name_lower for poi_term in POI_INDICATORS)

    # Derive clean administrative weather location
    admin_parts = []
    admin_seen = set()
    for item in [city, district, state, country]:
        if item and str(item).strip():
            c_item = str(item).strip()
            # Do NOT include numeric postcodes in administrative location strings
            if re.match(r"^\d{4,6}$", c_item):
                continue
            i_low = c_item.lower()
            if i_low not in admin_seen:
                admin_seen.add(i_low)
                admin_parts.append(c_item)

    if not is_poi and not is_numeric_pin:
        if primary_name and primary_name.lower() not in admin_seen:
            admin_parts.insert(0, primary_name)

    if not admin_parts:
        admin_parts = [primary_name, country] if country else [primary_name]

    admin_label = ", ".join(admin_parts)
    weather_location = admin_label

    # Display label: Primary name + administrative context without raw PIN
    display_parts = []
    d_seen = set()
    for item in [primary_name, city, district, state, country]:
        if item and str(item).strip():
            c_item = str(item).strip()
            if re.match(r"^\d{4,6}$", c_item):
                continue
            i_low = c_item.lower()
            if i_low not in d_seen:
                d_seen.add(i_low)
                display_parts.append(c_item)
    label = ", ".join(display_parts) if display_parts else admin_label

    short_label = f"{primary_name}, {state}" if state and str(state).strip() and str(state).strip().lower() not in primary_name.lower() else primary_name
    display_name = f"{label} ({postcode})" if postcode and str(postcode) not in label else label

    return {
        "id": f"{round(float(lat), 4)},{round(float(lon), 4)}",
        "name": primary_name,
        "admin_name": geo_name or primary_name,
        "short_label": short_label,
        "label": label,
        "displayName": display_name,
        "weather_location": weather_location,
        "admin_label": admin_label,
        "city": city or "",
        "district": district or "",
        "state": state or "",
        "country": country or "India",
        "postcode": postcode or "",
        "lat": round(float(lat), 4),
        "lon": round(float(lon), 4),
        "latitude": round(float(lat), 4),
        "longitude": round(float(lon), 4),
        "is_poi": is_poi,
        "poi_name": str_name if is_poi else None,
        "source": source,
    }


# Set of Indian geographic cues derived from country names and all official Indian States/UTs
from services.rag_service import INDIAN_STATES

INDIAN_GEOGRAPHIC_CUES = {"india", "bharat", "ind", "in"} | INDIAN_STATES


def _score_photon_feature(feature: dict, cleaned_query: str) -> float:
    """
    Ranks Photon search results to:
    1. Prioritize administrative entities (city, town, village, district) over commercial POIs (hotels, shops, hair studios).
    2. Strongly prefer Indian results when Indian geographic cues or places are searched.
    3. Match query keywords to name, city, district, and state.
    """
    props = feature.get("properties", {})
    osm_key = (props.get("osm_key") or "").lower()
    osm_value = (props.get("osm_value") or "").lower()
    f_type = (props.get("type") or "").lower()
    country = (props.get("country") or "").lower()
    country_code = (props.get("countrycode") or "").lower()
    name = (props.get("name") or "").lower()
    state = (props.get("state") or "").lower()
    city = (props.get("city") or "").lower()
    district = (props.get("district") or props.get("county") or "").lower()

    q_lower = cleaned_query.lower()
    q_words = [w for w in re.findall(r"\w+", q_lower) if len(w) > 1]
    has_indian_cue = any(cue in q_lower for cue in INDIAN_GEOGRAPHIC_CUES)

    score = 100.0
    is_india = country in ["india", "in"] or country_code in ["in", "ind"]

    # 1. Geographic preference
    if is_india:
        score += 300.0
    else:
        if has_indian_cue:
            score -= 1000.0  # Discard/demote foreign results when query is Indian
        else:
            score -= 150.0

    # 2. Administrative places (city, town, village, district) vs Commercial POIs
    admin_place_keys = {"place", "boundary"}
    admin_place_values = {
        "city", "town", "village", "hamlet", "suburb", "district",
        "administrative", "postcode", "county", "state", "municipality"
    }
    poi_keys = {"amenity", "shop", "tourism", "craft", "office", "commercial", "building", "highway", "leisure", "landuse"}

    if osm_key in admin_place_keys or osm_value in admin_place_values or f_type in ["city", "town", "village", "district", "administrative"]:
        score += 250.0
        if osm_value in ["city", "town", "village", "district"] or f_type in ["city", "town", "village", "district"]:
            score += 100.0
    elif osm_key in poi_keys or f_type in ["house", "street"]:
        score -= 180.0

    # 3. Query string matching bonuses
    for qw in q_words:
        if qw in ["india"]:
            continue
        if qw == name:
            score += 160.0
        elif name.startswith(qw):
            score += 90.0
        elif qw in name:
            score += 40.0

        if qw == city or qw in city:
            score += 60.0
        if qw == district or qw in district:
            score += 50.0
        if qw == state or qw in state:
            score += 70.0

    # 4. Dynamic phonetic alias match
    for alias_src, alias_target in PHONETIC_ALIASES.items():
        if alias_src in q_lower and (alias_target in name or alias_target in city):
            score += 180.0
            break

    return score


async def search_locations(query: str, limit: int = 6) -> list[dict]:
    """
    Search places, villages, towns, cities, districts, states, PIN codes, or landmarks via Photon API.
    Prioritizes Indian results and returns normalized location objects.
    Includes phonetic location correction and agricultural gazetteer fallback.
    """
    cleaned_query = sanitize_location_query(query)
    if not cleaned_query or len(cleaned_query) < 2:
        return []

    q_low = cleaned_query.lower()
    has_indian_cue = any(cue in q_low for cue in INDIAN_GEOGRAPHIC_CUES)

    # 1. Attempt live Photon search with geographic bias toward India
    # Whitelisted parameters ONLY. Never send utm_* or tracking parameters.
    raw_params = {
        "q": cleaned_query,
        "limit": max(limit * 3, 15),
        "lat": INDIA_CENTER_LAT,
        "lon": INDIA_CENTER_LON,
    }
    photon_params = {k: v for k, v in raw_params.items() if k in ALLOWED_PHOTON_PARAMS}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                PHOTON_API_URL,
                params=photon_params,
                headers=HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()
                features = data.get("features", [])

                # Filter foreign contamination: strictly discard non-Indian features when Indian cues exist
                if has_indian_cue:
                    features = [
                        f for f in features
                        if (f.get("properties", {}).get("country") or "").strip().lower() in ["india", "in"]
                        or (f.get("properties", {}).get("countrycode") or "").strip().lower() in ["in", "ind"]
                    ]
                elif any((f.get("properties", {}).get("country") or "").strip().lower() in ["india", "in"] for f in features):
                    # If any Indian results exist, prioritize Indian features only
                    features = [
                        f for f in features
                        if (f.get("properties", {}).get("country") or "").strip().lower() in ["india", "in"]
                        or (f.get("properties", {}).get("countrycode") or "").strip().lower() in ["in", "ind"]
                    ]

                # Score and rank features to prioritize administrative entities over POIs
                scored_features = sorted(
                    features,
                    key=lambda f: _score_photon_feature(f, cleaned_query),
                    reverse=True,
                )

                results = []
                seen_coords = set()

                for f in scored_features:
                    coords = f.get("geometry", {}).get("coordinates", [])
                    if len(coords) < 2:
                        continue
                    try:
                        lon, lat = float(coords[0]), float(coords[1])
                    except (ValueError, TypeError):
                        continue

                    coord_key = (round(lat, 3), round(lon, 3))
                    if coord_key in seen_coords:
                        continue
                    seen_coords.add(coord_key)

                    props = f.get("properties", {})
                    name = props.get("name") or props.get("city") or props.get("district") or cleaned_query.title()
                    city = props.get("city") or props.get("town") or props.get("village")
                    district = props.get("district") or props.get("county")
                    state = props.get("state")
                    country = props.get("country") or "India"
                    postcode = props.get("postcode")

                    item = _build_location_dict(
                        name=name,
                        lat=lat,
                        lon=lon,
                        city=city,
                        district=district,
                        state=state,
                        country=country,
                        postcode=postcode,
                        source="photon",
                    )
                    results.append(item)

                    if len(results) >= limit:
                        break

                if results:
                    return results
    except Exception as exc:
        logger.warning("Live Photon location search failed (%s); attempting gazetteer fallback.", exc)

    # 2. Fallback: Check direct phonetic alias / gazetteer match
    target_key = PHONETIC_ALIASES.get(q_low, q_low)
    if target_key in INDIAN_AGRICULTURAL_GAZETTEER:
        gaz = INDIAN_AGRICULTURAL_GAZETTEER[target_key]
        return [_build_location_dict(
            name=gaz["name"],
            lat=gaz["latitude"],
            lon=gaz["longitude"],
            district=gaz.get("district"),
            state=gaz.get("state"),
            country=gaz.get("country", "India"),
            source="gazetteer",
        )]

    # Normalized match without punctuation
    norm_q = re.sub(r"[,.\-_/]+", " ", q_low).strip()
    norm_q = " ".join(norm_q.split())
    for k, v in INDIAN_AGRICULTURAL_GAZETTEER.items():
        norm_k = re.sub(r"[,.\-_/]+", " ", k).strip()
        norm_k = " ".join(norm_k.split())
        if norm_q == norm_k or (len(norm_k) > 4 and norm_k in norm_q):
            return [_build_location_dict(
                name=v["name"],
                lat=v["latitude"],
                lon=v["longitude"],
                district=v.get("district"),
                state=v.get("state"),
                country=v.get("country", "India"),
                source="gazetteer",
            )]


    # 3. Phonetic variation fallback
    candidates = generate_phonetic_candidates(cleaned_query)
    for c in candidates:
        c_low = c.lower()
        if c_low in INDIAN_AGRICULTURAL_GAZETTEER:
            gaz = INDIAN_AGRICULTURAL_GAZETTEER[c_low]
            return [_build_location_dict(
                name=gaz["name"],
                lat=gaz["latitude"],
                lon=gaz["longitude"],
                district=gaz.get("district"),
                state=gaz.get("state"),
                country=gaz.get("country", "India"),
                source="phonetic_correction",
            )]

    for key, data in INDIAN_AGRICULTURAL_GAZETTEER.items():
        if key == q_low or (len(q_low) >= 4 and key in q_low):
            return [_build_location_dict(
                name=data["name"],
                lat=data["latitude"],
                lon=data["longitude"],
                district=data.get("district"),
                state=data.get("state"),
                country=data.get("country", "India"),
                source="phonetic_gazetteer",
            )]

    return []


async def reverse_geocode(latitude: float, longitude: float) -> dict:
    """
    Reverse geocode coordinates into a canonical location dictionary.
    Attempts Photon reverse, then BigDataCloud, then Nominatim, then agricultural gazetteer.
    """
    lat = float(latitude)
    lon = float(longitude)

    # 1. Try Photon reverse
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(
                PHOTON_REVERSE_URL,
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
                    city = props.get("city") or props.get("town") or props.get("village")
                    district = props.get("district") or props.get("county") or city
                    state = props.get("state")
                    country = props.get("country") or "India"
                    postcode = props.get("postcode")

                    return _build_location_dict(
                        name=name or f"Lat {lat:.2f}, Lon {lon:.2f}",
                        lat=lat,
                        lon=lon,
                        city=city,
                        district=district,
                        state=state,
                        country=country,
                        postcode=postcode,
                        source="gps",
                    )
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
                postcode = data.get("postcode")

                return _build_location_dict(
                    name=city or f"Lat {lat:.2f}, Lon {lon:.2f}",
                    lat=lat,
                    lon=lon,
                    city=city,
                    district=district,
                    state=state,
                    country=country,
                    postcode=postcode,
                    source="gps",
                )
    except Exception as exc:
        logger.warning("BigDataCloud reverse geocoding failed: %s", exc)

    # 3. Check nearest entry in INDIAN_AGRICULTURAL_GAZETTEER (within ~25 km)
    for g in INDIAN_AGRICULTURAL_GAZETTEER.values():
        if abs(lat - g["latitude"]) < 0.25 and abs(lon - g["longitude"]) < 0.25:
            return _build_location_dict(
                name=g["name"],
                lat=g["latitude"],
                lon=g["longitude"],
                district=g.get("district"),
                state=g.get("state"),
                country=g.get("country", "India"),
                source="gps",
            )

    # 4. Fallback: return formatted coordinates
    return _build_location_dict(
        name=f"Lat {lat:.2f}, Lon {lon:.2f}",
        lat=lat,
        lon=lon,
        country="India",
        source="gps",
    )
