"""SQLAlchemy ORM models for all 9 HeatWise AI database tables."""

from datetime import date, datetime
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(150), unique=True, nullable=False)
    full_name = Column(String(120), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="resident")  # resident | admin | planner
    organisation = Column(String(150), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class DataSource(Base):
    __tablename__ = "data_sources"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)
    provider = Column(String(150), nullable=False)
    category = Column(String(60), nullable=False)
    spatial_resolution = Column(String(80), nullable=True)
    update_cadence = Column(String(80), nullable=True)
    data_nature = Column(String(30), nullable=False)  # Real | Derived | Estimated | Synthetic
    api_endpoint = Column(Text, nullable=True)
    requires_api_key = Column(Boolean, nullable=False, default=False)
    status = Column(String(40), nullable=False, default="Demo Fallback")
    last_synced_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)


class Neighbourhood(Base):
    __tablename__ = "neighbourhoods"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(40), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False, index=True)
    city = Column(String(80), nullable=False, default="Ahmedabad")
    zone = Column(String(80), nullable=False)
    ward_number = Column(String(30), nullable=True)
    population_estimate = Column(Integer, nullable=True)
    area_sq_km = Column(Float, nullable=True)
    centroid_lat = Column(Float, nullable=False)
    centroid_lng = Column(Float, nullable=False)
    boundary_geojson = Column(JSON, nullable=False)
    cooling_shelters_count = Column(Integer, default=0)
    public_water_points_count = Column(Integer, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    indicators = relationship("EnvironmentalIndicator", back_populates="neighbourhood", cascade="all, delete-orphan")
    risk_scores = relationship("HeatRiskScore", back_populates="neighbourhood", cascade="all, delete-orphan")
    reports = relationship("CommunityReport", back_populates="neighbourhood", cascade="all, delete-orphan")
    recommendations = relationship("CoolingRecommendation", back_populates="neighbourhood", cascade="all, delete-orphan")
    interventions = relationship("Intervention", back_populates="neighbourhood", cascade="all, delete-orphan")


class EnvironmentalIndicator(Base):
    __tablename__ = "environmental_indicators"
    __table_args__ = (UniqueConstraint("neighbourhood_id", "observation_date", name="uq_indicator_nb_date"),)

    id = Column(Integer, primary_key=True, index=True)
    neighbourhood_id = Column(Integer, ForeignKey("neighbourhoods.id", ondelete="CASCADE"), nullable=False, index=True)
    observation_date = Column(Date, nullable=False, index=True)

    # Strictly separated temperature metrics
    land_surface_temp_c = Column(Float, nullable=True)  # Satellite LST (Landsat)
    air_temp_c = Column(Float, nullable=True)  # 2m Ambient Air Temp (Open-Meteo / Weather Station)
    relative_humidity_pct = Column(Float, nullable=True)

    ndvi_vegetation_pct = Column(Float, nullable=True)
    built_up_intensity_pct = Column(Float, nullable=True)
    albedo_index = Column(Float, nullable=True)

    elderly_pct = Column(Float, nullable=True)
    low_income_housing_pct = Column(Float, nullable=True)
    outdoor_worker_pct = Column(Float, nullable=True)

    healthcare_distance_km = Column(Float, nullable=True)
    cooling_facility_coverage_pct = Column(Float, nullable=True)

    lst_source_id = Column(Integer, ForeignKey("data_sources.id"), nullable=True)
    weather_source_id = Column(Integer, ForeignKey("data_sources.id"), nullable=True)
    data_nature = Column(String(30), nullable=False, default="Synthetic")
    spatial_resolution = Column(String(80), default="30m (Landsat LST) / 10m (Sentinel-2)")
    missing_fields = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    neighbourhood = relationship("Neighbourhood", back_populates="indicators")


class HeatRiskScore(Base):
    __tablename__ = "heat_risk_scores"

    id = Column(Integer, primary_key=True, index=True)
    neighbourhood_id = Column(Integer, ForeignKey("neighbourhoods.id", ondelete="CASCADE"), nullable=False, index=True)
    indicator_id = Column(Integer, ForeignKey("environmental_indicators.id", ondelete="SET NULL"), nullable=True)
    observation_date = Column(Date, nullable=False, index=True)

    exposure_score = Column(Float, nullable=True)
    vulnerability_score = Column(Float, nullable=True)
    cooling_deficit_score = Column(Float, nullable=True)

    weight_exposure = Column(Float, nullable=False, default=0.40)
    weight_vulnerability = Column(Float, nullable=False, default=0.35)
    weight_cooling_deficit = Column(Float, nullable=False, default=0.25)

    overall_risk_score = Column(Float, nullable=False)
    risk_category = Column(String(30), nullable=False)
    data_confidence_pct = Column(Float, nullable=False)
    data_confidence_label = Column(String(20), nullable=False)
    contributions = Column(JSON, nullable=False)
    model_note = Column(Text, nullable=False)
    calculated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    neighbourhood = relationship("Neighbourhood", back_populates="risk_scores")


class CommunityReport(Base):
    __tablename__ = "community_reports"

    id = Column(Integer, primary_key=True, index=True)
    reference_code = Column(String(30), unique=True, nullable=False, index=True)
    neighbourhood_id = Column(Integer, ForeignKey("neighbourhoods.id", ondelete="CASCADE"), nullable=False, index=True)
    submitted_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    category = Column(String(80), nullable=False)
    location_label = Column(String(200), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    description = Column(Text, nullable=False)
    image_url = Column(Text, nullable=True)
    submission_date = Column(Date, nullable=False, default=date.today)

    priority = Column(String(20), nullable=False, default="Medium")
    moderation_status = Column(String(20), nullable=False, default="Pending")  # Pending | Approved | Rejected
    workflow_status = Column(String(30), nullable=False, default="Reported")  # Reported | Under review | Planned | In progress | Completed
    moderator_notes = Column(Text, nullable=True)
    moderated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    neighbourhood = relationship("Neighbourhood", back_populates="reports")


class CoolingRecommendation(Base):
    __tablename__ = "cooling_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    neighbourhood_id = Column(Integer, ForeignKey("neighbourhoods.id", ondelete="CASCADE"), nullable=False, index=True)
    intervention_type = Column(String(100), nullable=False)
    title = Column(String(180), nullable=False)
    rationale = Column(Text, nullable=False)
    target_location = Column(String(200), nullable=False)
    priority_level = Column(String(20), nullable=False)
    expected_beneficiaries = Column(String(180), nullable=False)
    estimated_cost_range = Column(String(120), nullable=True)
    maintenance_considerations = Column(Text, nullable=False)
    triggered_rules = Column(JSON, nullable=False, default=list)
    generated_by = Column(String(60), nullable=False, default="RuleEngine+ExplainableNLG")
    is_synthetic_estimate = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    neighbourhood = relationship("Neighbourhood", back_populates="recommendations")


class Intervention(Base):
    __tablename__ = "interventions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(40), unique=True, nullable=False, index=True)
    neighbourhood_id = Column(Integer, ForeignKey("neighbourhoods.id", ondelete="CASCADE"), nullable=False, index=True)
    recommendation_id = Column(Integer, ForeignKey("cooling_recommendations.id", ondelete="SET NULL"), nullable=True)
    source_report_id = Column(Integer, ForeignKey("community_reports.id", ondelete="SET NULL"), nullable=True)

    title = Column(String(180), nullable=False)
    intervention_type = Column(String(100), nullable=False)
    target_location = Column(String(200), nullable=False)
    priority = Column(String(20), nullable=False, default="High")
    status = Column(String(30), nullable=False, default="Reported")  # Reported | Under review | Planned | In progress | Completed
    assigned_department = Column(String(140), nullable=True)
    estimated_cost_range = Column(String(120), nullable=True)
    expected_beneficiaries = Column(String(180), nullable=True)
    assigned_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_completion_date = Column(Date, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    neighbourhood = relationship("Neighbourhood", back_populates="interventions")
    history = relationship("InterventionHistory", back_populates="intervention", cascade="all, delete-orphan", order_by="InterventionHistory.changed_at.desc()")


class InterventionHistory(Base):
    __tablename__ = "intervention_history"

    id = Column(Integer, primary_key=True, index=True)
    intervention_id = Column(Integer, ForeignKey("interventions.id", ondelete="CASCADE"), nullable=False, index=True)
    previous_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=False)
    note = Column(Text, nullable=False)
    changed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_by_name = Column(String(120), nullable=False)
    changed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    intervention = relationship("Intervention", back_populates="history")
