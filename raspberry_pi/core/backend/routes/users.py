"""User management (administrators only). Accounts are deactivated, never deleted."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from services import user_store
from services.auth import require_admin

router = APIRouter(prefix="/users", tags=["users"])

_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
_GROUP = r"^G[1-9]$"


class UserCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=_EMAIL, max_length=255)
    password: str = Field(min_length=12, max_length=200)
    role: Literal["admin", "zone_technician"] = "zone_technician"
    group_code: Optional[str] = Field(None, pattern=_GROUP)


class UserUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[str] = Field(None, pattern=_EMAIL, max_length=255)
    role: Optional[Literal["admin", "zone_technician"]] = None
    group_code: Optional[str] = Field(None, pattern=_GROUP)
    active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=12, max_length=200)


def _guard_self(admin: dict, user_id: str, changes: dict):
    """Stops an administrator from locking themselves out."""
    if str(admin["id"]) == user_id and "password" in changes:
        raise HTTPException(status_code=400, detail="Use profile settings to change your own password")
    if str(admin["id"]) == user_id and (changes.get("active") is False or changes.get("role", "admin") != "admin"):
        raise HTTPException(status_code=400, detail="You cannot deactivate or demote your own account")


def _found(user):
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/", response_model=list[dict])
def list_users(admin: dict = Depends(require_admin)):
    return user_store.list_users()


@router.post("/", status_code=201, response_model=dict)
def create_user(body: UserCreate, admin: dict = Depends(require_admin)):
    if body.role == "zone_technician" and not body.group_code:
        raise HTTPException(status_code=422, detail="Zone technicians must be assigned to a group")
    return user_store.create_user(body.first_name, body.last_name, body.email, body.password,
                                  body.role, body.group_code)


@router.get("/{user_id}", response_model=dict)
def get_user(user_id: str, admin: dict = Depends(require_admin)):
    return _found(user_store.get_user(user_id, include_inactive=True))


@router.put("/{user_id}", response_model=dict)
def update_user(user_id: str, body: UserUpdate, admin: dict = Depends(require_admin)):
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k == "group_code"}
    _guard_self(admin, user_id, changes)
    current = _found(user_store.get_user(user_id, include_inactive=True))
    resulting_role = changes.get("role", current["role"])
    resulting_group = changes.get("group_code", current["group_code"])
    if resulting_role == "zone_technician" and not resulting_group:
        raise HTTPException(status_code=422, detail="Zone technicians must be assigned to a group")
    return _found(user_store.update_user(user_id, changes))


@router.delete("/{user_id}", status_code=204)
def deactivate_user(user_id: str, admin: dict = Depends(require_admin)):
    _guard_self(admin, user_id, {"active": False})
    _found(user_store.update_user(user_id, {"active": False}))
    return Response(status_code=204)
