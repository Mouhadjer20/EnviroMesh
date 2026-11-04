"""Groups API routes."""

from fastapi import APIRouter

from services import database_access as db

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("/", response_model=list[dict])
def list_groups():
    """Groupes configurés, y compris ceux qui n'ont pas encore de nœud."""
    return db.list_groups()
