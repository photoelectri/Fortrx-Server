from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_active_user
from app.models.user import User
from app.schemas.presence import PresenceContactResponse, PresenceHeartbeatResponse
from app.services import presence_service


router = APIRouter(prefix="/presence", tags=["presence"])


@router.get("/contacts", response_model=list[PresenceContactResponse])
async def contacts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_active_user),
):
    return await presence_service.get_contacts_presence(db, current_user.id)


@router.post("/heartbeat", response_model=PresenceHeartbeatResponse)
async def heartbeat(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_active_user),
    x_client_session: str | None = Header(default=None),
):
    session_id = (x_client_session or "").strip()
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Client-Session header",
        )
    return await presence_service.heartbeat_and_broadcast(db, current_user.id, session_id)
