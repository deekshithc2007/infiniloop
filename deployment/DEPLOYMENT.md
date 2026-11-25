# HeatWise AI — Cloud Deployment Guide

## 1. Database Setup (Supabase / Managed PostgreSQL + PostGIS)
1. Create a PostgreSQL 15+ database (e.g., on Supabase or Render PostgreSQL).
2. Enable PostGIS and apply the schema in `database/schema_postgis.sql`:
   ```bash
   psql "$DATABASE_URL" -f database/schema_postgis.sql
   ```
3. Note: For local development or hackathons, leaving `DATABASE_URL` unset defaults to SQLite (`backend/heatwise.db`) with automatic schema creation and seeding.

## 2. Backend Deployment (Render)
1. Connect this repository to Render and select **Blueprint** (`deployment/render.yaml`) or create a Python Web Service with root directory `backend`.
2. Set environment variables:
   - `SECRET_KEY`: strong 32+ character random string
   - `DATABASE_URL`: PostgreSQL connection string (`postgresql+psycopg2://...`)
   - `CORS_ORIGINS`: `https://your-vercel-app.vercel.app`
   - Optional API keys (`GOOGLE_EARTH_ENGINE_PROJECT_ID`, `NASA_EARTHDATA_TOKEN`, `SENTINEL_HUB_CLIENT_ID`, `SENTINEL_HUB_CLIENT_SECRET`). If left blank, the platform uses the clearly labelled Ahmedabad synthetic/demo dataset and live Open-Meteo fallback.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## 3. Frontend Deployment (Vercel)
1. Import the repository into Vercel with root directory `frontend`.
2. Framework preset: **Vite**.
3. Copy `deployment/vercel.json` or ensure SPA rewrites route all paths to `/index.html`.
4. Set environment variable:
   - `VITE_API_BASE_URL`: `https://your-render-backend.onrender.com/api`
5. Deploy.
