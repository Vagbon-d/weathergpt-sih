"""
WeatherGPT Management Portal & Telephony Simulation Hub (Smart India Hackathon SIH26068).

A unified Streamlit dashboard providing:
1. Tab 1: "🌦️ Conversational WeatherGPT" - Multi-lingual conversational weather assistant grounded in live Open-Meteo & IMD rules.
2. Tab 2: "🌾 Farmer Offline Registration Portal" - Offline farmer registration with geocoding, SQLite persistence, and live directory.
3. Tab 3: "📱 MacroDroid GSM Gateway Monitor" - Action sequence visual guide and live telephony testing console.
"""

from __future__ import annotations

import os
import sys
import json
import importlib
import requests
import streamlit as st
try:
    import pandas as pd
except Exception:
    pd = None


# Add backend directory to path
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database
import weather_engine
import free_ivr_server

importlib.reload(database)
importlib.reload(weather_engine)
importlib.reload(free_ivr_server)

st.set_page_config(
    page_title="WeatherGPT Portal | SIH26068",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #1b5e20;
        margin-bottom: 0.1rem;
    }
    .sub-title {
        font-size: 1.0rem;
        color: #555;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: #f1f8e9;
        border-left: 5px solid #4caf50;
        padding: 14px;
        border-radius: 6px;
        margin-bottom: 12px;
    }
    .alert-card-green {
        background: #e8f5e9;
        border-left: 5px solid #2e7d32;
        padding: 12px;
        border-radius: 6px;
    }
    .alert-card-yellow {
        background: #fffde7;
        border-left: 5px solid #fbc02d;
        padding: 12px;
        border-radius: 6px;
    }
    .alert-card-orange {
        background: #fff3e0;
        border-left: 5px solid #ef6c00;
        padding: 12px;
        border-radius: 6px;
    }
    .alert-card-red {
        background: #ffebee;
        border-left: 5px solid #c62828;
        padding: 12px;
        border-radius: 6px;
    }
    .sms-box {
        background: #212121;
        color: #e0e0e0;
        font-family: 'Consolas', 'Courier New', monospace;
        padding: 14px;
        border-radius: 8px;
        border: 1px solid #424242;
        font-size: 0.95rem;
        line-height: 1.5;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🌾 WeatherGPT: Telephony Bridge & Advisory Hub</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Smart India Hackathon SIH26068 — Zero-Internet Conversational AI for Weather, Alerts & Agricultural Agromet</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("⚙️ Telephony Gateway Status")
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        st.success("✅ Groq Whisper & LLaMA Active")
    else:
        st.warning("⚠️ GROQ_API_KEY not configured in .env")

    st.info("📞 **Webhook Endpoint:** `/webhook/phone-call` (Port 8000)")
    st.divider()

    st.markdown("### 📊 Database Status")
    farmers_list = database.get_all_farmers()
    st.metric("Registered Farmers", len(farmers_list))

    st.markdown("### 📍 Quick Demo Profiles")
    st.write("• **Kashinath Chavan**: `+918806675887` (Pune)")
    st.write("• **Gopal Naik**: `+919527436232` (Ponda, Goa)")
    st.write("• **Ramesh Sahu**: `+919876543210` (Sambalpur)")


tab_chat, tab_register, tab_gateway = st.tabs([
    "🌦️ Conversational WeatherGPT",
    "🌾 Farmer Offline Registration Portal",
    "📱 MacroDroid GSM Gateway Monitor",
])


# ===========================================================================
# TAB 1: Conversational WeatherGPT (Chat & Live IMD Rules)
# ===========================================================================
with tab_chat:
    st.subheader("🌦️ Conversational Weather & Crop Advisory Assistant")
    st.write("Grounded exclusively in live Numerical Weather Prediction (NWP) feeds and official IMD/ICAR standards.")

    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = [
            {"role": "assistant", "content": "Namaste! I am WeatherGPT. Ask me any weather or crop spraying question in Hindi, Marathi, Odia, or English."}
        ]

    # Farmer profile context bar
    all_f = database.get_all_farmers()
    farmer_options = ["None (Extract from query text)"] + [f"{f['name']} ({f['village_district']}, {f['state']} - {f['primary_crop']}) [{f['phone_number']}]" for f in all_f]
    selected_farmer_opt = st.selectbox("👤 Caller Profile Context (Simulate Registered Farm Coordinates)", farmer_options, index=0)

    selected_farmer = None
    if selected_farmer_opt != "None (Extract from query text)":
        phone_selected = selected_farmer_opt.split("[")[-1].replace("]", "").strip()
        selected_farmer = database.get_farmer(phone_selected)
        if selected_farmer:
            st.caption(f"🌾 Grounded to **{selected_farmer['name']}**'s Farm at `({selected_farmer['latitude']:.6f}, {selected_farmer['longitude']:.6f})` | Crop: **{selected_farmer['primary_crop']}**")

    for msg in st.session_state["chat_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Ask a question, e.g., 'क्या कल बारिश होगी?' or 'Will it rain on cotton in Ponda today?'")

    if user_input:
        st.session_state["chat_messages"].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Extracting query intent & fetching live IMD NWP telemetry..."):
                entities = free_ivr_server.extract_spoken_entities(user_input)
                spoken_loc = entities.get("location")
                spoken_crop = entities.get("crop")
                lang_name = entities.get("language") or (selected_farmer["preferred_language"] if selected_farmer else "Hindi")

                # Resolve coordinates
                if spoken_loc:
                    geo = weather_engine.geocode_location(spoken_loc)
                    if geo:
                        lat = geo["lat"]
                        lon = geo["lon"]
                        resolved_loc = f"{geo['name']}, {geo['state']}"
                    else:
                        lat = selected_farmer["latitude"] if selected_farmer else 18.5204
                        lon = selected_farmer["longitude"] if selected_farmer else 73.8567
                        resolved_loc = spoken_loc
                elif selected_farmer:
                    lat = selected_farmer["latitude"]
                    lon = selected_farmer["longitude"]
                    resolved_loc = f"{selected_farmer['village_district']}, {selected_farmer['state']}"
                else:
                    lat = 18.5204
                    lon = 73.8567
                    resolved_loc = "Pune, Maharashtra"

                crop_name = spoken_crop or (selected_farmer["primary_crop"] if selected_farmer else "General Crop")

                metrics = weather_engine.fetch_live_imd_metrics(lat, lon)
                verified = free_ivr_server.verify_and_synthesize_sms(
                    user_query=user_input,
                    location_name=resolved_loc,
                    crop=crop_name,
                    language=lang_name,
                    metrics=metrics,
                )


                reply_sms = verified.get("sms_advisory", "")
                reason = verified.get("verification_reason", "")

                st.markdown(f"**Advisory:**\n\n{reply_sms}")

                # Telemetry Cards
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Current Temp", f"{metrics['current_temp']} °C")
                col2.metric("Rainfall (12h)", f"{metrics['total_rain_mm_12h']} mm", metrics['imd_rainfall_cat'])
                col3.metric("Rain Probability", f"{metrics['max_rain_prob_12h']:.0f} %")
                col4.metric("Peak Wind Speed", f"{metrics['max_wind_kmh_12h']} km/h")

                verdict_color = "alert-card-green" if metrics["safe_to_spray"] else "alert-card-red"
                st.markdown(f"""
                <div class="{verdict_color}">
                    <b>ICAR Agromet Spraying Advisory:</b> {metrics['icar_spraying_verdict']}
                </div>
                """, unsafe_allow_html=True)

                st.caption(f"📍 Coordinates: ({lat:.4f}, {lon:.4f}) | Verification: {reason}")

                st.session_state["chat_messages"].append({"role": "assistant", "content": reply_sms})


# ===========================================================================
# TAB 2: Farmer Offline Registration Portal (With Exact GPS & Live Location)
# ===========================================================================
with tab_register:
    st.subheader("🌾 Rural Farmer Registration (High-Precision GPS & Live Location)")
    st.write("Register farmers with exact coordinates so incoming calls from their feature-phones are immediately resolved with meter-level meteorological accuracy.")

    # Ingest Live GPS from URL parameters if redirected by the browser HTML5 Geolocation widget
    if "gps_lat" in st.query_params and "gps_lon" in st.query_params:
        try:
            detected_lat = float(st.query_params["gps_lat"])
            detected_lon = float(st.query_params["gps_lon"])
            st.session_state["reg_lat"] = detected_lat
            st.session_state["reg_lon"] = detected_lon
            rev_info = weather_engine.reverse_geocode(detected_lat, detected_lon)
            if rev_info:
                st.session_state["reg_village"] = rev_info["village_district"]
                st.session_state["reg_state"] = rev_info["state"]
            # Clear params from URL
            del st.query_params["gps_lat"]
            del st.query_params["gps_lon"]
            if "gps_acc" in st.query_params:
                del st.query_params["gps_acc"]
            st.success(f"📍 Live GPS detected: ({detected_lat:.6f}, {detected_lon:.6f})")
        except Exception as e:
            st.warning(f"GPS ingestion warning: {e}")

    # Set default session state values if not present
    if "reg_lat" not in st.session_state:
        st.session_state["reg_lat"] = 18.520400
    if "reg_lon" not in st.session_state:
        st.session_state["reg_lon"] = 73.856700
    if "reg_village" not in st.session_state:
        st.session_state["reg_village"] = ""
    if "reg_state" not in st.session_state:
        st.session_state["reg_state"] = "Maharashtra"

    # Live Device Location Action Box
    st.markdown("##### 📍 Step 1: Capture Farm Location (Live GPS or Search)")
    loc_btn_col1, loc_btn_col2 = st.columns([1, 1])

    with loc_btn_col1:
        # Browser Geolocation Button using embedded HTML5 Geolocation API
        st.components.v1.html("""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            <button onclick="getDeviceLocation()" style="
                background: linear-gradient(135deg, #2e7d32, #1b5e20);
                color: white;
                border: none;
                padding: 10px 18px;
                font-size: 14px;
                font-weight: 600;
                border-radius: 6px;
                cursor: pointer;
                box-shadow: 0 2px 5px rgba(0,0,0,0.2);
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            ">
                <span>📍</span> Detect My Live Device GPS Location
            </button>
            <div id="gps-status" style="font-size: 12px; color: #555; margin-top: 5px; text-align: center;"></div>
        </div>
        <script>
        function getDeviceLocation() {
            const status = document.getElementById('gps-status');
            if (!navigator.geolocation) {
                status.innerText = "Geolocation not supported by this browser.";
                return;
            }
            status.innerText = "Requesting device GPS coordinates...";
            navigator.geolocation.getCurrentPosition(
                function(pos) {
                    const lat = pos.coords.latitude;
                    const lon = pos.coords.longitude;
                    const acc = pos.coords.accuracy;
                    status.innerText = "GPS Acquired! Updating form...";
                    const url = new URL(window.parent.location.href);
                    url.searchParams.set("gps_lat", lat);
                    url.searchParams.set("gps_lon", lon);
                    url.searchParams.set("gps_acc", acc);
                    window.parent.location.href = url.toString();
                },
                function(err) {
                    status.innerText = "GPS Error: " + err.message;
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
            );
        }
        </script>
        """, height=70)

    with loc_btn_col2:
        st.info("💡 Click **'Detect My Live Device GPS Location'** on a mobile or laptop, or manually enter village/coordinates below.")

    # Coordinate & Address Inputs
    coord_col1, coord_col2, coord_col3 = st.columns([1.5, 1.5, 1])
    with coord_col1:
        current_lat = st.number_input(
            "🌐 Exact Farm Latitude (GPS Decimal)",
            value=float(st.session_state["reg_lat"]),
            format="%.6f",
            min_value=-90.0,
            max_value=90.0,
            step=0.0001,
            help="High-precision latitude from GPS or surveyor.",
        )
    with coord_col2:
        current_lon = st.number_input(
            "🌐 Exact Farm Longitude (GPS Decimal)",
            value=float(st.session_state["reg_lon"]),
            format="%.6f",
            min_value=-180.0,
            max_value=180.0,
            step=0.0001,
            help="High-precision longitude from GPS or surveyor.",
        )
    with coord_col3:
        st.write("")
        st.write("")
        if st.button("🔄 Reverse-Geocode GPS", use_container_width=True, help="Fetch Village & District from current Lat/Lon"):
            with st.spinner("Querying OpenStreetMap Nominatim..."):
                rev = weather_engine.reverse_geocode(current_lat, current_lon)
                if rev:
                    st.session_state["reg_lat"] = current_lat
                    st.session_state["reg_lon"] = current_lon
                    st.session_state["reg_village"] = rev["village_district"]
                    st.session_state["reg_state"] = rev["state"]
                    st.success(f"Resolved: {rev['village_district']}, {rev['state']}")
                    st.rerun()
                else:
                    st.warning("Could not reverse-geocode coordinates.")

    st.markdown("##### 👤 Step 2: Farmer & Agronomic Details")
    reg_col1, reg_col2 = st.columns(2)

    with reg_col1:
        phone_input = st.text_input("📱 Phone Number (with or without +91)", value="+91", help="Accepts 10-digit or E.164 numbers")
        name_input = st.text_input("👤 Farmer Full Name", placeholder="e.g. Ramesh Patel")
        crop_input = st.selectbox(
            "🌱 Primary Crop",
            ["Wheat", "Cotton", "Paddy", "Sugarcane", "Soybean", "Maize", "Groundnut", "Gram / Chickpea", "Tomato", "Onion"]
        )

    with reg_col2:
        village_input = st.text_input(
            "📍 Village / Gram Panchayat / Taluka",
            value=st.session_state.get("reg_village", ""),
            placeholder="e.g. Farmagudi, Ponda or Haveli, Pune",
        )
        state_list = [
            "Maharashtra", "Goa", "Odisha", "Gujarat", "Punjab", "Haryana",
            "Karnataka", "Madhya Pradesh", "Uttar Pradesh", "Rajasthan",
            "Tamil Nadu", "Andhra Pradesh", "Telangana", "Kerala", "West Bengal", "Bihar"
        ]
        default_state_idx = state_list.index(st.session_state.get("reg_state", "Maharashtra")) if st.session_state.get("reg_state", "Maharashtra") in state_list else 0
        state_input = st.selectbox("🏛️ State", state_list, index=default_state_idx)
        lang_input = st.selectbox("🗣️ Preferred Language", ["Hindi", "Marathi", "Odia", "English", "Gujarati", "Bengali"])

    # Forward Geocoding Helper
    search_col1, search_col2 = st.columns([3, 1])
    with search_col2:
        if st.button("🔍 Pinpoint from Village / PIN", use_container_width=True, help="Search OSM Nominatim for exact village coordinates"):
            if village_input:
                with st.spinner("Pinpointing exact village coordinates..."):
                    geo = weather_engine.geocode_location(f"{village_input}, {state_input}") or weather_engine.geocode_location(village_input)
                    if geo:
                        st.session_state["reg_lat"] = geo["lat"]
                        st.session_state["reg_lon"] = geo["lon"]
                        st.session_state["reg_village"] = geo["name"]
                        st.session_state["reg_state"] = geo["state"]
                        st.success(f"Found GPS: ({geo['lat']:.6f}, {geo['lon']:.6f}) - {geo['display']}")
                        st.rerun()
                    else:
                        st.error("Location not found. Please adjust spelling or enter coordinates directly.")

    # Live Farm Map Visualizer
    st.markdown("##### 🗺️ Farm Location Pinpoint Confirmation")
    farm_map_data = [{"lat": current_lat, "lon": current_lon}]
    try:
        st.map(farm_map_data, zoom=12)
    except Exception:
        st.info(f"📍 Selected Farm Coordinates: Latitude `{current_lat:.6f}`, Longitude `{current_lon:.6f}`")
    else:
        st.caption(f"📍 Selected Farm Pin: Latitude `{current_lat:.6f}`, Longitude `{current_lon:.6f}`")

    # Submission
    if st.button("🚀 Register Farmer with Verified GPS Coordinates", type="primary", use_container_width=True):
        if not phone_input or phone_input == "+91" or not name_input or not village_input:
            st.error("Please fill in Phone Number, Full Name, and Village/Taluka.")
        else:
            with st.spinner("Saving farmer profile to SQLite database..."):
                rec = database.register_farmer(
                    phone=phone_input,
                    name=name_input,
                    village_district=village_input,
                    state=state_input,
                    lat=current_lat,
                    lon=current_lon,
                    crop=crop_input,
                    language=lang_input,
                )

                st.balloons()
                st.success(f"🎉 Successfully registered **{rec['name']}** ({rec['phone_number']}) with verified GPS coordinates!")

                st.markdown(f"""
                <div class="metric-card">
                    <h4>✅ Registered Farmer Profile</h4>
                    <p><b>Name:</b> {rec['name']} &nbsp;|&nbsp; <b>Phone:</b> <code>{rec['phone_number']}</code></p>
                    <p><b>Location:</b> {rec['village_district']}, {rec['state']} &nbsp;|&nbsp; <b>Coordinates:</b> ({rec['latitude']:.6f}, {rec['longitude']:.6f})</p>
                    <p><b>Crop:</b> {rec['primary_crop']} &nbsp;|&nbsp; <b>Language:</b> {rec['preferred_language']}</p>
                </div>
                """, unsafe_allow_html=True)

                st.session_state["sim_test_number"] = rec["phone_number"]
                st.rerun()


    st.markdown("---")
    st.subheader("👥 Registered Farmer Database Directory")

    header_c1, header_c2 = st.columns([3, 1])
    with header_c2:
        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("🗑️ Clear All", help="Delete all records from SQLite"):
                count = database.clear_all_farmers()
                st.success(f"Cleared {count} farmers.")
                st.rerun()
        with btn_c2:
            if st.button("🌱 Load Demo", help="Re-seed 3 demo farmers"):
                database.reseed_default_farmers()
                st.success("Loaded demo profiles.")
                st.rerun()

    all_farmers_data = database.get_all_farmers()
    if all_farmers_data:
        try:
            if pd is not None:
                df = pd.DataFrame(all_farmers_data)
                st.dataframe(df, use_container_width=True)
                df_geo = df.rename(columns={"latitude": "lat", "longitude": "lon"})
                st.map(df_geo, zoom=4)
            else:
                st.table(all_farmers_data)
        except Exception:
            st.table(all_farmers_data)
    else:
        st.info("ℹ️ No registered farmers in database. Click 'Load Demo' above or register a new farmer.")


# ===========================================================================
# TAB 3: MacroDroid GSM Gateway Monitor & Live Debugger
# ===========================================================================
with tab_gateway:
    st.subheader("📱 Android GSM Gateway Integration (MacroDroid)")
    st.write("Detailed architecture and live simulation console for testing the telephony bridge pipeline.")

    with st.expander("📖 View MacroDroid 6-Step Action Sequence (Kernel Mic Lock Bypass)", expanded=False):
        st.markdown("""
        To record incoming cellular calls on modern Android 10–15 without root, MacroDroid uses system dialer auto-recording and a shell script bridge:
        1. **Trigger:** `Call Incoming (Any Number)`
        2. **Action 1:** `Wait 2 seconds` -> `Answer Call`
        3. **Action 2:** `Wait 10 seconds` *(Native system dialer records call audio into `/storage/emulated/0/Recordings/Record/Call/*.m4a`)*
        4. **Action 3:** `Call Reject / End Call` -> `Wait 2 seconds` *(Allows Android storage flush)*
        5. **Action 4:** `Shell Script (Non-Rooted)`:
           ```bash
           cp "$(ls -t /storage/emulated/0/Recordings/Record/Call/*.m4a | head -n 1)" /storage/emulated/0/Recordings/voice_query.m4a
           ```
        6. **Action 5:** `HTTP Request (POST)`:
           - **URL:** `https://<cloudflare-tunnel-url>/webhook/phone-call?caller_number=[call_number]`
           - **Content-Type:** `application/octet-stream`
           - **Body:** File -> `/storage/emulated/0/Recordings/voice_query.m4a`
           - **Response:** Stored in `{lv=advisory_reply}`
        7. **Action 6:** `Send SMS`:
           - **Recipient:** `[call_number]`
           - **Message:** `{lv=advisory_reply}`
           - **Constraint:** `{lv=advisory_reply} != "DO_NOT_SEND"` AND `{lv=advisory_reply} != ""`
        """)

    st.markdown("### 🧪 Live Telephony Pipeline Debugger")
    sim_col1, sim_col2 = st.columns([1, 1])

    with sim_col1:
        test_phone = st.text_input(
            "Enter Caller Number to Test:",
            value=st.session_state.get("sim_test_number", "+918806675887")
        )
        test_audio_state = st.radio(
            "Audio Scenario:",
            ["Silent Audio / No Spoken Words (Test Tier-2 Profile Fallback)",
             "Spoken Location Query (Test Tier-1 ASR Entity Extraction)",
             "Unregistered Caller Silent (Test Tier-3 Rejection Guidance)"]
        )

        test_query = ""
        if test_audio_state == "Spoken Location Query (Test Tier-1 ASR Entity Extraction)":
            test_query = st.text_input("Spoken Query Transcription:", value="Can I spray pesticide on cotton today in Ponda Goa?")

    with sim_col2:
        st.markdown("#### ⚡ Execution & Verification Trace")
        if st.button("🚀 Trigger Telephony Simulation", type="primary", use_container_width=True):
            clean_test_phone = database.normalize_phone(test_phone)
            prof = database.get_farmer(clean_test_phone)

            st.write(f"**Step 1:** Normalized Phone: `'{clean_test_phone}'`")
            if prof:
                st.write(f"**Step 2:** Found Profile: **{prof['name']}** ({prof['village_district']}, {prof['state']} | Crop: {prof['primary_crop']})")
            else:
                st.write(f"**Step 2:** Caller `'{clean_test_phone}'` is UNREGISTERED in SQLite.")

            # Location resolution
            if "Silent" in test_audio_state and not prof:
                st.write("**Step 3:** Tier 3 Unregistered & Silent -> Returning localized registration SMS.")
                sms_res = "WeatherGPT: आपका नंबर पंजीकृत नहीं है और आवाज़ साफ़ नहीं आई। कृपया पोर्टल पर अपना गाँव रजिस्टर करें या कॉल पर अपने जिले का नाम बोलें।"
                st.markdown(f'<div class="sms-box">{sms_res}</div>', unsafe_allow_html=True)
            else:
                if "Spoken" in test_audio_state and test_query:
                    entities = free_ivr_server.extract_spoken_entities(test_query)
                    geo = weather_engine.geocode_location(entities.get("location") or "Pune")
                    lat = geo["lat"] if geo else 18.5204
                    lon = geo["lon"] if geo else 73.8567
                    resolved_loc = f"{geo['name']}, {geo['state']}" if geo else "Pune, Maharashtra"
                    crop = entities.get("crop") or "Cotton"
                    lang = entities.get("language") or "Hindi"
                    st.write(f"**Step 3:** Tier 1 Spoken Resolution -> Location: {resolved_loc} ({lat}, {lon})")
                else:
                    lat = prof["latitude"]
                    lon = prof["longitude"]
                    resolved_loc = f"{prof['village_district']}, {prof['state']}"
                    crop = prof["primary_crop"]
                    lang = prof["preferred_language"]
                    st.write(f"**Step 3:** Tier 2 Profile Fallback -> Location: {resolved_loc} ({lat}, {lon})")

                metrics = weather_engine.fetch_live_imd_metrics(lat, lon)
                st.write(f"**Step 4:** Live NWP: Temp: {metrics['current_temp']}°C | Rain Prob: {metrics['max_rain_prob_12h']:.0f}% | Rain: {metrics['total_rain_mm_12h']}mm ({metrics['imd_rainfall_cat']}) | Wind: {metrics['max_wind_kmh_12h']}km/h")
                st.write(f"**Step 5:** Spraying Verdict: `{metrics['icar_spraying_verdict']}`")

                verified = free_ivr_server.verify_and_synthesize_sms(
                    user_query=test_query or f"Advisory for {crop} in {resolved_loc}",
                    location_name=resolved_loc,
                    crop=crop,
                    language=lang,
                    metrics=metrics,
                )

                st.write(f"**Step 6:** Verification Status: **{'APPROVED' if verified['verification_passed'] else 'REJECTED'}**")
                st.caption(f"Reason: {verified['verification_reason']}")

                st.markdown("#### 📤 Raw Outbound SMS Payload Dispatched to MacroDroid:")
                sms_body = verified.get("sms_advisory", "DO_NOT_SEND") if verified["verification_passed"] else "DO_NOT_SEND"
                st.markdown(f'<div class="sms-box">{sms_body}</div>', unsafe_allow_html=True)
                st.write(f"Characters: `{len(sms_body)}` (Max 160)")
