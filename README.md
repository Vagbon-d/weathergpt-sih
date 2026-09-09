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
├── backend/
│   ├── main.py                     # FastAPI entrypoint & crawler scheduler lifecycle
│   ├── routers/
│   │   ├── chat.py                 # Grounded conversational assistant endpoint
│   │   ├── weather.py              # Real-time weather & forecast endpoint
│   │   ├── alerts.py               # Official IMD warning cards
│   │   ├── advisory.py             # Agricultural decision support
│   │   ├── location.py             # Photon geocoding and reverse geocoding
│   │   ├── language.py             # Multilingual TTS & transliteration
│   │   └── crawler.py              # Crawler status & on-demand triggers
│   ├── services/
│   │   ├── crawler/                # IMD bulletin crawler, parser, normalizer, scheduler
│   │   ├── weather/                # Open-Meteo, IMD provider, and fallback logic
│   │   ├── location/               # Photon OpenStreetMap service
│   │   ├── language/               # Native TTS, Bhashini client, language detector
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
│   │   ├── components/             # Weather cards, ChatPanel, LocationModal, Audio controls
│   │   ├── i18n/                   # 12 Indic locale dictionaries (zero emojis)
│   │   └── services/api.js         # API integration client
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
# Navigate to project root
cd /Users/yuki.2/Desktop/weathergpt

# Create virtualenv and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Launch the Backend
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
- API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/health](http://localhost:8000/health)
- Crawler Status: [http://localhost:8000/crawl/status](http://localhost:8000/crawl/status)

### Step 4: Launch the Frontend
In a new terminal window:
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 6. Running in PyCharm

1. Open the `/Users/yuki.2/Desktop/weathergpt` directory in PyCharm.
2. Go to **Settings / Preferences -> Project: weathergpt -> Python Interpreter**.
3. Select **Add Interpreter -> Existing** and point to `/Users/yuki.2/Desktop/weathergpt/.venv/bin/python`.
4. Create a new **FastAPI / Python Run Configuration**:
   - **Script path**: Select `uvicorn` inside `.venv/bin/uvicorn` or module `uvicorn`.
   - **Parameters**: `main:app --reload --port 8000`
   - **Working directory**: `/Users/yuki.2/Desktop/weathergpt/backend`
5. Click **Run** or **Debug** to start the backend with full breakpoint debugging.

---

## 7. Automated Test Suite (All 15 Scenarios)

WeatherGPT includes a comprehensive end-to-end automated verification suite covering all core functional, mathematical, and safety requirements:

```bash
# Run the complete test suite
.venv/bin/python /Users/yuki.2/.gemini/antigravity/brain/622d3c36-4ada-4a2b-813b-3d8e6ae387f0/scratch/test_sih_suite.py
```

### Verified Test Scenarios:
1. `"tomorrow weather"`: Resolves strictly to tomorrow's date, never today.
2. `"will it rain tomorrow?"`: Extracts tomorrow's rain probability and advises on umbrella usage.
3. `"kal baarish hogi kya?"`: Responds in natural Roman Hindi / Hinglish.
4. `"कल बारिश होगी क्या?"`: Responds in pure Devanagari Hindi with zero leaked technical English.
5. `"Can I spray pesticide today?"`: Evaluates rain probability and wind speed to return practical safety advice.
6. `"Any warning near me?"`: Returns official IMD warnings or a clean "Normal conditions" notice with zero demo alerts.
7. `"Is there a cyclone warning?"`: Retrieves authoritative RSMC New Delhi cyclone bulletins.
8. `"Compare tomorrow and Sunday"`: Correctly extracts Sunday's forecast and performs temperature comparison.
9. **Location Search**: Resolves Indian locations via Photon with latitude/longitude coordinates.
10. **No Location Guard**: Prompts user to select a location; never silently defaults to Mumbai.
11. **Native Hindi TTS**: Generates audio using macOS `Lekha` voice with >100KB base64 audio payload.
12. **Duplicate Prevention**: Single-flight request locking ensures exactly 1 assistant response per query.
13. **Ollama Unavailable**: Deterministic Python engine constructs complete, safe answers without 500 errors.
14. **IMD Unavailable**: Gracefully falls back to crawled bulletin cache and Open-Meteo data.
15. **Crawler Endpoints**: `GET /crawl/status` and `POST /crawl/run` execute successfully.

---

## 8. API Reference

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/chat` | Conversational weather assistant with multi-turn history, RAG, and language enforcement |
| `GET` | `/weather` | Real-time weather and 4-day forecast for coordinates or location name |
| `GET` | `/alerts` | Official IMD active warnings for the specified district or state |
| `POST` | `/advisory` | Crop-specific agricultural safety assessments (spray, sow, irrigate, harvest) |
| `GET` | `/location/search` | Search Indian cities, villages, and landmarks via Photon |
| `GET` | `/location/reverse` | Reverse geocodes coordinates to canonical Indian location strings |
| `POST` | `/language/tts` | High-fidelity text-to-speech audio synthesis (`Lekha` / Bhashini fallback) |
| `GET` | `/crawl/status` | Current crawler state, document count, and last sweep timestamp |
| `POST` | `/crawl/run` | Triggers an immediate crawl cycle across official IMD endpoints |
| `GET` | `/health` | System health check and service readiness |

---

## 9. Hackathon Demonstration Walkthrough

1. **Location Selection & Real-Time Weather**:
   - Use GPS auto-detect or search for any Indian district (e.g., `Panaji, Goa` or `Bengaluru, Karnataka`).
   - Observe live temperature, condition, rain chance, wind speed, and humidity sourced from Open-Meteo.
2. **Authoritative Warnings**:
   - Open the **Alerts** tab. Observe official IMD bulletins (e.g. NWFC All India Bulletins, Coastal Karnataka/Goa Orange alerts). Notice that there are zero demo alerts.
3. **Conversational Weather & Farming Advice**:
   - Ask: *"Can I spray pesticide today?"*
   - WeatherGPT inspects wind and rain risk deterministically and returns a clear recommendation.
4. **Multilingual Speech & Devanagari Hindi**:
   - Switch language to **हिन्दी (Hindi)**.
   - Ask by voice or text: *"कल बारिश होगी क्या?"*
   - Click **Read Aloud** — listen to native Hindi audio synthesized via `Lekha`.
5. **Resilience & Offline Demo**:
   - Stop Ollama (`pkill ollama`).
   - Ask any weather or farming question — WeatherGPT's deterministic sentence engine returns a natural, grammatically correct answer instantly without any 500 error.
