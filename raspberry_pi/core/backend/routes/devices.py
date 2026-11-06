"""Device registry API routes (lecture seule pour l'instant)."""

from fastapi import APIRouter, Depends, HTTPException, status

from services import database_access as db
from services.auth import get_current_user, require_admin, scope_group

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("/", response_model=list[dict])
def list_devices(user: dict = Depends(get_current_user)):
    """Nœuds enregistrés avec leur groupe, leur zone et leurs capteurs."""
    return db.list_devices(group_code=scope_group(user))


@router.get("/{device_id}", response_model=dict)
def get_device(device_id: str, user: dict = Depends(get_current_user)):
    rows = db.list_devices(device_id, group_code=scope_group(user))
    if not rows:  # hors périmètre = même réponse qu'un nœud inexistant
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return rows[0]


@router.post("/", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def register_device(admin: dict = Depends(require_admin)):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")


@router.put("/{device_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def update_device(device_id: str, admin: dict = Depends(require_admin)):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")


@router.delete("/{device_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def delete_device(device_id: str, admin: dict = Depends(require_admin)):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")
