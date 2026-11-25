"""Role-protected Government / Municipal Admin Dashboard endpoints."""

import csv
import io
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import (
    CommunityReport,
    Intervention,
    InterventionHistory,
    Neighbourhood,
    User,
)
from app.routers.interventions_router import serialize_intervention
from app.routers.reports_router import _serialize_public_report
from app.schemas import InterventionCreate, InterventionStatusUpdate, ReportModerateInput

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])


@router.get("/reports")
def admin_list_reports(
    priority: Optional[str] = Query(default=None),
    moderation_status: Optional[str] = Query(default=None),
    neighbourhood_id: Optional[int] = Query(default=None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(CommunityReport, Neighbourhood.name).join(
        Neighbourhood, CommunityReport.neighbourhood_id == Neighbourhood.id
    )
    if priority:
        query = query.filter(CommunityReport.priority == priority)
    if moderation_status:
        query = query.filter(CommunityReport.moderation_status == moderation_status)
    if neighbourhood_id:
        query = query.filter(CommunityReport.neighbourhood_id == neighbourhood_id)

    rows = query.order_by(desc(CommunityReport.created_at), desc(CommunityReport.id)).all()
    return {
        "count": len(rows),
        "reports": [_serialize_public_report(rep, nb_name) for rep, nb_name in rows],
    }


@router.patch("/reports/{report_id}")
def admin_moderate_report(
    report_id: int,
    payload: ReportModerateInput,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rep = db.query(CommunityReport).filter(CommunityReport.id == report_id).first()
    if not rep:
        raise HTTPException(status_code=404, detail="Community report not found.")

    rep.moderation_status = payload.moderation_status
    rep.priority = payload.priority
    rep.workflow_status = payload.workflow_status
    rep.moderator_notes = payload.moderator_notes
    rep.moderated_by_user_id = admin_user.id
    db.commit()
    db.refresh(rep)

    nb = db.query(Neighbourhood).filter(Neighbourhood.id == rep.neighbourhood_id).first()
    return {
        "message": f"Report {rep.reference_code} updated ({rep.moderation_status}).",
        "report": _serialize_public_report(rep, nb.name if nb else "Unknown"),
    }


@router.post("/interventions", status_code=201)
def admin_create_intervention(
    payload: InterventionCreate,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    nb = db.query(Neighbourhood).filter(Neighbourhood.id == payload.neighbourhood_id).first()
    if not nb:
        raise HTTPException(status_code=404, detail="Neighbourhood not found.")

    code = f"INT-2026-{uuid.uuid4().hex[:4].upper()}"
    inv = Intervention(
        code=code,
        neighbourhood_id=nb.id,
        recommendation_id=payload.recommendation_id,
        source_report_id=payload.source_report_id,
        title=payload.title,
        intervention_type=payload.intervention_type,
        target_location=payload.target_location,
        priority=payload.priority,
        status=payload.status,
        assigned_department=payload.assigned_department,
        estimated_cost_range=payload.estimated_cost_range,
        expected_beneficiaries=payload.expected_beneficiaries,
        assigned_by_user_id=admin_user.id,
        target_completion_date=payload.target_completion_date,
    )
    db.add(inv)
    db.flush()

    hist = InterventionHistory(
        intervention_id=inv.id,
        previous_status=None,
        new_status=inv.status,
        note=payload.note,
        changed_by_user_id=admin_user.id,
        changed_by_name=admin_user.full_name,
    )
    db.add(hist)

    if payload.source_report_id:
        rep = db.query(CommunityReport).filter(CommunityReport.id == payload.source_report_id).first()
        if rep:
            rep.workflow_status = payload.status
            if rep.moderation_status == "Pending":
                rep.moderation_status = "Approved"
                rep.moderated_by_user_id = admin_user.id

    db.commit()
    db.refresh(inv)
    return {
        "message": f"Intervention {inv.code} assigned.",
        "intervention": serialize_intervention(inv, nb.name, [hist]),
    }


@router.patch("/interventions/{intervention_id}/status")
def admin_update_intervention_status(
    intervention_id: int,
    payload: InterventionStatusUpdate,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    inv = db.query(Intervention).filter(Intervention.id == intervention_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Intervention not found.")

    prev_status = inv.status
    inv.status = payload.status
    if payload.assigned_department:
        inv.assigned_department = payload.assigned_department
    inv.updated_at = datetime.utcnow()

    hist = InterventionHistory(
        intervention_id=inv.id,
        previous_status=prev_status,
        new_status=payload.status,
        note=payload.note,
        changed_by_user_id=admin_user.id,
        changed_by_name=admin_user.full_name,
    )
    db.add(hist)

    if inv.source_report_id:
        rep = db.query(CommunityReport).filter(CommunityReport.id == inv.source_report_id).first()
        if rep:
            rep.workflow_status = payload.status

    db.commit()
    db.refresh(inv)

    nb = db.query(Neighbourhood).filter(Neighbourhood.id == inv.neighbourhood_id).first()
    all_hist = (
        db.query(InterventionHistory)
        .filter(InterventionHistory.intervention_id == inv.id)
        .order_by(desc(InterventionHistory.changed_at), desc(InterventionHistory.id))
        .all()
    )
    return {
        "message": f"Intervention {inv.code} transitioned from {prev_status} to {payload.status}.",
        "intervention": serialize_intervention(inv, nb.name if nb else "Unknown", all_hist),
    }


@router.get("/export/reports.csv")
def export_reports_csv(
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(CommunityReport, Neighbourhood.name)
        .join(Neighbourhood, CommunityReport.neighbourhood_id == Neighbourhood.id)
        .order_by(desc(CommunityReport.submission_date))
        .all()
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Reference Code",
        "Neighbourhood",
        "Category",
        "Location",
        "Priority",
        "Moderation Status",
        "Workflow Status",
        "Submission Date",
        "Description",
        "Moderator Notes",
    ])
    for rep, nb_name in rows:
        writer.writerow([
            rep.reference_code,
            nb_name,
            rep.category,
            rep.location_label,
            rep.priority,
            rep.moderation_status,
            rep.workflow_status,
            rep.submission_date.isoformat(),
            rep.description,
            rep.moderator_notes or "",
        ])

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=heatwise_community_reports.csv"},
    )
