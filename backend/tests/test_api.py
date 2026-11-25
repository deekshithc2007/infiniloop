"""Automated backend test suite for HeatWise AI."""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ["DATABASE_URL"] = f"sqlite:///{(BACKEND_DIR / 'test_heatwise.db').as_posix()}"

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.risk_engine import compute_heat_risk  # noqa: E402


@pytest.fixture(scope="module")
def client():
    test_db = BACKEND_DIR / "test_heatwise.db"
    if test_db.exists():
        test_db.unlink()
    with TestClient(app) as c:
        yield c
    engine.dispose()
    if test_db.exists():
        test_db.unlink()


def test_risk_engine_missing_values_not_zero():
    """Missing indicators must be excluded and re-normalized, never treated as 0."""
    full = compute_heat_risk({
        "land_surface_temp_c": 48.0,
        "air_temp_c": 42.0,
        "ndvi_vegetation_pct": 10.0,
        "built_up_intensity_pct": 85.0,
        "albedo_index": 0.18,
        "elderly_pct": 12.0,
        "low_income_housing_pct": 55.0,
        "outdoor_worker_pct": 60.0,
        "healthcare_distance_km": 2.5,
        "cooling_facility_coverage_pct": 20.0,
    })
    partial = compute_heat_risk({
        "land_surface_temp_c": 48.0,
        "air_temp_c": None,
        "ndvi_vegetation_pct": 10.0,
        "built_up_intensity_pct": 85.0,
        "albedo_index": 0.18,
        "elderly_pct": 12.0,
        "low_income_housing_pct": 55.0,
        "outdoor_worker_pct": 60.0,
        "healthcare_distance_km": None,
        "cooling_facility_coverage_pct": 20.0,
    })
    assert "air_temp_c" in partial["missing_fields"]
    assert "healthcare_distance_km" in partial["missing_fields"]
    assert partial["data_confidence_pct"] < full["data_confidence_pct"]
    assert abs(partial["overall_risk_score"] - full["overall_risk_score"]) < 10.0


def test_health_and_seeded_neighbourhoods(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    nb_res = client.get("/api/neighbourhoods")
    assert nb_res.status_code == 200
    data = nb_res.json()
    assert data["count"] == 14
    assert any(n["name"] == "Odhav" and len(n["indicators"]["missing_fields"]) == 2 for n in data["neighbourhoods"])


def test_analytics_and_recommendations(client):
    an_res = client.get("/api/analytics/summary")
    assert an_res.status_code == 200
    kpis = an_res.json()["kpis"]
    assert kpis["total_neighbourhoods"] == 14
    assert kpis["avg_land_surface_temp_c"] > kpis["avg_air_temp_c"]  # LST distinct from Air Temp

    rec_res = client.get("/api/recommendations")
    assert rec_res.status_code == 200
    assert rec_res.json()["count"] > 0


def test_community_report_spam_and_submission(client):
    # Fail human check
    bad_res = client.post(
        "/api/reports",
        data={
            "neighbourhood_id": 1,
            "category": "Missing shade",
            "location_label": "Test Junction",
            "description": "No shade available at the transit junction during peak heat.",
            "human_check_answer": 99,
            "human_check_expected": 7,
        },
    )
    assert bad_res.status_code == 400

    # Valid submission
    ok_res = client.post(
        "/api/reports",
        data={
            "neighbourhood_id": 1,
            "category": "Missing shade",
            "location_label": "Test Bus Shelter East",
            "description": "No shade canopy for commuters waiting at East Bus Shelter.",
            "human_check_answer": 7,
            "human_check_expected": 7,
        },
    )
    assert ok_res.status_code == 201
    report = ok_res.json()["report"]
    assert report["moderation_status"] == "Pending"


def test_admin_rbac_moderation_intervention_and_csv(client):
    # Unauthenticated admin request blocked
    assert client.get("/api/admin/reports").status_code == 401

    # Resident cannot access admin routes
    res_login = client.post("/api/auth/login", json={"username": "resident", "password": "Resident@2026"})
    assert res_login.status_code == 200
    res_token = res_login.json()["access_token"]
    assert client.get("/api/admin/reports", headers={"Authorization": f"Bearer {res_token}"}).status_code == 403

    # Admin login
    adm_login = client.post("/api/auth/login", json={"username": "admin", "password": "HeatWiseAdmin@2026"})
    assert adm_login.status_code == 200
    adm_token = adm_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {adm_token}"}

    # Moderate a pending report
    rep_list = client.get("/api/admin/reports?moderation_status=Pending", headers=headers).json()["reports"]
    assert len(rep_list) >= 1
    target_id = rep_list[0]["id"]
    mod_res = client.patch(
        f"/api/admin/reports/{target_id}",
        headers=headers,
        json={
            "moderation_status": "Approved",
            "priority": "High",
            "workflow_status": "Planned",
            "moderator_notes": "Approved for ward action.",
        },
    )
    assert mod_res.status_code == 200

    # Create intervention and transition status
    inv_res = client.post(
        "/api/admin/interventions",
        headers=headers,
        json={
            "neighbourhood_id": 1,
            "source_report_id": target_id,
            "title": "Pilot Shade Structure",
            "intervention_type": "Installation of shade structures",
            "target_location": "East Bus Shelter",
            "priority": "High",
            "status": "Planned",
            "note": "Assigned to Engineering cell.",
        },
    )
    assert inv_res.status_code == 201
    inv_id = inv_res.json()["intervention"]["id"]

    upd_res = client.patch(
        f"/api/admin/interventions/{inv_id}/status",
        headers=headers,
        json={"status": "In progress", "note": "Frame erection started."},
    )
    assert upd_res.status_code == 200
    assert len(upd_res.json()["intervention"]["history"]) == 2

    # CSV Export
    csv_res = client.get("/api/admin/export/reports.csv", headers=headers)
    assert csv_res.status_code == 200
    assert "Reference Code,Neighbourhood" in csv_res.text
