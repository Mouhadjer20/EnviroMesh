"""User management API routes.

Endpoints for user registration, profile management, and role-based
access control (admin / zone_technician).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=List[dict])
async def list_users():
    """List all users (admin only)."""
    # TODO: Implement user listing
    return []


@router.get("/{user_id}", response_model=dict)
async def get_user(user_id: str):
    """Get a single user by ID."""
    # TODO: Implement user lookup
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=dict)
async def register_user(user: dict):
    """Register a new user."""
    # TODO: Implement user registration with bcrypt hashing
    return user


@router.put("/{user_id}", response_model=dict)
async def update_user(user_id: str, user: dict):
    """Update a user's profile or role."""
    # TODO: Implement user update
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str):
    """Delete a user account."""
    # TODO: Implement user deletion
    return None