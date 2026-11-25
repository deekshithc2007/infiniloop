"""Community Reporting Module endpoints with spam protection, optional image upload, and privacy-safe public views."""

import time
import uuid
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth import get_current_user_optional
from app.config import settings
from app.database import get_db
from app.models import CommunityReport, Neighbourhood, User
from app.schemas import CommunityReportCreate

router = APIRouter(prefix="/reports", tags=["Community Reports"])

# Simple in-memory IP rate limit window (max 8 submissions per 5 minutes per IP)
_RATE_BUCKETS: Dict[str, List[float]] = {}
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 3 * 1024 * 1024  # 3 MB

CATEGORY_DEFAULT_PRIORITY = {
    "Unavailable drinking water": "Critical",
    "Extremely hot public spaces": "High",
    "Missing shade": "High",
    "Poorly maintained cooling facilities": "High",
    "Lack of trees": "Medium",
}


def _check_rate_limit(client_ip: str) -> None:
    now = time.time()
    window = 300.0
    hits = [t for t in _RATE_BUCKETS.get(client_ip, []) if now - t < window]
    if len(hits) >= 8:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please wait a few minutes before submitting another report.",
        )
    hits.append(now)
    _RATE_BUCKETS[client_ip] = hits


def _serialize_public_report(rep: CommunityReport, nb_name: str) -> dict:
    """Serialize report for public views WITHOUT exposing any private submitter info."""
    return {
        "id": rep.id,
        "reference_code": rep.reference_code,
        "neighbourhood_id": rep.neighbourhood_id,
        "neighbourhood_name": nb_name,
        "category": rep.category,
        "location_label": rep.location_label,
        "latitude": rep.latitude,
        "longitude": rep.longitude,
        "description": rep.description,
        "image_url": rep.image_url,
        "submission_date": rep.submission_date.isoformat(),
        "priority": rep.priority,
        "moderation_status": rep.moderation_status,
        "workflow_status": rep.workflow_status,
        "moderator_notes": rep.moderator_notes,
        "created_at": rep.created_at.isoformat(),
    }


@router.get("")
def list_public_reports(
    neighbourhood_id: Optional[int] = Query(default=None),
    category: Optional[str] = Query(default=None),
    reference_code: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """List approved community reports (or look up a specific report by reference code)."""
    query = db.query(CommunityReport, Neighbourhood.name).join(
        Neighbourhood, CommunityReport.neighbourhood_id == Neighbourhood.id
    )
    if reference_code:
        query = query.filter(CommunityReport.reference_code == reference_code.strip().upper())
    else:
        query = query.filter(CommunityReport.moderation_status == "Approved")

    if neighbourhood_id:
        query = query.filter(CommunityReport.neighbourhood_id == neighbourhood_id)
    if category:
        query = query.filter(CommunityReport.category == category)

    rows = query.order_by(desc(CommunityReport.submission_date), desc(CommunityReport.id)).all()
    return {
        "count": len(rows),
        "reports": [_serialize_public_report(rep, nb_name) for rep, nb_name in rows],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_community_report(
    request: Request,
    neighbourhood_id: int = Form(...),
    category: str = Form(...),
    location_label: str = Form(...),
    description: str = Form(...),
    submission_date: Optional[date] = Form(default=None),
    latitude: Optional[float] = Form(default=None),
    longitude: Optional[float] = Form(default=None),
    website_honeypot: Optional[str] = Form(default=""),
    human_check_answer: int = Form(...),
    human_check_expected: int = Form(...),
    image: Optional[UploadFile] = File(default=None),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    # Honeypot & human check validation
    if website_honeypot and website_honeypot.strip():
        raise HTTPException(status_code=400, detail="Spam protection check failed.")
    if human_check_answer != human_check_expected:
        raise HTTPException(status_code=400, detail="Verification math answer is incorrect. Please try again.")

    # Validate core fields via Pydantic schema
    validated = CommunityReportCreate(
        neighbourhood_id=neighbourhood_id,
        category=category,  # type: ignore[arg-type]
        location_label=location_label.strip(),
        latitude=latitude,
        longitude=longitude,
        description=description.strip(),
        submission_date=submission_date,
        website_honeypot=website_honeypot,
        human_check_answer=human_check_answer,
        human_check_expected=human_check_expected,
    )

    nb = db.query(Neighbourhood).filter(Neighbourhood.id == validated.neighbourhood_id).first()
    if not nb:
        raise HTTPException(status_code=404, detail="Selected neighbourhood does not exist.")

    # Duplicate description guard within same neighbourhood
    dup = (
        db.query(CommunityReport)
        .filter(
            CommunityReport.neighbourhood_id == nb.id,
            CommunityReport.description == validated.description,
        )
        .first()
    )
    if dup:
        raise HTTPException(status_code=409, detail="An identical report has already been submitted for this locality.")

    image_url = None
    if image and image.filename:
        ext = Path(image.filename).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTS:
            raise HTTPException(status_code=400, detail="Unsupported image format. Allowed: JPG, PNG, WEBP.")
        content = await image.read()
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Uploaded image exceeds 3 MB limit.")
        filename = f"report_{uuid.uuid4().hex[:12]}{ext}"
        dest = Path(settings.upload_dir) / filename
        dest.write_bytes(content)
        image_url = f"/uploads/{filename}"

    ref_code = f"HW-RPT-{uuid.uuid4().hex[:6].upper()}"
    lat_val = validated.latitude if validated.latitude is not None else nb.centroid_lat
    lng_val = validated.longitude if validated.longitude is not None else nb.centroid_lng

    report = CommunityReport(
        reference_code=ref_code,
        neighbourhood_id=nb.id,
        submitted_by_user_id=user.id if user else None,
        category=validated.category,
        location_label=validated.location_label,
        latitude=lat_val,
        longitude=lng_val,
        description=validated.description,
        image_url=image_url,
        submission_date=validated.submission_date or date.today(),
        priority=CATEGORY_DEFAULT_PRIORITY.get(validated.category, "Medium"),
        moderation_status="Pending",
        workflow_status="Reported",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return {
        "message": "Report submitted successfully and queued for municipal moderation.",
        "report": _serialize_public_report(report, nb.name),
    }
