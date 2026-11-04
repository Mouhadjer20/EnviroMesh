"""Telemetry API routes.

Lecture des mesures (gaz, température, humidité, fuite d'eau, pression,
mouvement) depuis TimescaleDB. L'ingestion se fait par MQTT / LoRa.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from services import database_access as db

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/", response_model=list[dict])
def get_telemetry(
    device_id: Optional[str] = Query(None),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=5000),
):
    """Mesures, plus récentes en premier, filtrables par nœud et par période."""
    return db.list_telemetry(device_id, start, end, limit)


@router.get("/latest", response_model=list[dict])
def get_latest_for_all_devices():
    """Dernière mesure de chaque nœud."""
    return db.latest_telemetry()


@router.get("/{device_id}/latest", response_model=dict)
def get_latest_telemetry(device_id: str):
    """Dernière mesure d'un nœud."""
    rows = db.latest_telemetry(device_id)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No telemetry found")
    return rows[0]
