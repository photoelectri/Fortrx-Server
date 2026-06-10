from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_active_user, get_current_token_payload
from app.middleware.rate_limit import limiter
from app.models import User
from app.schemas import DeviceLinkCompleteRequest, DeviceLinkCompleteResponse, DeviceLinkStartResponse, DeviceResponse
from app.services.device_service import complete_device_link, list_devices, revoke_device, start_device_link


router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceResponse])
def get_devices(
    current_user: User = Depends(get_active_user),
    token_payload: dict = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
):
    return list_devices(db, current_user, token_payload.get("device_id"))


@router.delete("/{device_id}", status_code=204)
def delete_device(
    device_id: str,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    revoke_device(db, current_user, device_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/link/start", response_model=DeviceLinkStartResponse)
def link_start(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    return start_device_link(db, current_user)


@router.post("/link/complete", response_model=DeviceLinkCompleteResponse)
@limiter.limit("5/15minute")
def link_complete(
    request: Request,
    payload: DeviceLinkCompleteRequest,
    db: Session = Depends(get_db),
):
    return complete_device_link(db, payload.pairing_token, payload.code, payload.identity_pub, payload.device_name)
