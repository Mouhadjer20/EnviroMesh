"""Device registry API routes (lecture seule pour l'instant)."""

from fastapi import APIRouter, HTTPException, status

from services import database_access as db

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("/", response_model=list[dict])
def list_devices():
    """Nœuds enregistrés avec leur groupe, leur zone et leurs capteurs."""
    return db.list_devices()


@router.get("/{device_id}", response_model=dict)
def get_device(device_id: str):
    rows = db.list_devices(device_id)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return rows[0]


@router.post("/", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def register_device():
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")


@router.put("/{device_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def update_device(device_id: str):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")


@router.delete("/{device_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def delete_device(device_id: str):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")
