"""Device management API routes.

Endpoints for registering, listing, updating, and deleting edge devices
(e.g. G11, G41, G31, G61) and their sensor associations.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("/", response_model=List[dict])
async def list_devices():
    """List all registered devices."""
    # TODO: Implement device listing from database
    return []


@router.get("/{device_id}", response_model=dict)
async def get_device(device_id: str):
    """Get a single device by its device_id."""
    # TODO: Implement device lookup
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=dict)
async def register_device(device: dict):
    """Register a new edge device."""
    # TODO: Implement device registration
    return device


@router.put("/{device_id}", response_model=dict)
async def update_device(device_id: str, device: dict):
    """Update an existing device's metadata."""
    # TODO: Implement device update
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: str):
    """Delete a device and its sensor associations."""
    # TODO: Implement device deletion
    return None