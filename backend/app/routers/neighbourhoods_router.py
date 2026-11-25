"""Neighbourhood GIS, Environmental Indicator & Live Risk Score endpoints."""

import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT
from app.database import get_db
from app.data_integrations import fetch_open_meteo_current, get_integration_status
from app.models import CommunityReport, DataSource, EnvironmentalIndicator, HeatRiskScore, Intervention, Neighbourhood
from app.risk_engine import compute_heat_risk
from app.schemas import RiskWeightsInput

router = APIRouter(prefix="/neighbourhoods", tags=["Neighbourhoods & Map"])


def _serialize_neighbourhood_snapshot(
    nb: Neighbourhood,
    ind: Optional[EnvironmentalIndicator],
    score: Optional[HeatRiskScore],
    approved_reports_count: int,
    active_interventions_count: int,
    custom_weights: Optional[dict] = None,
) -> dict:
    ind_dict = {}
    if ind:
        ind_dict = {
            "observation_date": ind.observation_date.isoformat(),
            "land_surface_temp_c": ind.land_surface_temp_c,
            "air_temp_c": ind.air_temp_c,
            "relative_humidity_pct": ind.relative_humidity_pct,
            "ndvi_vegetation_pct": ind.ndvi_vegetation_pct,
            "built_up_intensity_pct": ind.built_up_intensity_pct,
            "albedo_index": ind.albedo_index,
            "elderly_pct": ind.elderly_pct,
            "low_income_housing_pct": ind.low_income_housing_pct,
            "outdoor_worker_pct": ind.outdoor_worker_pct,
            "healthcare_distance_km": ind.healthcare_distance_km,
            "cooling_facility_coverage_pct": ind.cooling_facility_coverage_pct,
            "data_nature": ind.data_nature,
            "spatial_resolution": ind.spatial_resolution,
            "missing_fields": ind.missing_fields or [],
        }

    if custom_weights and ind:
        risk_dict = compute_heat_risk(ind_dict, weights=custom_weights, data_nature=ind.data_nature)
    elif score:
        risk_dict = {
            "exposure_score": score.exposure_score,
            "vulnerability_score": score.vulnerability_score,
            "cooling_deficit_score": score.cooling_deficit_score,
            "weight_exposure": score.weight_exposure,
            "weight_vulnerability": score.weight_vulnerability,
            "weight_cooling_deficit": score.weight_cooling_deficit,
            "overall_risk_score": score.overall_risk_score,
            "risk_category": score.risk_category,
            "data_confidence_pct": score.data_confidence_pct,
            "data_confidence_label": score.data_confidence_label,
            "contributions": score.contributions,
            "model_note": score.model_note,
        }
    else:
        risk_dict = None

    return {
        "id": nb.id,
        "code": nb.code,
        "name": nb.name,
        "city": nb.city,
        "zone": nb.zone,
        "ward_number": nb.ward_number,
        "population_estimate": nb.population_estimate,
        "area_sq_km": nb.area_sq_km,
        "centroid_lat": nb.centroid_lat,
        "centroid_lng": nb.centroid_lng,
        "boundary_geojson": nb.boundary_geojson,
        "cooling_shelters_count": nb.cooling_shelters_count,
        "public_water_points_count": nb.public_water_points_count,
        "approved_reports_count": approved_reports_count,
        "active_interventions_count": active_interventions_count,
        "indicators": ind_dict,
        "risk": risk_dict,
    }


@router.get("")
def list_neighbourhoods(
    search: Optional[str] = Query(default=None, max_length=80),
    risk_category: Optional[str] = Query(default=None),
    observation_date: Optional[date] = Query(default=None),
    w_exposure: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    w_vulnerability: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    w_cooling: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    query = db.query(Neighbourhood)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter((Neighbourhood.name.ilike(pattern)) | (Neighbourhood.zone.ilike(pattern)) | (Neighbourhood.ward_number.ilike(pattern)))
    neighbourhoods = query.order_by(Neighbourhood.name).all()

    custom_weights = None
    if w_exposure is not None and w_vulnerability is not None and w_cooling is not None:
        if (w_exposure + w_vulnerability + w_cooling) > 0:
            custom_weights = {
                "exposure": w_exposure,
                "vulnerability": w_vulnerability,
                "cooling_deficit": w_cooling,
            }

    results = []
    for nb in neighbourhoods:
        ind_q = db.query(EnvironmentalIndicator).filter(EnvironmentalIndicator.neighbourhood_id == nb.id)
        if observation_date:
            ind = ind_q.filter(EnvironmentalIndicator.observation_date == observation_date).first()
        else:
            ind = ind_q.order_by(desc(EnvironmentalIndicator.observation_date)).first()

        score = None
        if ind:
            score = (
                db.query(HeatRiskScore)
                .filter(HeatRiskScore.neighbourhood_id == nb.id, HeatRiskScore.observation_date == ind.observation_date)
                .order_by(desc(HeatRiskScore.calculated_at))
                .first()
            )

        approved_reports = (
            db.query(CommunityReport)
            .filter(CommunityReport.neighbourhood_id == nb.id, CommunityReport.moderation_status == "Approved")
            .count()
        )
        active_interventions = (
            db.query(Intervention)
            .filter(Intervention.neighbourhood_id == nb.id)
            .count()
        )

        serialized = _serialize_neighbourhood_snapshot(
            nb, ind, score, approved_reports, active_interventions, custom_weights=custom_weights
        )
        if risk_category and serialized["risk"] and serialized["risk"]["risk_category"] != risk_category:
            continue
        results.append(serialized)

    # Cooling infrastructure overlay points
    sample_path = PROJECT_ROOT / "data" / "ahmedabad_heat_sample.json"
    cooling_assets = []
    if sample_path.exists():
        with open(sample_path, "r", encoding="utf-8") as f:
            cooling_assets = json.load(f).get("cooling_assets", [])

    return {
        "city": "Ahmedabad",
        "data_disclaimer": "Satellite LST, vegetation, and Census vulnerability metrics are clearly labelled Synthetic/Estimated demo indicators unless live APIs are configured.",
        "count": len(results),
        "neighbourhoods": results,
        "cooling_assets": cooling_assets,
    }


@router.get("/data-sources")
def get_data_sources(db: Session = Depends(get_db)):
    sources = db.query(DataSource).order_by(DataSource.id).all()
    return {
        "sources": [
            {
                "id": s.id,
                "code": s.code,
                "name": s.name,
                "provider": s.provider,
                "category": s.category,
                "spatial_resolution": s.spatial_resolution,
                "update_cadence": s.update_cadence,
                "data_nature": s.data_nature,
                "requires_api_key": s.requires_api_key,
                "status": s.status,
                "last_synced_at": s.last_synced_at.isoformat() if s.last_synced_at else None,
                "notes": s.notes,
            }
            for s in sources
        ],
        "integrations": get_integration_status(),
    }


@router.get("/{neighbourhood_id}")
async def get_neighbourhood_detail(
    neighbourhood_id: int,
    include_live_weather: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    nb = db.query(Neighbourhood).filter(Neighbourhood.id == neighbourhood_id).first()
    if not nb:
        raise HTTPException(status_code=404, detail="Neighbourhood not found.")

    ind = (
        db.query(EnvironmentalIndicator)
        .filter(EnvironmentalIndicator.neighbourhood_id == nb.id)
        .order_by(desc(EnvironmentalIndicator.observation_date))
        .first()
    )
    score = None
    if ind:
        score = (
            db.query(HeatRiskScore)
            .filter(HeatRiskScore.neighbourhood_id == nb.id, HeatRiskScore.observation_date == ind.observation_date)
            .order_by(desc(HeatRiskScore.calculated_at))
            .first()
        )

    approved_reports = (
        db.query(CommunityReport)
        .filter(CommunityReport.neighbourhood_id == nb.id, CommunityReport.moderation_status == "Approved")
        .count()
    )
    active_interventions = db.query(Intervention).filter(Intervention.neighbourhood_id == nb.id).count()

    data = _serialize_neighbourhood_snapshot(nb, ind, score, approved_reports, active_interventions)

    # Historical snapshots for this neighbourhood
    history_scores = (
        db.query(HeatRiskScore)
        .filter(HeatRiskScore.neighbourhood_id == nb.id)
        .order_by(HeatRiskScore.observation_date)
        .all()
    )
    data["history"] = [
        {
            "observation_date": h.observation_date.isoformat(),
            "overall_risk_score": h.overall_risk_score,
            "exposure_score": h.exposure_score,
            "vulnerability_score": h.vulnerability_score,
            "cooling_deficit_score": h.cooling_deficit_score,
            "risk_category": h.risk_category,
        }
        for h in history_scores
    ]

    if include_live_weather:
        live = await fetch_open_meteo_current(nb.centroid_lat, nb.centroid_lng)
        data["live_air_weather"] = live or {
            "air_temp_c": ind.air_temp_c if ind else None,
            "relative_humidity_pct": ind.relative_humidity_pct if ind else None,
            "source": "Demo Sample Fallback (Open-Meteo unavailable or offline)",
            "data_nature": "Synthetic",
        }

    return data


@router.post("/{neighbourhood_id}/recalculate")
def recalculate_neighbourhood_risk(
    neighbourhood_id: int,
    weights: RiskWeightsInput,
    db: Session = Depends(get_db),
):
    nb = db.query(Neighbourhood).filter(Neighbourhood.id == neighbourhood_id).first()
    if not nb:
        raise HTTPException(status_code=404, detail="Neighbourhood not found.")

    ind = (
        db.query(EnvironmentalIndicator)
        .filter(EnvironmentalIndicator.neighbourhood_id == nb.id)
        .order_by(desc(EnvironmentalIndicator.observation_date))
        .first()
    )
    if not ind:
        raise HTTPException(status_code=404, detail="No indicators available for this neighbourhood.")

    ind_dict = {
        "land_surface_temp_c": ind.land_surface_temp_c,
        "air_temp_c": ind.air_temp_c,
        "ndvi_vegetation_pct": ind.ndvi_vegetation_pct,
        "built_up_intensity_pct": ind.built_up_intensity_pct,
        "albedo_index": ind.albedo_index,
        "elderly_pct": ind.elderly_pct,
        "low_income_housing_pct": ind.low_income_housing_pct,
        "outdoor_worker_pct": ind.outdoor_worker_pct,
        "healthcare_distance_km": ind.healthcare_distance_km,
        "cooling_facility_coverage_pct": ind.cooling_facility_coverage_pct,
    }
    return compute_heat_risk(ind_dict, weights=weights.model_dump(), data_nature=ind.data_nature)
