"""Idempotent database seeder loading the Ahmedabad demo dataset into all 9 tables."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import PROJECT_ROOT
from app.models import (
    CommunityReport,
    CoolingRecommendation,
    DataSource,
    EnvironmentalIndicator,
    HeatRiskScore,
    Intervention,
    InterventionHistory,
    Neighbourhood,
    User,
)
from app.recommendation_engine import generate_recommendations_for_neighbourhood
from app.risk_engine import compute_heat_risk


def seed_database(db: Session) -> None:
    """Populate initial demo users, data sources, neighbourhoods, indicators, scores, recommendations, reports & interventions."""
    if db.query(Neighbourhood).count() > 0:
        return

    sample_path = PROJECT_ROOT / "data" / "ahmedabad_heat_sample.json"
    with open(sample_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    # 1. Users (Demo accounts for SIH evaluation)
    admin_user = User(
        username="admin",
        email="admin@heatwise.gov.demo",
        full_name="Dr. Meera Patel (Municipal Heat Officer)",
        password_hash=hash_password("HeatWiseAdmin@2026"),
        role="admin",
        organisation="Ahmedabad Heat Action Cell (Demo)",
    )
    planner_user = User(
        username="planner",
        email="planner@heatwise.gov.demo",
        full_name="Arjun Deshmukh (Urban GIS Planner)",
        password_hash=hash_password("Planner@2026"),
        role="planner",
        organisation="Urban Planning & Forestry Dept (Demo)",
    )
    resident_user = User(
        username="resident",
        email="citizen@heatwise.demo",
        full_name="Kavita Shah (Community Volunteer)",
        password_hash=hash_password("Resident@2026"),
        role="resident",
        organisation="Ward 14 Resident Welfare Association",
    )
    db.add_all([admin_user, planner_user, resident_user])
    db.flush()

    # 2. DataSources
    source_map = {}
    for ds_item in dataset["data_sources"]:
        ds = DataSource(
            code=ds_item["code"],
            name=ds_item["name"],
            provider=ds_item["provider"],
            category=ds_item["category"],
            spatial_resolution=ds_item.get("spatial_resolution"),
            update_cadence=ds_item.get("update_cadence"),
            data_nature=ds_item["data_nature"],
            api_endpoint=ds_item.get("api_endpoint"),
            requires_api_key=ds_item.get("requires_api_key", False),
            status=ds_item.get("status", "Demo Fallback"),
            last_synced_at=datetime.utcnow(),
            notes=ds_item.get("notes"),
        )
        db.add(ds)
        db.flush()
        source_map[ds.code] = ds

    lst_source_id = source_map.get("LANDSAT_LST").id if "LANDSAT_LST" in source_map else None
    weather_source_id = source_map.get("OPEN_METEO").id if "OPEN_METEO" in source_map else None

    # 3, 4, 5, 7. Neighbourhoods, EnvironmentalIndicators, HeatRiskScores, CoolingRecommendations
    nb_by_code = {}
    latest_date_str = dataset["metadata"]["default_observation_date"]

    for nb_item in dataset["neighbourhoods"]:
        nb = Neighbourhood(
            code=nb_item["code"],
            name=nb_item["name"],
            city=dataset["metadata"]["city"],
            zone=nb_item["zone"],
            ward_number=nb_item.get("ward_number"),
            population_estimate=nb_item.get("population_estimate"),
            area_sq_km=nb_item.get("area_sq_km"),
            centroid_lat=nb_item["centroid_lat"],
            centroid_lng=nb_item["centroid_lng"],
            boundary_geojson=nb_item["boundary_geojson"],
            cooling_shelters_count=nb_item.get("cooling_shelters_count", 0),
            public_water_points_count=nb_item.get("public_water_points_count", 0),
        )
        db.add(nb)
        db.flush()
        nb_by_code[nb.code] = nb

        latest_ind_dict = None
        latest_risk_dict = None

        for snap in nb_item["snapshots"]:
            obs_date = date.fromisoformat(snap["observation_date"])
            risk_res = compute_heat_risk(snap, data_nature="Synthetic")

            ind = EnvironmentalIndicator(
                neighbourhood_id=nb.id,
                observation_date=obs_date,
                land_surface_temp_c=snap.get("land_surface_temp_c"),
                air_temp_c=snap.get("air_temp_c"),
                relative_humidity_pct=snap.get("relative_humidity_pct"),
                ndvi_vegetation_pct=snap.get("ndvi_vegetation_pct"),
                built_up_intensity_pct=snap.get("built_up_intensity_pct"),
                albedo_index=snap.get("albedo_index"),
                elderly_pct=snap.get("elderly_pct"),
                low_income_housing_pct=snap.get("low_income_housing_pct"),
                outdoor_worker_pct=snap.get("outdoor_worker_pct"),
                healthcare_distance_km=snap.get("healthcare_distance_km"),
                cooling_facility_coverage_pct=snap.get("cooling_facility_coverage_pct"),
                lst_source_id=lst_source_id,
                weather_source_id=weather_source_id,
                data_nature="Synthetic",
                spatial_resolution="30m (Landsat LST) / 10m (Sentinel-2)",
                missing_fields=risk_res["missing_fields"],
            )
            db.add(ind)
            db.flush()

            score_row = HeatRiskScore(
                neighbourhood_id=nb.id,
                indicator_id=ind.id,
                observation_date=obs_date,
                exposure_score=risk_res["exposure_score"],
                vulnerability_score=risk_res["vulnerability_score"],
                cooling_deficit_score=risk_res["cooling_deficit_score"],
                weight_exposure=risk_res["weight_exposure"],
                weight_vulnerability=risk_res["weight_vulnerability"],
                weight_cooling_deficit=risk_res["weight_cooling_deficit"],
                overall_risk_score=risk_res["overall_risk_score"],
                risk_category=risk_res["risk_category"],
                data_confidence_pct=risk_res["data_confidence_pct"],
                data_confidence_label=risk_res["data_confidence_label"],
                contributions=risk_res["contributions"],
                model_note=risk_res["model_note"],
            )
            db.add(score_row)

            if snap["observation_date"] == latest_date_str:
                latest_ind_dict = snap
                latest_risk_dict = risk_res

        # Generate initial rule-based recommendations for latest snapshot
        if latest_ind_dict and latest_risk_dict:
            recs = generate_recommendations_for_neighbourhood(
                {
                    "name": nb.name,
                    "zone": nb.zone,
                    "population_estimate": nb.population_estimate,
                },
                latest_ind_dict,
                latest_risk_dict,
            )
            for rec in recs:
                db.add(
                    CoolingRecommendation(
                        neighbourhood_id=nb.id,
                        intervention_type=rec["intervention_type"],
                        title=rec["title"],
                        rationale=rec["rationale"],
                        target_location=rec["target_location"],
                        priority_level=rec["priority_level"],
                        expected_beneficiaries=rec["expected_beneficiaries"],
                        estimated_cost_range=rec.get("estimated_cost_range"),
                        maintenance_considerations=rec["maintenance_considerations"],
                        triggered_rules=rec["triggered_rules"],
                        is_synthetic_estimate=True,
                    )
                )

    db.flush()

    # 6. Seed Sample Community Reports (approved + pending for moderation demo)
    seed_reports = [
        {
            "reference_code": "HW-RPT-1001",
            "nb_code": "AMD-NAR",
            "category": "Missing shade",
            "location_label": "Naroda GIDC Phase II Bus Stand",
            "lat": 23.069,
            "lng": 72.652,
            "description": "No overhead shade canopy at the main industrial shift bus stop; over 200 factory workers wait in direct afternoon sun.",
            "submission_date": date(2026, 5, 10),
            "priority": "Critical",
            "moderation_status": "Approved",
            "workflow_status": "In progress",
            "moderator_notes": "Verified by Ward 14 inspector. Temporary cool-net shade approved.",
        },
        {
            "reference_code": "HW-RPT-1002",
            "nb_code": "AMD-VAT",
            "category": "Unavailable drinking water",
            "location_label": "Vatva Labour Naka Chowk",
            "lat": 22.971,
            "lng": 72.634,
            "description": "Public water tap has been dry for two weeks; construction and industrial workers lack potable drinking water nearby.",
            "submission_date": date(2026, 5, 12),
            "priority": "Critical",
            "moderation_status": "Approved",
            "workflow_status": "Planned",
            "moderator_notes": "Scheduled for solar-chilled water kiosk installation.",
        },
        {
            "reference_code": "HW-RPT-1003",
            "nb_code": "AMD-JAM",
            "category": "Extremely hot public spaces",
            "location_label": "Jamalpur Vegetable Market Lane",
            "lat": 23.011,
            "lng": 72.583,
            "description": "Asphalt market lane traps extreme afternoon heat; vendors with tin stalls report severe heat dizziness after 1 PM.",
            "submission_date": date(2026, 5, 14),
            "priority": "High",
            "moderation_status": "Approved",
            "workflow_status": "Under review",
            "moderator_notes": "Evaluated for cool-paving pilot and overhead misting canopy.",
        },
        {
            "reference_code": "HW-RPT-1004",
            "nb_code": "AMD-DAN",
            "category": "Lack of trees",
            "location_label": "Dani Limda Municipal Primary School Approach",
            "lat": 22.997,
            "lng": 72.586,
            "description": "Zero avenue trees along the 600m approach road to the primary school; students walk exposed during noon dismissal.",
            "submission_date": date(2026, 5, 15),
            "priority": "High",
            "moderation_status": "Approved",
            "workflow_status": "Planned",
            "moderator_notes": "Included in monsoon pre-pit avenue plantation list.",
        },
        {
            "reference_code": "HW-RPT-1005",
            "nb_code": "AMD-KAL",
            "category": "Poorly maintained cooling facilities",
            "location_label": "Kalupur East Auto Stand Water Pyao",
            "lat": 23.027,
            "lng": 72.603,
            "description": "Cooling fan and water dispenser filter at the municipal shelter are non-functional and need urgent servicing.",
            "submission_date": date(2026, 5, 17),
            "priority": "High",
            "moderation_status": "Pending",
            "workflow_status": "Reported",
            "moderator_notes": None,
        },
        {
            "reference_code": "HW-RPT-1006",
            "nb_code": "AMD-ODH",
            "category": "Missing shade",
            "location_label": "Odhav Ring Road Transit Crossing",
            "lat": 23.026,
            "lng": 72.658,
            "description": "Long pedestrian signal wait without any shaded shelter near the industrial junction.",
            "submission_date": date(2026, 5, 18),
            "priority": "Medium",
            "moderation_status": "Pending",
            "workflow_status": "Reported",
            "moderator_notes": None,
        },
    ]

    report_map = {}
    for r in seed_reports:
        nb = nb_by_code[r["nb_code"]]
        rep = CommunityReport(
            reference_code=r["reference_code"],
            neighbourhood_id=nb.id,
            submitted_by_user_id=resident_user.id,
            category=r["category"],
            location_label=r["location_label"],
            latitude=r["lat"],
            longitude=r["lng"],
            description=r["description"],
            submission_date=r["submission_date"],
            priority=r["priority"],
            moderation_status=r["moderation_status"],
            workflow_status=r["workflow_status"],
            moderator_notes=r["moderator_notes"],
            moderated_by_user_id=admin_user.id if r["moderation_status"] != "Pending" else None,
        )
        db.add(rep)
        db.flush()
        report_map[r["reference_code"]] = rep

    # 8 & 9. Seed Interventions & InterventionHistory across all 5 statuses
    seed_interventions = [
        {
            "code": "INT-2026-01",
            "nb_code": "AMD-NAR",
            "report_code": "HW-RPT-1001",
            "title": "Naroda GIDC Bus Stand Modular Shade Canopy",
            "type": "Installation of shade structures",
            "location": "Naroda GIDC Phase II Main Transit Stop",
            "priority": "Critical",
            "status": "In progress",
            "dept": "Municipal Engineering & BRTS Cell",
            "cost": "INR 8.5 Lakhs (estimated)",
            "beneficiaries": "~4,200 daily factory commuters",
            "steps": [
                ("Reported", "Resident report HW-RPT-1001 logged for unshaded transit wait zone.", 8),
                ("Under review", "Site inspection confirmed peak LST > 50°C and zero overhead shelter.", 6),
                ("Planned", "Budget sanctioned under Ahmedabad Heat Action Plan 2026.", 4),
                ("In progress", "Steel frame foundation laid; UV tensile canopy installation underway.", 1),
            ],
        },
        {
            "code": "INT-2026-02",
            "nb_code": "AMD-VAT",
            "report_code": "HW-RPT-1002",
            "title": "Vatva Labour Naka Solar-Chilled Drinking Water Kiosk",
            "type": "Public drinking-water facilities",
            "location": "Vatva Labour Naka & Phase IV Junction",
            "priority": "Critical",
            "status": "Planned",
            "dept": "Water Supply & Health Department",
            "cost": "INR 6.0 Lakhs (estimated)",
            "beneficiaries": "~3,800 outdoor workers & pedestrians",
            "steps": [
                ("Reported", "Community alert HW-RPT-1002 flagged non-functional water supply.", 6),
                ("Under review", "Water department verified pipeline pressure drop and high heat exposure.", 4),
                ("Planned", "Work order issued for 2 solar-chilled water ATMs with ORS stock.", 2),
            ],
        },
        {
            "code": "INT-2026-03",
            "nb_code": "AMD-JAM",
            "report_code": None,
            "title": "Jamalpur Low-Income Housing Cool-Roof Lime Drive (Phase 1)",
            "type": "Cool-roof initiatives",
            "location": "Jamalpur Ward 23 Dense Chawls (320 roofs)",
            "priority": "Critical",
            "status": "Completed",
            "dept": "Housing Resilience & NGO Partners",
            "cost": "INR 14.2 Lakhs (actual municipal-NGO joint)",
            "beneficiaries": "~1,450 residents in tin/asbestos-roof homes",
            "steps": [
                ("Under review", "Landsat thermal hotspot scan flagged Jamalpur roof clusters > 49°C LST.", 25),
                ("Planned", "Partner NGO trained local youth applicators for white solar-reflective coating.", 18),
                ("In progress", "320 priority roofs coated across blocks A–D.", 10),
                ("Completed", "Phase 1 completed with post-application rooftop audit logged.", 3),
            ],
        },
        {
            "code": "INT-2026-04",
            "nb_code": "AMD-DAN",
            "report_code": "HW-RPT-1004",
            "title": "Dani Limda School Corridor Avenue Tree Plantation",
            "type": "Shaded walking routes",
            "location": "Dani Limda Primary School 600m Approach Road",
            "priority": "High",
            "status": "Planned",
            "dept": "Parks & Urban Forestry Department",
            "cost": "INR 7.2 Lakhs (estimated)",
            "beneficiaries": "~1,900 students & senior residents",
            "steps": [
                ("Reported", "School parent community flagged unshaded walking path (HW-RPT-1004).", 4),
                ("Planned", "180 native Neem & Karanj saplings + rest benches scheduled for planting.", 2),
            ],
        },
        {
            "code": "INT-2026-05",
            "nb_code": "AMD-MAN",
            "report_code": None,
            "title": "Maninagar Pocket Green Buffer & Permeable Walk",
            "type": "Green-space development",
            "location": "Maninagar East Municipal Plot #12",
            "priority": "Medium",
            "status": "Under review",
            "dept": "Urban Planning Cell",
            "cost": "INR 22.0 Lakhs (estimated)",
            "beneficiaries": "~5,500 nearby residents",
            "steps": [
                ("Reported", "Identified during ward green-gap audit.", 5),
                ("Under review", "Land title clearance and soil percolation survey in progress.", 2),
            ],
        },
    ]

    for item in seed_interventions:
        nb = nb_by_code[item["nb_code"]]
        rep = report_map.get(item["report_code"]) if item["report_code"] else None
        inv = Intervention(
            code=item["code"],
            neighbourhood_id=nb.id,
            source_report_id=rep.id if rep else None,
            title=item["title"],
            intervention_type=item["type"],
            target_location=item["location"],
            priority=item["priority"],
            status=item["status"],
            assigned_department=item["dept"],
            estimated_cost_range=item["cost"],
            expected_beneficiaries=item["beneficiaries"],
            assigned_by_user_id=admin_user.id,
            target_completion_date=date(2026, 6, 30),
        )
        db.add(inv)
        db.flush()

        prev = None
        for new_st, note_txt, days_ago in item["steps"]:
            db.add(
                InterventionHistory(
                    intervention_id=inv.id,
                    previous_status=prev,
                    new_status=new_st,
                    note=note_txt,
                    changed_by_user_id=admin_user.id,
                    changed_by_name=admin_user.full_name,
                    changed_at=datetime.utcnow() - timedelta(days=days_ago),
                )
            )
            prev = new_st

    db.commit()
