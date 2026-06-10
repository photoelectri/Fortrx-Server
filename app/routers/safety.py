from fastapi import APIRouter,Depends,HTTPException,status
from sqlalchemy.orm import Session

from app.dependencies import get_active_user
from app.database import get_db
from app.services import fingerprint_service

router = APIRouter(
    prefix="/safety",
    tags=['safety']
)

@router.get("/numbers/{other_user_id}")
def get_numbers(
    other_user_id: int,
    current_user=Depends(get_active_user),
    db:Session=Depends(get_db)
):
    try:
        return fingerprint_service.get_safety_number(
            db,current_user.id,other_user_id
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key bundle not found for one or both users"
    )