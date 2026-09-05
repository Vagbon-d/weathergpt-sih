"""
Agricultural Decision and Advisory Service for WeatherGPT.

Provides deterministic, rule-based agronomic evaluations for:
- Pesticide / Fertilizer Spraying
- Field Irrigation
- Crop Harvesting
- Sowing / Seeding

All thresholds are strictly evaluated in Python before any LLM generation.
"""

from typing import Any


def extract_weather_metrics(weather_data: dict[str, Any]) -> dict[str, float]:
    """
    Extract normalized weather metrics from weather_data across current and forecast.
    """
    current = weather_data.get("current", {})
    forecast = weather_data.get("forecast", [])
    today = forecast[0] if forecast else {}
    tomorrow = forecast[1] if len(forecast) > 1 else today

    rain_prob_today = float(today.get("rain_probability") or 0)
    rain_prob_tomorrow = float(tomorrow.get("rain_probability") or 0)
    max_rain_prob = max(rain_prob_today, rain_prob_tomorrow)

    temp_current = float(current.get("temperature_c") or 0)
    temp_max_today = float(today.get("temp_max") or temp_current)
    temp_min_today = float(today.get("temp_min") or temp_current)

    wind_current = float(current.get("wind_kmh") or 0)
    wind_max = float(today.get("wind_max_kmh") or wind_current)

    humidity = float(current.get("humidity_pct") or 0)

    return {
        "rain_prob_today": rain_prob_today,
        "rain_prob_tomorrow": rain_prob_tomorrow,
        "max_rain_prob": max_rain_prob,
        "temp_current": temp_current,
        "temp_max": temp_max_today,
        "temp_min": temp_min_today,
        "wind_current": wind_current,
        "wind_max": wind_max,
        "humidity": humidity,
    }


def evaluate_spray_safety(weather_data: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluate chemical spray safety (pesticides, fungicides, foliar fertilizers).
    - Wind > 15 km/h: Risk of drift to non-target areas.
    - Wind > 20 km/h: Completely unsafe.
    - Rain prob > 40%: Risk of rain washing chemicals off leaves.
    - Temp > 35°C: High evaporation and risk of phytotoxicity (leaf scorch).
    """
    m = extract_weather_metrics(weather_data)
    reasons = []
    status = "SAFE"  # SAFE, CAUTION, UNSAFE

    if m["wind_max"] > 20:
        status = "UNSAFE"
        reasons.append(f"High wind speed ({m['wind_max']:.1f} km/h) will cause severe spray drift.")
    elif m["wind_max"] > 15:
        if status != "UNSAFE":
            status = "CAUTION"
        reasons.append(f"Moderate wind ({m['wind_max']:.1f} km/h) requires drift-reduction nozzles.")

    if m["max_rain_prob"] >= 50:
        status = "UNSAFE"
        reasons.append(f"High chance of rain ({m['max_rain_prob']:.0f}%) will wash away applied chemicals.")
    elif m["max_rain_prob"] >= 35:
        if status != "UNSAFE":
            status = "CAUTION"
        reasons.append(f"Moderate rain probability ({m['max_rain_prob']:.0f}%); rain within 4-6 hours will reduce efficacy.")

    if m["temp_max"] > 35:
        if status != "UNSAFE":
            status = "CAUTION"
        reasons.append(f"High temperature ({m['temp_max']:.1f}°C) may cause rapid evaporation and leaf scorch; spray in early morning.")

    if status == "SAFE":
        reasons.append(f"Wind ({m['wind_max']:.1f} km/h) and rain probability ({m['max_rain_prob']:.0f}%) are within ideal spray limits.")

    return {
        "operation": "spray",
        "status": status,
        "is_safe": status == "SAFE",
        "metrics": m,
        "reasons": reasons,
        "recommendation": (
            "Ideal conditions for spraying." if status == "SAFE"
            else "Exercise caution or spray in calm early morning hours." if status == "CAUTION"
            else "Postpone spraying to avoid chemical loss and environmental drift."
        ),
    }


def evaluate_irrigation_safety(weather_data: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluate field irrigation necessity and safety.
    - Rain prob >= 50% in next 24-48h: Postpone irrigation (prevent waterlogging).
    - Rain prob < 30% & Temp > 32°C: Irrigation recommended, preferably early morning or evening.
    """
    m = extract_weather_metrics(weather_data)
    reasons = []
    status = "RECOMMENDED"

    if m["max_rain_prob"] >= 50:
        status = "POSTPONE"
        reasons.append(f"Upcoming rain ({m['max_rain_prob']:.0f}% chance) will supply natural moisture. Avoid waterlogging and nutrient leaching.")
    elif m["max_rain_prob"] >= 35:
        status = "CAUTION"
        reasons.append(f"Scattered rain is possible ({m['max_rain_prob']:.0f}%). Monitor soil moisture before irrigating.")
    else:
        if m["temp_max"] >= 32:
            reasons.append(f"Warm dry weather ({m['temp_max']:.1f}°C, rain {m['max_rain_prob']:.0f}%). Irrigate in early morning or evening to minimize evaporative loss.")
        else:
            reasons.append(f"Normal moisture demand under mild conditions ({m['temp_max']:.1f}°C). Maintain routine irrigation.")

    return {
        "operation": "irrigation",
        "status": status,
        "is_safe": status != "POSTPONE",
        "metrics": m,
        "reasons": reasons,
        "recommendation": (
            "Delay irrigation; sufficient natural rainfall is expected." if status == "POSTPONE"
            else "Check soil depth moisture before irrigating." if status == "CAUTION"
            else "Light to moderate irrigation recommended in cooler hours."
        ),
    }


def evaluate_harvest_safety(weather_data: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluate harvesting conditions.
    - High rain prob (> 40%): Risk of grain sprouting, moisture damage, fungal infection.
    - Dry sunny conditions (< 25% rain prob): Excellent for harvesting and solar drying.
    """
    m = extract_weather_metrics(weather_data)
    reasons = []
    status = "SAFE"

    if m["max_rain_prob"] >= 45:
        status = "UNSAFE"
        reasons.append(f"High risk of rainfall ({m['max_rain_prob']:.0f}%). Harvested crops risk mould, sprouting, and discoloration.")
    elif m["max_rain_prob"] >= 25:
        status = "CAUTION"
        reasons.append(f"Low-to-moderate rain chance ({m['max_rain_prob']:.0f}%). If harvesting, ensure tarpaulins and covered sheds are ready.")
    else:
        reasons.append(f"Dry sunny weather (rain chance {m['max_rain_prob']:.0f}%). Ideal for field harvesting and open-air drying.")

    return {
        "operation": "harvest",
        "status": status,
        "is_safe": status == "SAFE",
        "metrics": m,
        "reasons": reasons,
        "recommendation": (
            "Clear skies and dry weather: excellent time for harvesting." if status == "SAFE"
            else "Proceed with caution; have protective tarpaulins ready." if status == "CAUTION"
            else "Avoid field harvesting unless crop is at imminent risk. Move harvested produce to dry storage."
        ),
    }


def evaluate_sowing_safety(weather_data: dict[str, Any], crop: str | None = None) -> dict[str, Any]:
    """
    Evaluate sowing / nursery transplanting conditions.
    - Torrential downpour / storms (> 70% rain): Washout risk.
    - Extreme heat (> 40°C): Germination failure risk.
    - Moderate moisture and mild temp: Favorable.
    """
    m = extract_weather_metrics(weather_data)
    reasons = []
    status = "FAVORABLE"

    if m["max_rain_prob"] >= 70:
        status = "UNFAVORABLE"
        reasons.append(f"Heavy rain risk ({m['max_rain_prob']:.0f}%) may wash away seeds or waterlog young seedbeds.")
    elif m["temp_max"] >= 40:
        status = "UNFAVORABLE"
        reasons.append(f"Extreme heat ({m['temp_max']:.1f}°C) severely impairs seed germination and seedling survival.")
    elif m["max_rain_prob"] >= 45:
        status = "CAUTION"
        reasons.append("Sufficient moisture expected, but ensure field drainage channels are open.")
    else:
        reasons.append(f"Temperature ({m['temp_current']:.1f}°C to {m['temp_max']:.1f}°C) and weather conditions are favorable for field prep and sowing.")

    return {
        "operation": "sowing",
        "status": status,
        "is_safe": status in ["FAVORABLE", "CAUTION"],
        "metrics": m,
        "crop": crop or "general",
        "reasons": reasons,
        "recommendation": (
            "Favorable conditions for field preparation and sowing." if status == "FAVORABLE"
            else "Prepare soil and ensure proper drainage before sowing." if status == "CAUTION"
            else "Postpone sowing until extreme heat or heavy rain subsides."
        ),
    }


def generate_daily_action_recommendations(weather_data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Generate deterministic, actionable advice chips ('What should I do today?')
    evaluated from real weather metrics.
    """
    m = extract_weather_metrics(weather_data)
    spray_eval = evaluate_spray_safety(weather_data)
    irr_eval = evaluate_irrigation_safety(weather_data)
    harvest_eval = evaluate_harvest_safety(weather_data)

    actions = []

    # 1. Umbrella
    if m["max_rain_prob"] >= 40:
        actions.append({
            "id": "umbrella_yes",
            "icon": "umbrella",
            "title": "Carry an Umbrella",
            "desc": f"Rain probability is {m['max_rain_prob']:.0f}%. Expect wet conditions.",
            "status": "CAUTION",
        })
    else:
        actions.append({
            "id": "umbrella_no",
            "icon": "sun",
            "title": "No Umbrella Needed",
            "desc": f"Low chance of rain today ({m['max_rain_prob']:.0f}%).",
            "status": "SAFE",
        })

    # 2. Chemical Spraying
    if spray_eval["is_safe"]:
        actions.append({
            "id": "spray_ok",
            "icon": "wind",
            "title": "Suitable for Spraying",
            "desc": f"Gentle wind ({m['wind_max']:.0f} km/h) & safe rain probability.",
            "status": "SAFE",
        })
    else:
        actions.append({
            "id": "spray_delay",
            "icon": "alert",
            "title": "Avoid Chemical Spraying",
            "desc": spray_eval["reasons"][0] if spray_eval["reasons"] else "Adverse weather.",
            "status": "POSTPONE",
        })

    # 3. Irrigation
    if irr_eval["status"] == "POSTPONE":
        actions.append({
            "id": "irrigation_delay",
            "icon": "rain",
            "title": "Postpone Irrigation",
            "desc": f"Upcoming natural rain ({m['max_rain_prob']:.0f}%) will supply soil moisture.",
            "status": "POSTPONE",
        })
    else:
        actions.append({
            "id": "irrigation_ok",
            "icon": "droplet",
            "title": "Irrigate in Cooler Hours",
            "desc": "Recommended in early morning or late evening.",
            "status": "SAFE",
        })

    # 4. Field Work / Outdoor Tasks
    if m["max_rain_prob"] < 40 and m["temp_max"] < 38:
        actions.append({
            "id": "outdoor_good",
            "icon": "sprout",
            "title": "Good for Outdoor Work",
            "desc": "Stable weather conditions across the day.",
            "status": "SAFE",
        })
    else:
        actions.append({
            "id": "outdoor_morning",
            "icon": "sun",
            "title": "Plan Outdoor Work Early",
            "desc": "Rain or high afternoon temperatures expected later.",
            "status": "CAUTION",
        })

    # 5. Crop Drying
    if harvest_eval["is_safe"]:
        actions.append({
            "id": "crop_dry_ok",
            "icon": "sun",
            "title": "Safe to Sun-Dry Crops",
            "desc": "Low moisture and clear skies for grain drying.",
            "status": "SAFE",
        })
    else:
        actions.append({
            "id": "crop_dry_cover",
            "icon": "alert",
            "title": "Keep Harvests Covered",
            "desc": "Elevated moisture/rain risk; avoid open-air drying.",
            "status": "CAUTION",
        })

    # 6. Heat Caution
    if m["temp_max"] >= 35:
        actions.append({
            "id": "heat_alert",
            "icon": "thermometer",
            "title": "Afternoon Heat Caution",
            "desc": f"High reaches {m['temp_max']:.1f}°C. Avoid peak direct sun.",
            "status": "CAUTION",
        })

    return actions


def calculate_best_time_window(hourly_forecast: list[dict[str, Any]], activity: str = "outdoor") -> dict[str, Any]:
    """
    Calculate the optimal time window for outdoor activities or spraying using 24-hour hourly forecast.
    """
    if not hourly_forecast:
        return {
            "window": "Morning hours (6:00 AM - 10:00 AM)",
            "reason": "Generally calmer weather and lower temperatures.",
        }

    # Filter daytime hours (6:00 AM to 6:00 PM)
    candidates = []
    for h in hourly_forecast[:18]:
        time_str = h.get("time", "")
        rain = float(h.get("rain_probability") or 0)
        wind = float(h.get("wind_kmh") or 0)
        temp = float(h.get("temperature_c") or 25)

        # Parse hour
        hour = 8
        try:
            if "T" in time_str:
                hour = int(time_str.split("T")[1].split(":")[0])
        except Exception:
            pass

        if 6 <= hour <= 18:
            score = rain * 2 + (wind if activity == "spray" else 0) + (temp if temp > 32 else 0)
            candidates.append((score, hour, rain, wind, temp))

    if candidates:
        candidates.sort(key=lambda x: x[0])
        best = candidates[0]
        best_hour = best[1]
        start_ampm = f"{best_hour if best_hour <= 12 else best_hour - 12}:00 {'AM' if best_hour < 12 else 'PM'}"
        end_hour = min(best_hour + 3, 18)
        end_ampm = f"{end_hour if end_hour <= 12 else end_hour - 12}:00 {'AM' if end_hour < 12 else 'PM'}"

        period_name = "Morning" if best_hour < 12 else "Afternoon"
        return {
            "window": f"{period_name} ({start_ampm} - {end_ampm})",
            "reason": f"Lowest rain probability ({best[2]:.0f}%) and comfortable conditions.",
        }

    return {
        "window": "Morning hours",
        "reason": "Optimal weather before afternoon heat or showers.",
    }
