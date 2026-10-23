"""Telemetry API routes.

Endpoints for querying time-series sensor telemetry (gas, temperature,
humidity, water leak, pressure, motion) from TimescaleDB.
"""

from fastapi import APIRouter, Query, Depends, HTTPException, status
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/", response_model=List[dict])
async def get_telemetry(
    device_id: Optional[str] = Query(None),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(100, le=1000),
):
    """Query telemetry readings, optionally filtered by device and time range."""
    # TODO: Implement telemetry query from TimescaleDB
    return []


@router.get("/{device_id}/latest", response_model=dict)
async def get_latest_telemetry(device_id: str):
    """Get the most recent telemetry reading for a device."""
    # TODO: Implement latest reading lookup
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No telemetry found")