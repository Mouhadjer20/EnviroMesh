"""Group registry and administrative membership routes."""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import group_store
from services.auth import get_current_user, require_admin, scope_group

router = APIRouter(prefix="/groups", tags=["groups"])
_GROUP = r"^G[1-9]$"

class GroupCreate(BaseModel):
    group_code: str = Field(pattern=_GROUP)
    description: str = Field(min_length=1, max_length=255)


class GroupUpdate(BaseModel):
    description: str = Field(min_length=1, max_length=255)


@router.get("/", response_model=list[dict])
def list_groups(user: dict = Depends(get_current_user)):
    """Groupes configurés (un technicien ne voit que le sien)."""
    return group_store.list_groups(group_code=scope_group(user))


@router.post("/", status_code=201, response_model=dict)
def create_group(body: GroupCreate, admin: dict = Depends(require_admin)):
    return group_store.create_group(body.group_code, body.description.strip())


@router.put("/{group_code}", response_model=dict)
def update_group(group_code: str, body: GroupUpdate, admin: dict = Depends(require_admin)):
    if not re.fullmatch(_GROUP, group_code):
        raise HTTPException(status_code=404, detail="Group not found")
    group = group_store.update_group(group_code, body.description.strip())
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.put("/{group_code}/devices/{device_id}", response_model=dict)
def assign_device(group_code: str, device_id: str, admin: dict = Depends(require_admin)):
    if not re.fullmatch(_GROUP, group_code):
        raise HTTPException(status_code=404, detail="Group not found")
    if not group_store.assign_device(group_code, device_id):
        raise HTTPException(status_code=404, detail="Group or device not found")
    return {"group_code": group_code, "device_id": device_id}
