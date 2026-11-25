"""Public & Admin Cooling Intervention Tracking endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Intervention, InterventionHistory, Neighbourhood

router = APIRouter(prefix="/interventions", tags=["Interventions"])


def serialize_intervention(inv: Intervention, nb_name: str, history_rows: list) -> dict:
    return {
        "id": inv.id,
        "code": inv.code,
        "neighbourhood_id": inv.neighbourhood_id,
        "neighbourhood_name": nb_name,
        "recommendation_id": inv.recommendation_id,
        "source_report_id": inv.source_report_id,
        "title": inv.title,
        "intervention_type": inv.intervention_type,
        "target_location": inv.target_location,
        "priority": inv.priority,
        "status": inv.status,
        "assigned_department": inv.assigned_department,
        "estimated_cost_range": inv.estimated_cost_range,
        "expected_beneficiaries": inv.expected_beneficiaries,
        "target_completion_date": inv.target_completion_date.isoformat() if inv.target_completion_date else None,
        "created_at": inv.created_at.isoformat(),
        "updated_at": inv.updated_at.isoformat(),
        "history": [
            {
                "id": h.id,
                "previous_status": h.previous_status,
                "new_status": h.new_status,
                "note": h.note,
                "changed_by_name": h.changed_by_name,
                "changed_at": h.changed_at.isoformat(),
            }
            for h in history_rows
        ],
    }


@router.get("")
def list_interventions(
    neighbourhood_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Intervention, Neighbourhood.name).join(
        Neighbourhood, Intervention.neighbourhood_id == Neighbourhood.id
    )
    if neighbourhood_id:
        query = query.filter(Intervention.neighbourhood_id == neighbourhood_id)
    if status:
        query = query.filter(Intervention.status == status)

    rows = query.order_by(desc(Intervention.updated_at), desc(Intervention.id)).all()
    items = []
    for inv, nb_name in rows:
        hist = (
            db.query(InterventionHistory)
            .filter(InterventionHistory.intervention_id == inv.id)
            .order_by(desc(InterventionHistory.changed_at), desc(InterventionHistory.id))
            .all()
        )
        items.append(serialize_intervention(inv, nb_name, hist))

    return {"count": len(items), "interventions": items}
