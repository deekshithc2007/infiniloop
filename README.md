# HeatWise AI — Neighbourhood Heat Intelligence & Cooling Action Platform

**HeatWise AI** is a full-stack urban heat-risk assessment, vulnerability analysis, and cooling-action decision-support platform built for municipal authorities, urban planners, NGOs, and communities.

> **Data Transparency Note:** Baseline satellite Land-Surface Temperature (LST), NDVI vegetation, and Census vulnerability figures in this prototype use a clearly labelled **Synthetic / Demo Sample Dataset** for 14 Ahmedabad wards (`data/ahmedabad_heat_sample.json`). Ambient 2m air temperature optionally connects live to Open-Meteo (`OPEN_METEO_ENABLED=true`) with automatic fallback. Satellite LST and 2m Air Temperature are always displayed separately.

---

## Core Workflow
`COLLECT DATA → IDENTIFY HEAT-RISK AREAS → ANALYSE VULNERABILITY → RECOMMEND COOLING ACTIONS → COLLECT COMMUNITY REPORTS → TRACK GOVERNMENT INTERVENTIONS`

---

## Architecture & Modules
- **Frontend (`frontend/`)**: React 18, Vite, Tailwind CSS, Leaflet.js + OpenStreetMap, Recharts, Lucide React icons.
  - Landing Page (`/`), Interactive Heat-Risk Map (`/map`), Heat Analytics Dashboard (`/analytics`), AI Cooling Recommendation Engine (`/cooling-solutions`), Community Reporting (`/community`), Government/Admin Portal (`/admin`), About & Methodology (`/about`).
- **Backend (`backend/`)**: Python FastAPI, SQLAlchemy ORM, JWT Role-Based Access Control (`admin`, `planner`, `resident`), automated pytest suite.
  - **Heat-Risk Calculation Engine (`backend/app/risk_engine.py`)**: Explainable weighted formula `Risk = 0.40×E + 0.35×V + 0.25×C` with configurable weights, min-max normalization, strict missing-data handling (missing fields are never treated as zero), and data confidence scoring.
  - **AI Cooling Recommendation Engine (`backend/app/recommendation_engine.py`)**: Deterministic rule engine + explainable natural-language rationales across 6 practical cooling interventions.
- **Database (`database/schema_postgis.sql`)**: PostgreSQL + PostGIS DDL for all 9 core tables (`users`, `data_sources`, `neighbourhoods`, `environmental_indicators`, `heat_risk_scores`, `community_reports`, `cooling_recommendations`, `interventions`, `intervention_history`). Uses local SQLite out-of-the-box for zero-config evaluation.

---

## Local Setup & Installation

### Prerequisites
- Python 3.10+
- Node.js 20+ & npm

### 1. Backend Setup
```bash
cd heatwise-ai/backend
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
API docs will be live at `http://127.0.0.1:8000/docs`. The database auto-creates and seeds on startup.

### 2. Frontend Setup
```bash
cd heatwise-ai/frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser. Vite proxies `/api` and `/uploads` requests directly to `http://127.0.0.1:8000`.

### 3. Running Automated Tests
```bash
cd heatwise-ai/backend
pytest tests/test_api.py -v
```

---

## Demo Evaluation Accounts
| Role | Username | Password | Permissions |
| --- | --- | --- | --- |
| Municipal Admin | `admin` | `HeatWiseAdmin@2026` | Moderate reports, assign & update interventions, export CSV |
| Urban Planner | `planner` | `Planner@2026` | Moderate reports, assign & update interventions, export CSV |
| Resident | `resident` | `Resident@2026` | Submit reports, view public map & analytics |

---

## External API Configuration
Copy `.env.example` to `backend/.env` and configure optional keys (`GOOGLE_EARTH_ENGINE_PROJECT_ID`, `NASA_EARTHDATA_TOKEN`, `SENTINEL_HUB_CLIENT_ID`, `SENTINEL_HUB_CLIENT_SECRET`). When unset, the platform safely uses the labelled demo dataset without fabricating live readings.

See `deployment/DEPLOYMENT.md` for Vercel, Render, and Supabase/PostGIS production instructions.
