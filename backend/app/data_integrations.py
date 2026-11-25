"""External Data Integration Layer (Open-Meteo live connector + satellite/census adapters).

Never fabricates real-time environmental readings:
- When Open-Meteo is reachable and enabled, fetches live 2m air temperature & humidity
  and labels them explicitly as 'Real' (Open-Meteo).
- Otherwise gracefully falls back to the stored sample snapshot and labels it 'Synthetic'.
"""

from datetime import datetime
from typing import Any, Dict, Optional
import httpx

from app.config import settings


async def fetch_open_meteo_current(lat: float, lng: float) -> Optional[Dict[str, Any]]:
    """Fetch live 2m ambient air temperature & relative humidity from Open-Meteo."""
    if not settings.open_meteo_enabled:
        return None
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lng,
        "current": "temperature_2m,relative_humidity_2m",
        "timezone": "Asia/Kolkata",
    }
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                payload = resp.json()
                current = payload.get("current", {})
                if "temperature_2m" in current:
                    return {
                        "air_temp_c": float(current["temperature_2m"]),
                        "relative_humidity_pct": float(current.get("relative_humidity_2m", 0.0)),
                        "observed_at": current.get("time") or datetime.utcnow().isoformat(),
                        "source": "Open-Meteo Live API (2m Ambient Air Temperature)",
                        "data_nature": "Real",
                    }
    except Exception:
        return None
    return None


def get_integration_status() -> Dict[str, Any]:
    """Report configuration status for external satellite & weather pipelines."""
    return {
        "open_meteo": {
            "enabled": settings.open_meteo_enabled,
            "requires_api_key": False,
            "mode": "Live API with Demo Sample Fallback",
        },
        "google_earth_engine": {
            "configured": bool(settings.google_earth_engine_project_id),
            "requires_api_key": True,
            "mode": "Configured" if settings.google_earth_engine_project_id else "Demo Sample Fallback",
        },
        "nasa_landsat": {
            "configured": bool(settings.nasa_earthdata_token),
            "requires_api_key": True,
            "mode": "Configured" if settings.nasa_earthdata_token else "Demo Sample Fallback",
        },
        "sentinel_hub": {
            "configured": bool(settings.sentinel_hub_client_id and settings.sentinel_hub_client_secret),
            "requires_api_key": True,
            "mode": "Configured" if settings.sentinel_hub_client_id else "Demo Sample Fallback",
        },
    }
