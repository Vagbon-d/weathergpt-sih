# WeatherGPT -- SIH26068 Prototype

A demo-ready (NOT production) prototype for the Smart India Hackathon problem
statement **SIH26068 — WeatherGPT: Conversational AI for Weather Forecasting,
Alerts, and Climate Information** (Ministry of Earth Sciences).

This is intentionally small: real weather data, a grounded local LLM, a
keyword-based domain router, and a mobile-first chat UI. It is built to prove
the concept end-to-end for judges, not to be a finished product.

## Architecture

```
React (Vite + Tailwind)
        |
        v
FastAPI backend  ---->  Open-Meteo (live weather + forecast)
        |          ---->  Local JSON knowledge base (agri advisory, demo alerts)
        v
Domain router (weather / agriculture / alert)
        |
        v
Ollama (qwen3:4b) -- summarizes/explains ONLY the retrieved data above.
It never invents numbers. If Ollama is unreachable, the raw retrieved
data is shown instead of a made-up answer.
```

Why it's built this way:
- **Grounding first.** Every numeric fact (temperature, rain %, wind, alerts)
  comes from Open-Meteo or the local knowledge base *before* the LLM sees the
  question. The LLM's only job is to phrase that data as a helpful sentence,
  in the selected language. This directly satisfies the "no hallucinated
  weather values" safety rule from the problem statement.
- **No vector DB.** The advisory/alert knowledge base is a handful of JSON
  entries -- simple keyword matching is faster to build, easier to debug live
  in front of judges, and just as correct at this scale. Swap in a real
  vector store later if the knowledge base grows.
- **Demo alerts are clearly labeled.** `alerts_demo.json` is marked
  `DEMO/SIMULATED` everywhere it surfaces in the UI and in LLM prompts, so it
  can never be mistaken for an official IMD/NDMA warning.

## Project structure

```
weathergpt/
├── backend/
│   ├── main.py
│   ├── routers/       weather.py, chat.py, alerts.py, advisory.py
│   ├── services/       weather_service.py, rag_service.py, llm_service.py
│   └── data/           advisory_kb.json, alerts_demo.json
├── frontend/
│   └── src/            App.jsx, components/, services/api.js, i18n.js
├── requirements.txt
└── README.md
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com) installed, with `qwen3:4b` pulled:
  ```
  ollama pull qwen3:4b
  ```
- Internet access at run time (Open-Meteo is a live public API; the LLM
  itself runs fully local via Ollama)

## Quickstart Instructions

### 1. Install Dependencies

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
```

### 2. Run Ollama (Language Layer)

```bash
ollama list
ollama run qwen3:4b

# If necessary, ensure Ollama server is running:
ollama serve
```

### 3. Run Backend API

```bash
cd backend
uvicorn main:app --reload --port 8000
```
- FastAPI Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/health](http://localhost:8000/health)

### 4. Run Frontend Dashboard

```bash
cd frontend
npm install
npm run dev
```
- Open Web Application: [http://localhost:5173](http://localhost:5173)

---

## API Endpoints

| Method | Path        | Purpose                                                                 |
|--------|-------------|-------------------------------------------------------------------------|
| GET    | `/health`   | Service liveness check (`{"status": "healthy"}`)                       |
| GET    | `/weather`  | Real-time conditions + 4-day forecast for an Indian location            |
| GET    | `/alerts`   | Simulated demo alerts, filtered by location (substring match)           |
| POST   | `/chat`     | Grounded conversational weather, agricultural, and alert intelligence    |
| POST   | `/advisory` | Dedicated agronomic advisory with deterministic Python rule evaluation |


## Sample questions to test

- "What's the weather in Mumbai?" (general weather)
- "Will it rain tomorrow?" (forecast)
- "Can I spray pesticide today?" (agriculture -- try with location = Pune)
- "Any active alerts?" (alert relay, clearly marked DEMO)
- Hindi: "क्या कल बारिश होगी?"
- Switch the language toggle to हिं or कों and repeat a question -- the
  answer is generated in that language by the LLM.

## Language support -- what's real vs. what's honest about its limits

- **English & Hindi**: full loop -- UI strings, voice input/output (via the
  browser's built-in Web Speech API, no cloud service, no API key), and LLM
  responses.
- **Konkani**: UI strings and LLM response *requests* are wired up, but
  browser speech engines don't reliably support `kok-IN` yet, and qwen3:4b's
  Konkani fluency is inconsistent. The app is upfront about this in-UI rather
  than faking it -- worth calling out to judges as a known, scoped
  limitation with a clear next step (a proper ASR/TTS service such as
  Bhashini/AI4Bharat, per the research report).

## Demonstrating to SIH judges

1. Open the app, show the live weather card for a city (point out it's a
   real API call, not a hardcoded number).
2. Ask a rain question by **voice** in English or Hindi -- show the mic
   button and the spoken transcript appearing.
3. Run the pesticide-spraying scenario end-to-end: ask "Can I spray today in
   Pune?" and narrate the pipeline out loud -- weather fetched -> advisory KB
   matched -> LLM phrases the recommendation, never inventing the rain %.
4. Show the alerts section and explicitly point out the "DEMO ALERT" label
   -- this is the safety design the problem statement asks for.
5. Kill the Ollama server and ask a question again, to show the graceful
   fallback (raw data instead of a fabricated answer) rather than a crash.
6. Close by naming what's next (Phase 2/3 from the research report): full
   IMD/WIS 2.0 data, Bhashini voice for more languages, aviation/marine
   agents, push alerts.

## What this prototype deliberately does NOT do

Per the original scope: no custom NWP model, no Kubernetes, no vector DB,
no fine-tuned LLM, no production auth/payments, no full WhatsApp/aviation/
marine/disaster platform. See the accompanying research report for the
phased roadmap toward those.
