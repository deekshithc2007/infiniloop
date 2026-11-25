"""Pydantic schemas for strict input validation and clean API responses."""

from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# --- Auth ---
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)
    organisation: Optional[str] = Field(default=None, max_length=120)


class UserLogin(BaseModel):
    username: str = Field(..., min_length=2, max_length=80)
    password: str = Field(..., min_length=4, max_length=100)


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: str
    organisation: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# --- Risk Engine ---
class RiskWeightsInput(BaseModel):
    exposure: float = Field(default=0.40, ge=0.0, le=1.0)
    vulnerability: float = Field(default=0.35, ge=0.0, le=1.0)
    cooling_deficit: float = Field(default=0.25, ge=0.0, le=1.0)

    @field_validator("cooling_deficit")
    @classmethod
    def check_nonzero_total(cls, v, info):
        total = (info.data.get("exposure") or 0.0) + (info.data.get("vulnerability") or 0.0) + v
        if total <= 0.0:
            raise ValueError("At least one indicator weight must be greater than zero.")
        return v


# --- Community Reports ---
ReportCategory = Literal[
    "Missing shade",
    "Unavailable drinking water",
    "Extremely hot public spaces",
    "Lack of trees",
    "Poorly maintained cooling facilities",
]


class CommunityReportCreate(BaseModel):
    neighbourhood_id: int = Field(..., ge=1)
    category: ReportCategory
    location_label: str = Field(..., min_length=3, max_length=180)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    description: str = Field(..., min_length=10, max_length=1200)
    submission_date: Optional[date] = None
    # Basic spam protection fields
    website_honeypot: Optional[str] = Field(default="", max_length=100)
    human_check_answer: int = Field(..., description="Sum check for basic spam prevention")
    human_check_expected: int = Field(..., description="Expected sum check")


class ReportModerateInput(BaseModel):
    moderation_status: Literal["Pending", "Approved", "Rejected"]
    priority: Literal["Critical", "High", "Medium", "Low"]
    workflow_status: Literal["Reported", "Under review", "Planned", "In progress", "Completed"]
    moderator_notes: Optional[str] = Field(default=None, max_length=500)


# --- Interventions ---
InterventionStatus = Literal["Reported", "Under review", "Planned", "In progress", "Completed"]


class InterventionCreate(BaseModel):
    neighbourhood_id: int = Field(..., ge=1)
    recommendation_id: Optional[int] = None
    source_report_id: Optional[int] = None
    title: str = Field(..., min_length=4, max_length=180)
    intervention_type: str = Field(..., min_length=3, max_length=100)
    target_location: str = Field(..., min_length=3, max_length=200)
    priority: Literal["Critical", "High", "Medium", "Low"] = "High"
    status: InterventionStatus = "Planned"
    assigned_department: Optional[str] = Field(default="Municipal Heat Action Cell", max_length=140)
    estimated_cost_range: Optional[str] = Field(default=None, max_length=120)
    expected_beneficiaries: Optional[str] = Field(default=None, max_length=180)
    target_completion_date: Optional[date] = None
    note: str = Field(default="Intervention assigned from HeatWise AI platform.", max_length=500)


class InterventionStatusUpdate(BaseModel):
    status: InterventionStatus
    note: str = Field(..., min_length=3, max_length=500)
    assigned_department: Optional[str] = Field(default=None, max_length=140)
