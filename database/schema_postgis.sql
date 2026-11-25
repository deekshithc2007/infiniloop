-- HeatWise AI — PostgreSQL + PostGIS Database Schema
-- Supports all 9 core tables with spatial geometry columns and audit history.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'resident' CHECK (role IN ('resident', 'admin', 'planner')),
    organisation VARCHAR(150),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. DataSources
CREATE TABLE IF NOT EXISTS data_sources (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL,
    provider VARCHAR(150) NOT NULL,
    category VARCHAR(60) NOT NULL,
    spatial_resolution VARCHAR(80),
    update_cadence VARCHAR(80),
    data_nature VARCHAR(30) NOT NULL CHECK (data_nature IN ('Real', 'Derived', 'Estimated', 'Synthetic')),
    api_endpoint TEXT,
    requires_api_key BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(40) NOT NULL DEFAULT 'Demo Fallback',
    last_synced_at TIMESTAMPTZ,
    notes TEXT
);

-- 3. Neighbourhoods
CREATE TABLE IF NOT EXISTS neighbourhoods (
    id SERIAL PRIMARY KEY,
    code VARCHAR(40) UNIQUE NOT NULL,
    name VARCHAR(120) NOT NULL,
    city VARCHAR(80) NOT NULL DEFAULT 'Ahmedabad',
    zone VARCHAR(80) NOT NULL,
    ward_number VARCHAR(30),
    population_estimate INTEGER,
    area_sq_km DOUBLE PRECISION,
    centroid_lat DOUBLE PRECISION NOT NULL,
    centroid_lng DOUBLE PRECISION NOT NULL,
    centroid_geom GEOMETRY(Point, 4326),
    boundary_geom GEOMETRY(Polygon, 4326),
    boundary_geojson JSONB NOT NULL,
    cooling_shelters_count INTEGER DEFAULT 0,
    public_water_points_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_neighbourhoods_boundary_geom ON neighbourhoods USING GIST (boundary_geom);
CREATE INDEX IF NOT EXISTS idx_neighbourhoods_centroid_geom ON neighbourhoods USING GIST (centroid_geom);

-- 4. EnvironmentalIndicators
CREATE TABLE IF NOT EXISTS environmental_indicators (
    id SERIAL PRIMARY KEY,
    neighbourhood_id INTEGER NOT NULL REFERENCES neighbourhoods(id) ON DELETE CASCADE,
    observation_date DATE NOT NULL,
    -- Satellite LST and Air Temperature are strictly separated
    land_surface_temp_c DOUBLE PRECISION,          -- Satellite LST (e.g., Landsat 8/9 30m)
    air_temp_c DOUBLE PRECISION,                   -- 2m Ambient Air Temp (Open-Meteo / Weather Station)
    relative_humidity_pct DOUBLE PRECISION,
    ndvi_vegetation_pct DOUBLE PRECISION,          -- Sentinel-2 vegetation coverage (%)
    built_up_intensity_pct DOUBLE PRECISION,       -- Impervious / built-up surface (%)
    albedo_index DOUBLE PRECISION,                 -- Surface reflectance (0-1)
    elderly_pct DOUBLE PRECISION,                  -- Census demographic indicator
    low_income_housing_pct DOUBLE PRECISION,       -- Informal / heat-vulnerable housing (%)
    outdoor_worker_pct DOUBLE PRECISION,           -- High-exposure workforce (%)
    healthcare_distance_km DOUBLE PRECISION,       -- Distance to nearest cooling/health facility
    cooling_facility_coverage_pct DOUBLE PRECISION,-- Existing shade/water/shelter coverage (%)
    lst_source_id INTEGER REFERENCES data_sources(id),
    weather_source_id INTEGER REFERENCES data_sources(id),
    data_nature VARCHAR(30) NOT NULL DEFAULT 'Synthetic' CHECK (data_nature IN ('Real', 'Derived', 'Estimated', 'Synthetic')),
    spatial_resolution VARCHAR(80) DEFAULT '30m (Landsat) / 10m (Sentinel-2)',
    missing_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (neighbourhood_id, observation_date)
);

-- 5. HeatRiskScores
CREATE TABLE IF NOT EXISTS heat_risk_scores (
    id SERIAL PRIMARY KEY,
    neighbourhood_id INTEGER NOT NULL REFERENCES neighbourhoods(id) ON DELETE CASCADE,
    indicator_id INTEGER REFERENCES environmental_indicators(id) ON DELETE SET NULL,
    observation_date DATE NOT NULL,
    exposure_score DOUBLE PRECISION,               -- E (0-100)
    vulnerability_score DOUBLE PRECISION,          -- V (0-100)
    cooling_deficit_score DOUBLE PRECISION,        -- C (0-100)
    weight_exposure DOUBLE PRECISION NOT NULL DEFAULT 0.40,
    weight_vulnerability DOUBLE PRECISION NOT NULL DEFAULT 0.35,
    weight_cooling_deficit DOUBLE PRECISION NOT NULL DEFAULT 0.25,
    overall_risk_score DOUBLE PRECISION NOT NULL,  -- 0-100
    risk_category VARCHAR(30) NOT NULL CHECK (risk_category IN ('Low Risk', 'Moderate Risk', 'High Risk', 'Very High Risk')),
    data_confidence_pct DOUBLE PRECISION NOT NULL,
    data_confidence_label VARCHAR(20) NOT NULL CHECK (data_confidence_label IN ('High', 'Medium', 'Low')),
    contributions JSONB NOT NULL,
    model_note TEXT NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. CommunityReports
CREATE TABLE IF NOT EXISTS community_reports (
    id SERIAL PRIMARY KEY,
    reference_code VARCHAR(30) UNIQUE NOT NULL,
    neighbourhood_id INTEGER NOT NULL REFERENCES neighbourhoods(id) ON DELETE CASCADE,
    submitted_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    category VARCHAR(80) NOT NULL CHECK (category IN (
        'Missing shade',
        'Unavailable drinking water',
        'Extremely hot public spaces',
        'Lack of trees',
        'Poorly maintained cooling facilities'
    )),
    location_label VARCHAR(200) NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    geom GEOMETRY(Point, 4326),
    description TEXT NOT NULL,
    image_url TEXT,
    submission_date DATE NOT NULL,
    priority VARCHAR(20) NOT NULL DEFAULT 'Medium' CHECK (priority IN ('Critical', 'High', 'Medium', 'Low')),
    moderation_status VARCHAR(20) NOT NULL DEFAULT 'Pending' CHECK (moderation_status IN ('Pending', 'Approved', 'Rejected')),
    workflow_status VARCHAR(30) NOT NULL DEFAULT 'Reported' CHECK (workflow_status IN ('Reported', 'Under review', 'Planned', 'In progress', 'Completed')),
    moderator_notes TEXT,
    moderated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_community_reports_geom ON community_reports USING GIST (geom);

-- 7. CoolingRecommendations
CREATE TABLE IF NOT EXISTS cooling_recommendations (
    id SERIAL PRIMARY KEY,
    neighbourhood_id INTEGER NOT NULL REFERENCES neighbourhoods(id) ON DELETE CASCADE,
    intervention_type VARCHAR(100) NOT NULL,
    title VARCHAR(180) NOT NULL,
    rationale TEXT NOT NULL,
    target_location VARCHAR(200) NOT NULL,
    priority_level VARCHAR(20) NOT NULL CHECK (priority_level IN ('Critical', 'High', 'Medium', 'Low')),
    expected_beneficiaries VARCHAR(180) NOT NULL,
    estimated_cost_range VARCHAR(120),
    maintenance_considerations TEXT NOT NULL,
    triggered_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    generated_by VARCHAR(60) NOT NULL DEFAULT 'RuleEngine+ExplainableNLG',
    is_synthetic_estimate BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 8. Interventions
CREATE TABLE IF NOT EXISTS interventions (
    id SERIAL PRIMARY KEY,
    code VARCHAR(40) UNIQUE NOT NULL,
    neighbourhood_id INTEGER NOT NULL REFERENCES neighbourhoods(id) ON DELETE CASCADE,
    recommendation_id INTEGER REFERENCES cooling_recommendations(id) ON DELETE SET NULL,
    source_report_id INTEGER REFERENCES community_reports(id) ON DELETE SET NULL,
    title VARCHAR(180) NOT NULL,
    intervention_type VARCHAR(100) NOT NULL,
    target_location VARCHAR(200) NOT NULL,
    priority VARCHAR(20) NOT NULL DEFAULT 'High' CHECK (priority IN ('Critical', 'High', 'Medium', 'Low')),
    status VARCHAR(30) NOT NULL DEFAULT 'Reported' CHECK (status IN ('Reported', 'Under review', 'Planned', 'In progress', 'Completed')),
    assigned_department VARCHAR(140),
    estimated_cost_range VARCHAR(120),
    expected_beneficiaries VARCHAR(180),
    assigned_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    target_completion_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 9. InterventionHistory
CREATE TABLE IF NOT EXISTS intervention_history (
    id SERIAL PRIMARY KEY,
    intervention_id INTEGER NOT NULL REFERENCES interventions(id) ON DELETE CASCADE,
    previous_status VARCHAR(30),
    new_status VARCHAR(30) NOT NULL,
    note TEXT NOT NULL,
    changed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    changed_by_name VARCHAR(120) NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
