"""Telemetry API routes.

Lecture des mesures depuis TimescaleDB. Un technicien ne reçoit que les mesures
des nœuds de son groupe (filtre appliqué dans la requête SQL).
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services import database_access as db
from services.auth import get_current_user, scope_group

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/", response_model=list[dict])
def get_telemetry(
    device_id: Optional[str] = Query(None),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=5000),
    user: dict = Depends(get_current_user),
):
    """Mesures, plus récentes en premier, filtrables par nœud et par période."""
    return db.list_telemetry(device_id, start, end, limit, group_code=scope_group(user))


@router.get("/latest", response_model=list[dict])
def get_latest_for_all_devices(user: dict = Depends(get_current_user)):
    """Dernière mesure de chaque nœud."""
    return db.latest_telemetry(group_code=scope_group(user))


@router.get("/{device_id}/latest", response_model=dict)
def get_latest_telemetry(device_id: str, user: dict = Depends(get_current_user)):
    """Dernière mesure d'un nœud."""
    rows = db.latest_telemetry(device_id, group_code=scope_group(user))
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No telemetry found")
    return rows[0]
