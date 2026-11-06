"""Authentication routes: login, current user, password change."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from services import auth, user_store

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=12, max_length=200)


class ProfileUpdate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

@router.post("/login")
def login(body: LoginRequest):
    email = body.email.strip().lower()
    auth.check_throttle(email)
    user = user_store.authenticate(email, body.password)
    if not user:
        auth.record_failure(email)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    auth.clear_failures(email)
    return {"access_token": auth.create_token(user), "token_type": "bearer",
            "expires_in": auth.EXPIRE_MINUTES * 60, "user": user}


@router.get("/me")
def me(user: dict = Depends(auth.get_authenticated_user)):
    return user


@router.put("/profile")
def update_profile(body: ProfileUpdate, user: dict = Depends(auth.get_authenticated_user)):
    if user["id"] is None:
        raise HTTPException(status_code=400, detail="Not available when authentication is disabled")
    first_name, last_name = body.first_name.strip(), body.last_name.strip()
    if not first_name or not last_name:
        raise HTTPException(status_code=422, detail="First and last names are required")
    updated = user_store.update_profile(user["id"], first_name, last_name, body.email)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return updated


@router.post("/change-password", status_code=204)
def change_password(body: PasswordChange, user: dict = Depends(auth.get_authenticated_user)):
    if user["id"] is None:
        raise HTTPException(status_code=400, detail="Not available when authentication is disabled")
    if not user_store.change_password(user["id"], body.current_password, body.new_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    return Response(status_code=204)
