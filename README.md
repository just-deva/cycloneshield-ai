# CycloneShield AI — Track-Based Cyclone Vulnerability & Early Warning System

**Track:** Google Cloud AI Builder Cup — Track 05: Resilience  
**Live Frontend:** [https://cycloneshield-2026.web.app](https://cycloneshield-2026.web.app)  
**Pilot Target District:** Visakhapatnam, Andhra Pradesh, India  

---

## 🌪️ Project Overview
**CycloneShield AI** is an anticipatory disaster response platform designed for coastal resilience in India. By ingesting IMD cyclone track geometry, high-resolution elevation data, and asset exposure vectors, it dynamically forecasts ward-level infrastructure risk, reroutes evacuees away from inundated roads, and provides voice-enabled, multimodal advisories before landfall.

---

## 🛠️ Google Cloud & AI Tech Stack
- **AI & Reasoning:** Gemini 3.7 Flash SDK for context-grounded structured briefings and localized advisories.
- **Geospatial Processing:** Google Earth Engine (GEE) API for elevation profiling (NASA SRTM DEM) and storm surge flood mapping.
- **Hosting & Infrastructure:**
  - **Frontend:** Deployed live on **Firebase Hosting**.
  - **Backend API:** Dockerized FastAPI architecture structured for **Google Cloud Run**.
- **Routing Engine:** NetworkX graph pathfinding with dynamic flood-penalty weights.
- **Accessibility:** Browser Web Speech API & Multilingual Translation (Telugu, Odia, Tamil, Hindi).

---

## 📁 Repository Structure
├── frontend/             # React.js UI (Dashboard, Leaflet Maps, Speech Player)
│   ├── public/           # Static assets and mock fallback data
│   └── src/              # React components
├── backend/              # Python FastAPI Application
│   ├── main.py           # Core routing, GEE integration, and Gemini 3.7 Flash logic
│   ├── Dockerfile        # Container configuration for Google Cloud Run
│   └── requirements.txt  # Python dependency specification
└── README.md

---

## 🚀 Running Locally

### 1. Backend Setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
set GEMINI_API_KEY="your_api_key_here"
uvicorn main:app --reload --port 8000