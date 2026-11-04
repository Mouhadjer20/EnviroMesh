"""Alert API routes.

Endpoints for creating, listing, and acknowledging alerts triggered by
telemetry thresholds (e.g. gas_ppm, water leak, motion detected).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/", response_model=list[dict])
async def list_alerts(
    device_id: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    limit: int = 100,
):
    """List alerts, optionally filtered by device and acknowledgment state."""
    # TODO: Implement alert listing from database
    return []


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=dict)
async def create_alert(alert: dict):
    """Create a new alert."""
    # TODO: Implement alert creation
    return alert


@router.patch("/{alert_id}/acknowledge", response_model=dict)
async def acknowledge_alert(alert_id: str):
    """Mark an alert as acknowledged."""
    # TODO: Implement alert acknowledgment
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")