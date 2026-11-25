"""Application configuration with environment variable support."""

from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent


class Settings(BaseSettings):
    app_name: str = "HeatWise AI"
    app_env: str = "development"
    secret_key: str = "heatwise-sih-dev-secret-key-change-in-production-2026"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 720
    database_url: str = f"sqlite:///{(BASE_DIR / 'heatwise.db').as_posix()}"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    open_meteo_enabled: bool = True
    google_earth_engine_project_id: str = ""
    nasa_earthdata_token: str = ""
    sentinel_hub_client_id: str = ""
    sentinel_hub_client_secret: str = ""
    upload_dir: str = (BASE_DIR / "uploads").as_posix()

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
