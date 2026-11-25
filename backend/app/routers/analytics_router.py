"""Heat Analytics Dashboard endpoints."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CommunityReport, EnvironmentalIndicator, HeatRiskScore, Intervention, Neighbourhood

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary")
def get_analytics_summary(
    neighbourhood_id: Optional[int] = Query(default=None),
    observation_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
):
    available_dates = [
        d[0].isoformat()
        for d in db.query(EnvironmentalIndicator.observation_date)
        .distinct()
        .order_by(EnvironmentalIndicator.observation_date)
        .all()
    ]

    nb_query = db.query(Neighbourhood)
    if neighbourhood_id:
        nb_query = nb_query.filter(Neighbourhood.id == neighbourhood_id)
    neighbourhoods = nb_query.order_by(Neighbourhood.name).all()

    target_date_str = observation_date.isoformat() if observation_date else (available_dates[-1] if available_dates else None)

    lst_values = []
    air_values = []
    veg_values = []
    risk_distribution = {"Low Risk": 0, "Moderate Risk": 0, "High Risk": 0, "Very High Risk": 0}
    comparison_rows = []
    veg_vs_lst = []

    for nb in neighbourhoods:
        ind_q = db.query(EnvironmentalIndicator).filter(EnvironmentalIndicator.neighbourhood_id == nb.id)
        if observation_date:
            ind = ind_q.filter(EnvironmentalIndicator.observation_date == observation_date).first()
        else:
            ind = ind_q.order_by(desc(EnvironmentalIndicator.observation_date)).first()

        if not ind:
            continue

        score = (
            db.query(HeatRiskScore)
            .filter(HeatRiskScore.neighbourhood_id == nb.id, HeatRiskScore.observation_date == ind.observation_date)
            .order_by(desc(HeatRiskScore.calculated_at))
            .first()
        )
        if not score:
            continue

        if ind.land_surface_temp_c is not None:
            lst_values.append(ind.land_surface_temp_c)
        if ind.air_temp_c is not None:
            air_values.append(ind.air_temp_c)
        if ind.ndvi_vegetation_pct is not None:
            veg_values.append(ind.ndvi_vegetation_pct)

        risk_distribution[score.risk_category] = risk_distribution.get(score.risk_category, 0) + 1

        comparison_rows.append({
            "neighbourhood_id": nb.id,
            "name": nb.name,
            "zone": nb.zone,
            "overall_risk_score": score.overall_risk_score,
            "risk_category": score.risk_category,
            "exposure_score": score.exposure_score,
            "vulnerability_score": score.vulnerability_score,
            "cooling_deficit_score": score.cooling_deficit_score,
            "land_surface_temp_c": ind.land_surface_temp_c,
            "air_temp_c": ind.air_temp_c,
            "vegetation_pct": ind.ndvi_vegetation_pct,
            "data_confidence_pct": score.data_confidence_pct,
        })

        if ind.ndvi_vegetation_pct is not None and ind.land_surface_temp_c is not None:
            veg_vs_lst.append({
                "name": nb.name,
                "vegetation_pct": ind.ndvi_vegetation_pct,
                "land_surface_temp_c": ind.land_surface_temp_c,
                "overall_risk_score": score.overall_risk_score,
                "risk_category": score.risk_category,
            })

    comparison_rows.sort(key=lambda r: r["overall_risk_score"], reverse=True)

    # Reports and Interventions
    rep_q = db.query(CommunityReport)
    inv_q = db.query(Intervention)
    if neighbourhood_id:
        rep_q = rep_q.filter(CommunityReport.neighbourhood_id == neighbourhood_id)
        inv_q = inv_q.filter(Intervention.neighbourhood_id == neighbourhood_id)

    total_reports = rep_q.count()
    approved_reports = rep_q.filter(CommunityReport.moderation_status == "Approved").count()
    interventions = inv_q.all()

    status_counts = {
        "Reported": 0,
        "Under review": 0,
        "Planned": 0,
        "In progress": 0,
        "Completed": 0,
    }
    for inv in interventions:
        status_counts[inv.status] = status_counts.get(inv.status, 0) + 1

    pending_interventions = sum(v for k, v in status_counts.items() if k != "Completed")

    # Risk trends over time (explicitly from historical HeatRiskScore snapshots)
    trend_map = {}
    score_q = db.query(HeatRiskScore)
    if neighbourhood_id:
        score_q = score_q.filter(HeatRiskScore.neighbourhood_id == neighbourhood_id)
    for row in score_q.order_by(HeatRiskScore.observation_date).all():
        d_str = row.observation_date.isoformat()
        bucket = trend_map.setdefault(d_str, {"risk": [], "exposure": [], "vulnerability": []})
        bucket["risk"].append(row.overall_risk_score)
        if row.exposure_score is not None:
            bucket["exposure"].append(row.exposure_score)
        if row.vulnerability_score is not None:
            bucket["vulnerability"].append(row.vulnerability_score)

    risk_trends = [
        {
            "date": d_str,
            "avg_risk_score": round(sum(b["risk"]) / len(b["risk"]), 1),
            "avg_exposure_score": round(sum(b["exposure"]) / len(b["exposure"]), 1) if b["exposure"] else None,
            "avg_vulnerability_score": round(sum(b["vulnerability"]) / len(b["vulnerability"]), 1) if b["vulnerability"] else None,
        }
        for d_str, b in sorted(trend_map.items())
    ]

    high_risk_count = risk_distribution["High Risk"] + risk_distribution["Very High Risk"]

    return {
        "observation_date": target_date_str,
        "available_dates": available_dates,
        "data_nature": "Synthetic / Demo Dataset",
        "kpis": {
            "total_neighbourhoods": len(comparison_rows),
            "high_risk_neighbourhoods": high_risk_count,
            "avg_land_surface_temp_c": round(sum(lst_values) / len(lst_values), 1) if lst_values else None,
            "avg_air_temp_c": round(sum(air_values) / len(air_values), 1) if air_values else None,
            "avg_vegetation_pct": round(sum(veg_values) / len(veg_values), 1) if veg_values else None,
            "community_reports": total_reports,
            "approved_community_reports": approved_reports,
            "pending_interventions": pending_interventions,
            "total_interventions": len(interventions),
        },
        "charts": {
            "risk_distribution": [
                {"category": k, "count": v} for k, v in risk_distribution.items()
            ],
            "neighbourhood_comparison": comparison_rows,
            "vegetation_vs_lst": veg_vs_lst,
            "intervention_progress": [
                {"status": k, "count": v} for k, v in status_counts.items()
            ],
            "risk_trends": risk_trends,
        },
    }
