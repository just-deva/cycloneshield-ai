# 🌪️ CycloneShield AI — Track-Based Cyclone Impact & Infrastructure Vulnerability Forecaster

> **Google Cloud AI Builder Cup Entry**  
> **Track:** Track 05 — Resilience  
> **Pilot Location:** Visakhapatnam, Andhra Pradesh, India  
> **Live Web Application:** [https://cycloneshield-2026.web.app](https://cycloneshield-2026.web.app)  
> **GitHub Repository:** [https://github.com/just-deva/cycloneshield-ai](https://github.com/just-deva/cycloneshield-ai)  

---

## 📌 Executive Summary

**CycloneShield AI** is an end-to-end anticipatory disaster management platform built to mitigate track-based cyclone impacts along coastal India. By coupling **IMD cyclone track geometry**, **Google Earth Engine (GEE)** spatial feeds, **flood-penalized graph routing**, and **Gemini 3.7 Flash multimodal reasoning**, CycloneShield AI enables disaster command centers and citizens to transition from reactive response to predictive, localized resilience.

---

## ✨ Key Features

1. **Dynamic Ward Risk Engine:** Calculates real-time composite risk scores ($Risk = 0.30H + 0.25E + 0.25V + 0.20C$) across target coastal wards by combining elevation profiles and storm surge corridors.
2. **Evacuation Route Guardian:** Dynamic NetworkX graph pathfinding recalculates safe evacuation routes to relief shelters, penalizing flood-prone road segments in real time.
3. **Multilingual Gemini 3.7 Flash Advisories:** Generates contextual early-warning alerts and command-center briefings grounded in ward status, available in **Telugu, Odia, Tamil, Bengali, and Hindi**.
4. **Voice-Enabled Accessibility:** Integrated Web Speech API converts advisories into regional audio alerts for low-literacy residents.
5. **Parametric Relief Liquidity:** Triggers automated pre-landfall aid releases paired with cryptographically hashed (SHA-256) audit logs.

---

## 🛠️ Google Cloud & AI Tech Stack Matrix

| Layer | Technology | Usage & Integration |
| :--- | :--- | :--- |
| **Generative AI & Reasoning** | **Gemini 3.7 Flash** | Generates context-grounded multimodal alerts, command center advisories, and disaster response actions. |
| **Geospatial Intelligence** | **Google Earth Engine (GEE)** | Processes **NASA SRTM DEM** elevation data and Sentinel-1 SAR flood backscatter along IMD track corridors. |
| **Frontend Hosting** | **Firebase Hosting** | Hosts the interactive React + Leaflet single-page web app at `cycloneshield-2026.web.app`. |
| **Backend & Microservices** | **Google Cloud Run / FastAPI** | Containerized Python backend orchestrating GEE processing, graph routing algorithms, and Gemini API calls. |
| **Predictive & Routing** | **NetworkX / Python** | Dynamic graph re-weighting for safe evacuation corridor determination under predicted inundation. |
| **Language & Accessibility** | **Web Speech API & Translation** | Multilingual text translation and text-to-speech voice dispatching. |

---

## 📁 Repository Structure

```text
cycloneshield-ai/
├── frontend/                   # React.js Single Page Application
│   ├── public/                 # Static assets & fallback mock data
│   │   ├── index.html
│   │   └── mockData.json
│   ├── src/                    # UI Components & Map Controls
│   │   ├── App.js              # Main Dashboard Logic & Timeline Controls
│   │   ├── components/         # Map View, Route Overlay, Advisory Panel
│   │   └── index.js
│   ├── package.json
│   └── firebase.json           # Firebase Hosting configuration
├── backend/                    # Python FastAPI Microservice
│   ├── main.py                 # Core API endpoints & orchestration
│   ├── gee_engine.py           # Google Earth Engine spatial ingestion
│   ├── gemini_ai.py            # Gemini 3.7 Flash prompt engineering & SDK setup
│   ├── router.py               # NetworkX flood-penalized graph pathfinding
│   ├── parametric.py           # Parametric relief triggering & SHA-256 auditing
│   ├── Dockerfile              # Container definition for Google Cloud Run
│   └── requirements.txt        # Python dependency manifest
├── .gitignore                  # Exclusion patterns for keys, cache, build folders
└── README.md                   # Project documentation
```

🚦 Local Development & Setup
Prerequisites
Node.js: v18+

Python: v3.10+

Google AI Studio: Gemini API Key

---
1. Backend Setup
# Navigate to backend directory
cd backend

# Create and activate Python virtual environment
python -m venv venv
# On Windows Command Prompt:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set Gemini API Key
set GEMINI_API_KEY="your_actual_gemini_api_key"

# Start FastAPI development server
uvicorn main:app --reload --port 8000

