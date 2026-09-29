# WeatherGPT — Conversational AI for Weather Forecasting, Alerts, and Climate Information

**Smart India Hackathon (SIH26068) Prototype**  
*Ministry of Earth Sciences (MoES) / India Meteorological Department (IMD)*

WeatherGPT is a production-grade hackathon prototype designed for Indian farmers, coastal communities, and citizens. It combines authoritative meteorological data ingestion, deterministic mathematical evaluation, Retrieval-Augmented Generation (RAG) over official IMD bulletins, and a local open-source LLM (`qwen3:4b` via Ollama) to deliver hyper-local, multilingual weather intelligence with **zero hallucinated facts**.

---

## 1. High-Level Architecture & Safety Pipeline

```
 User Input (Voice / Text in 12 Indian Languages)
                     │
                     ▼
 Photon OpenStreetMap Geocoder (Indian POI / District / GPS Resolution)
                     │
                     ▼
 Deterministic Temporal & Intent Classifier (Python Date & Hazard Parsing)
                     │
       ┌─────────────┴─────────────┐
       ▼                           ▼
Open-Meteo Service           Authoritative IMD Ingestion Layer
(High-Resolution Numerical   (NWFC Bulletins, RSMC Cyclone Outlooks,
 Forecast Models)             Severe Nowcasts, Agromet Advisories)
       │                           │
       └─────────────┬─────────────┘
                     ▼
 RAG Knowledge Layer & Advisory Rule Engine (Python Threshold Calculations)
                     │
                     ▼
 Factual Grounded Context Builder (Strict Tokenized Factual Constraints)
                     │
       ┌─────────────┴─────────────┐
       ▼                           ▼
Local Ollama (qwen3:4b)      Deterministic Human Fallback Engine
(Empathetic Multilingual     (100% Reliable if Ollama is Offline
 Natural Language Synthesis)  or Timeout Occurs)
                     │
                     ▼
 Multilingual Output (Devanagari / Roman Hindi / 12 Indic Locales)
                     │
                     ▼
 Native System TTS (`say -v Lekha` for Hindi / Bhashini Cloud Fallback)
```

### The Zero-Hallucination Rule
1. **The LLM is NEVER the source of weather facts.** Every numerical metric (temperature, rain probability, humidity, wind velocity) is retrieved from verified models and official meteorological bulletins *before* the prompt is constructed.
2. **Mathematical and agricultural evaluations occur strictly in Python.** Spraying safety, irrigation postponement, harvest protection, and date diff calculations are deterministic. The LLM only acts as a conversational translator and explainer.
3. **Zero Demo Alerts.** All simulated or fake warnings have been eradicated. WeatherGPT displays authoritative warnings crawled directly from IMD or explicitly indicates that weather conditions are normal.

---

## 2. Core Subsystems

### A. Authoritative IMD Crawler & Scheduler (`backend/services/crawler/`)
- **Async Meteorological Crawler (`imd_crawler.py`)**: Crawls official IMD targets including:
  - IMD National Weather Forecasting Centre (NWFC) All India Weather Warning Bulletins
  - RSMC New Delhi Tropical Weather Outlooks & Cyclone Bulletins
  - Severe Weather Nowcasts & District Agromet Advisories
- **Intelligent Parser & Normalizer (`bulletin_parser.py`, `normalizer.py`)**: Extracts hazard categories, color severities (Red/Orange/Yellow/Green), validity timeframes, and actionable agricultural instructions into a canonical JSON schema.
- **SHA-256 Deduplication**: Generates unique content hashes to prevent redundant storage and unnecessary processing.
- **Resilient Offline Fallback**: Pre-seeds official IMD snapshots in `backend/data/crawled/official_imd_bulletins.json` so the prototype functions completely offline or in sandboxed networks.
- **In-Process Scheduler (`scheduler.py`)**: Runs periodic background crawls (configurable via `IMD_CRAWL_INTERVAL_MINUTES`, default 60 min) with manual on-demand trigger capability.

### B. Retrieval-Augmented Generation (RAG) Layer (`backend/services/rag_service.py`)
- Ingests both crawled IMD bulletins and crop-specific decision rules from `advisory_kb.json`.
- Implements multi-faceted retrieval matching location tokens (District, State, Sub-division), temporal horizons (Today, Tomorrow, Sunday, Next Week), and hazard intents (Cyclone, Heavy Rain, Thunderstorm, Spraying, Sowing).
- Annotates agronomic rules with deterministic boolean trigger states (`triggered: True/False`) based on live weather thresholds.

### C. Natural Language & Native TTS Engine (`backend/services/language/`)
- **Deterministic Temporal Engine**: Accurately maps colloquial time queries (`tomorrow`, `day after tomorrow`, `parso` / `परसों`, `sunday`, `weekend`) to calendar dates without date-shifting errors.
- **Script-Aware Language Resolution**: Seamlessly distinguishes between pure Devanagari Hindi (`कल बारिश होगी क्या?`), Roman Hindi / Hinglish (`kal baarish hogi kya?`), and English.
- **Native System Voice Synthesis (`native_tts.py`)**: Synthesizes clean, high-fidelity Hindi speech locally on macOS using `say -v Lekha` without external API dependencies. Automatically falls back to Government of India Bhashini endpoints or the browser Speech Synthesis API.

---

## 3. Project Directory Structure

```
weathergpt/
├── app.py                          # Streamlit Management Portal & Telephony Simulation Hub
├── backend/
│   ├── main.py                     # FastAPI entrypoint, IVR webhooks & crawler lifecycle
│   ├── free_ivr_server.py          # Free GSM Telephony Gateway & Webhook Server
│   ├── weather_engine.py           # Real-time NWP & IMD classification engine
│   ├── database.py                 # SQLite farmer persistence & lookup
│   ├── db/
│   │   └── database.py             # SQLAlchemy aiosqlite caller profiles
│   ├── routers/
│   │   ├── chat.py                 # Grounded conversational assistant endpoint
│   │   ├── weather.py              # Real-time weather & forecast endpoint
│   │   ├── alerts.py               # Official IMD warning cards
│   │   ├── advisory.py             # Agricultural decision support
│   │   ├── location.py             # Photon geocoding and reverse geocoding
│   │   ├── language.py             # Multilingual TTS & transliteration
│   │   ├── crawler.py              # Crawler status & on-demand triggers
│   │   ├── webhook.py              # Twilio / GSM IVR & SMS webhook handlers
│   │   └── ws_call_status.py       # Live call-status WebSocket feed
│   ├── services/
│   │   ├── crawler/                # IMD bulletin crawler, parser, normalizer, scheduler
│   │   ├── weather/                # Open-Meteo, IMD provider, and fallback logic
│   │   ├── location/               # Photon OpenStreetMap service
│   │   ├── language/               # Native TTS, Bhashini client, language detector
│   │   ├── grounded_advisory.py    # Shared zero-hallucination advisory pipeline
│   │   ├── query_engine.py         # Intent classification & deterministic fallback engine
│   │   ├── rag_service.py          # Multidimensional RAG over IMD bulletins & advisories
│   │   ├── advisory_service.py     # Agricultural threshold evaluation (spray, sow, harvest)
│   │   └── llm_service.py          # Ollama (qwen3:4b) grounding & numeric validator
│   └── data/
│       ├── advisory_kb.json        # Agronomic decision rules & thresholds
│       └── crawled/
│           └── official_imd_bulletins.json # Authoritative pre-seeded bulletin repository
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 # Main application container & single-flight chat lock
│   │   ├── components/             # Weather cards, ChatPanel, IVRSimulator, HelplineBanner
│   │   ├── i18n/                   # 12 Indic locale dictionaries
│   │   └── api.js                  # API integration client
│   └── package.json
├── requirements.txt
├── .env.example
└── README.md
```

---

## 4. Environment Variables Configuration

Copy `.env.example` to `.env` in the project root:

```bash
cp .env.example .env
```

| Variable | Default | Description |
| :--- | :--- | :--- |
| `IMD_API_KEY` | *(empty)* | Optional IMD API key (crawler uses web scraper & local snapshots if omitted) |
| `IMD_BASE_URL` | `https://api.imd.gov.in` | Base URL for official IMD API endpoints |
| `IMD_CRAWLER_ENABLED` | `true` | Enables/disables periodic in-process background crawling |
| `IMD_CRAWL_INTERVAL_MINUTES` | `60` | Frequency in minutes between automated crawler sweeps |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Endpoint of the local Ollama LLM instance |
| `OLLAMA_MODEL` | `qwen3:4b` | Ollama model tag for natural language synthesis |
| `PHOTON_BASE_URL` | `https://photon.komoot.io` | Komoot Photon OpenStreetMap geocoding endpoint |
| `BHASHINI_API_KEY` | *(empty)* | Optional MeitY Bhashini API Key for Indic voice synthesis |
| `PORT` | `8000` | Backend listening port |

---

## 5. Quickstart & Running Locally

### Step 1: Install Ollama & Pull the Model
Ensure Ollama is installed and running:
```bash
ollama pull qwen3:4b
ollama serve
```

### Step 2: Set Up Backend Virtual Environment
```bash
# Create virtualenv and install dependencies
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

pip install -r requirements.txt
```

### Step 3: Launch the Backend (FastAPI + IVR Webhooks)
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
- API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/health](http://localhost:8000/health)
- Crawler Status: [http://localhost:8000/crawl/status](http://localhost:8000/crawl/status)
- IVR Webhooks: `POST /webhook/sms`, `POST /webhook/voice`, `POST /webhook/voice/process`

### Step 4: Launch the Frontend (React + Vite)
In a new terminal:
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

### Step 5: (Optional) Launch the Streamlit Farmer Portal & Telephony Hub
In a separate terminal:
```bash
streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) for the unified portal:
1. **Conversational WeatherGPT**: Multi-lingual assistant with zero hallucination.
2. **Farmer Offline Registration Portal**: Offline GPS/village registration & SQLite directory.
3. **MacroDroid GSM Gateway Monitor**: GSM sequence visual guide & telephony simulator console.

---

## 6. Running in PyCharm / VS Code

1. Open the project root directory in your IDE.
2. Select the Python interpreter inside `.venv`.
3. Create a **FastAPI** run configuration:
   - **Module**: `uvicorn`
   - **Parameters**: `main:app --reload --port 8000`
   - **Working directory**: `backend`
4. Click **Run** or **Debug** to start with full breakpoint debugging.

---

## 7. API Reference

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/chat` | Conversational weather assistant with multi-turn history, RAG, and language enforcement |
| `GET` | `/weather` | Real-time weather and 4-day forecast for coordinates or location name |
| `GET` | `/alerts` | Official IMD active warnings for the specified district or state |
| `POST` | `/advisory` | Crop-specific agricultural safety assessments (spray, sow, irrigate, harvest) |
| `GET` | `/location/search` | Search Indian cities, villages, and landmarks via Photon |
| `GET` | `/location/reverse` | Reverse geocodes coordinates to canonical Indian location strings |
| `POST` | `/language/tts` | High-fidelity text-to-speech audio synthesis (`Lekha` / Bhashini fallback) |
| `POST` | `/webhook/sms` | Twilio / GSM inbound SMS gateway endpoint |
| `POST` | `/webhook/voice` | Twilio / GSM voice call IVR entrypoint |
| `POST` | `/webhook/voice/process` | ASR speech transcript processor with grounded advisory synthesis |
| `GET` | `/ws/call-status` | WebSocket feed broadcasting live telephony call events |
| `GET` | `/crawl/status` | Current crawler state, document count, and last sweep timestamp |
| `POST` | `/crawl/run` | Triggers an immediate crawl cycle across official IMD endpoints |
| `GET` | `/health` | System health check and service readiness |

---

## 8. Hackathon Demonstration Walkthrough

1. **Location Selection & Real-Time Weather**:
   - Use GPS auto-detect or search for any Indian district (e.g., `Panaji, Goa` or `Pune, Maharashtra`).
   - Observe live temperature, condition, rain chance, wind speed, and humidity sourced from Open-Meteo.
2. **Authoritative Warnings**:
   - Open the **Alerts** tab. Observe official IMD bulletins (e.g. NWFC All India Bulletins, District Warnings). Zero demo alerts.
3. **Conversational Weather & Farming Advice**:
   - Ask: *"Can I spray pesticide today?"*
   - WeatherGPT inspects wind and rain risk deterministically and returns a clear recommendation.
4. **Multilingual Speech & Devanagari Hindi**:
   - Switch language to **हिन्दी (Hindi)**.
   - Ask by voice or text: *"कल बारिश होगी क्या?"*
   - Click **Read Aloud** to listen to native voice output.
5. **Feature-Phone IVR Helpline & Simulator**:
   - Use the **IVR Simulator** on the dashboard or test simulated inbound voice calls / SMS requests.
   - Profile recognition automatically recalls registered farmers' villages without re-asking.
6. **Resilience & Offline Demo**:
   - Even without an external LLM running, WeatherGPT's deterministic Python engine constructs grammatically correct, safe answers instantly.
