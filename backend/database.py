"""
WeatherGPT Persistent Database Layer (Smart India Hackathon SIH26068).

Implements SQLite-backed storage for farmer profiles and Tier-2 profile lookup
using 'weathergpt.db'.
"""

from __future__ import annotations

import os
import re
import sqlite3
import urllib.parse
from datetime import datetime, timezone
from typing import Any

DB_PATH = os.path.join(os.path.dirname(__file__), "weathergpt.db")


def normalize_phone(phone: str) -> str:
    """
    Strips URL encoding (%2B), whitespace, hyphens, and standardizes to +91XXXXXXXXXX.
    Handles '8806675887', '08806675887', '+91 8806675887', '%2B918806675887'.
    """
    if not phone:
        return ""
    # Unquote URL encoding like %2B
    decoded = urllib.parse.unquote(str(phone)).strip()
    digits = re.sub(r"\D", "", decoded)
    if len(digits) == 10:
        return f"+91{digits}"
    elif len(digits) == 11 and digits.startswith("0"):
        return f"+91{digits[1:]}"
    elif len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    elif len(digits) > 10 and not decoded.startswith("+"):
        return f"+{digits}"
    elif decoded.startswith("+"):
        return f"+{digits}"
    return f"+91{digits}" if len(digits) >= 10 else decoded


def sanitize_phone_number(phone: str) -> str:
    """Alias for backwards compatibility."""
    return normalize_phone(phone)


def get_db_connection() -> sqlite3.Connection:
    """Open an SQLite connection with Row mapping."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Initializes the 'farmers' SQLite table schema and seeds benchmark profiles.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS farmers (
            phone_number TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            village_district TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'Maharashtra',
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            primary_crop TEXT NOT NULL DEFAULT 'Wheat',
            preferred_language TEXT NOT NULL DEFAULT 'Hindi',
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS _db_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cursor.execute("SELECT value FROM _db_meta WHERE key = 'seeded'")
    is_seeded = cursor.fetchone()

    if not is_seeded:
        seed_farmers = [
            (
                "+918806675887",
                "Kashinath Chavan",
                "Haveli, Pune",
                "Maharashtra",
                18.5204,
                73.8567,
                "Wheat",
                "Hindi",
                datetime.now(timezone.utc).isoformat(),
            ),
            (
                "+919527436232",
                "Gopal Naik",
                "Ponda",
                "Goa",
                15.4010,
                74.0064,
                "Cotton",
                "Marathi",
                datetime.now(timezone.utc).isoformat(),
            ),
            (
                "+919876543210",
                "Ramesh Sahu",
                "Sambalpur",
                "Odisha",
                21.4678,
                83.9812,
                "Paddy",
                "Odia",
                datetime.now(timezone.utc).isoformat(),
            ),
        ]

        for farmer in seed_farmers:
            cursor.execute("""
                INSERT OR IGNORE INTO farmers (
                    phone_number, name, village_district, state, latitude, longitude,
                    primary_crop, preferred_language, registered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, farmer)

        cursor.execute("INSERT OR REPLACE INTO _db_meta (key, value) VALUES ('seeded', '1')")

    conn.commit()
    conn.close()


def init_farmers_db() -> None:
    """Alias for backwards compatibility."""
    init_db()


def register_farmer(
    phone: str,
    name: str,
    village_district: str,
    state: str,
    lat: float,
    lon: float,
    crop: str = "Wheat",
    language: str = "Hindi",
) -> dict[str, Any]:
    """Upsert farmer profile in SQLite."""
    init_db()
    clean_phone = normalize_phone(phone)
    conn = get_db_connection()
    cursor = conn.cursor()

    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        INSERT INTO farmers (
            phone_number, name, village_district, state, latitude, longitude,
            primary_crop, preferred_language, registered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(phone_number) DO UPDATE SET
            name=excluded.name,
            village_district=excluded.village_district,
            state=excluded.state,
            latitude=excluded.latitude,
            longitude=excluded.longitude,
            primary_crop=excluded.primary_crop,
            preferred_language=excluded.preferred_language,
            registered_at=excluded.registered_at
    """, (clean_phone, name.strip(), village_district.strip(), state.strip(), float(lat), float(lon), crop.strip(), language.strip(), now_iso))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "phone_number": clean_phone,
        "name": name,
        "village_district": village_district,
        "state": state,
        "latitude": float(lat),
        "longitude": float(lon),
        "primary_crop": crop,
        "preferred_language": language,
        "registered_at": now_iso,
    }


def register_user(
    phone_number: str,
    name: str,
    village_district: str,
    latitude: float,
    longitude: float,
    primary_crop: str = "Wheat",
    preferred_language: str = "Hindi",
    state: str = "Maharashtra",
) -> dict[str, Any]:
    """Compatibility alias for register_farmer."""
    return register_farmer(
        phone=phone_number,
        name=name,
        village_district=village_district,
        state=state,
        lat=latitude,
        lon=longitude,
        crop=primary_crop,
        language=preferred_language,
    )


def get_farmer(phone: str) -> dict[str, Any] | None:
    """Normalize phone and return farmer profile dict or None."""
    init_db()
    clean_phone = normalize_phone(phone)
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM farmers WHERE phone_number = ?", (clean_phone,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "phone_number": row["phone_number"],
        "name": row["name"],
        "village_district": row["village_district"],
        "state": row["state"] if "state" in row.keys() else "Maharashtra",
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "primary_crop": row["primary_crop"],
        "preferred_language": row["preferred_language"],
        "registered_at": row["registered_at"],
    }


def get_user_profile(phone: str) -> dict[str, Any] | None:
    """Compatibility alias for get_farmer."""
    return get_farmer(phone)


def get_all_farmers() -> list[dict[str, Any]]:
    """Retrieve all registered farmers sorted by most recent."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM farmers ORDER BY registered_at DESC")
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "phone_number": r["phone_number"],
            "name": r["name"],
            "village_district": r["village_district"],
            "state": r["state"] if "state" in r.keys() else "Maharashtra",
            "latitude": float(r["latitude"]),
            "longitude": float(r["longitude"]),
            "primary_crop": r["primary_crop"],
            "preferred_language": r["preferred_language"],
            "registered_at": r["registered_at"],
        }
        for r in rows
    ]


def clear_all_farmers(clear_caller_profiles: bool = True) -> int:
    """Delete all records from the farmers table and return count."""
    init_db()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM farmers")
        deleted_count = cursor.rowcount
        conn.commit()
        return int(deleted_count) if deleted_count is not None and deleted_count >= 0 else 0
    except Exception as exc:
        conn.rollback()
        raise exc
    finally:
        conn.close()


def reseed_default_farmers() -> int:
    """Re-seed the 3 benchmark demo farmers."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM _db_meta WHERE key = 'seeded'")
    conn.commit()
    conn.close()
    init_db()
    return len(get_all_farmers())


# Initialize on module import
init_db()
