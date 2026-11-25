"""HeatWise AI FastAPI Application Entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.routers import (
    admin_router,
    analytics_router,
    auth_router,
    interventions_router,
    neighbourhoods_router,
    recommendations_router,
    reports_router,
)
from app.seed import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="HeatWise AI API",
    description="Neighbourhood Heat Intelligence, Vulnerability Analysis & Cooling Action Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

app.include_router(auth_router.router, prefix="/api")
app.include_router(neighbourhoods_router.router, prefix="/api")
app.include_router(analytics_router.router, prefix="/api")
app.include_router(recommendations_router.router, prefix="/api")
app.include_router(reports_router.router, prefix="/api")
app.include_router(interventions_router.router, prefix="/api")
app.include_router(admin_router.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
        "dataset_mode": "Synthetic / Demo Sample Dataset with Optional Open-Meteo Live Weather",
    }
