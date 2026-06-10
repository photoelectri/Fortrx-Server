from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from app.schemas import KeyBundleUpload,KeyBundleResponse
from app.database import get_db
from app.services import upload_key_bundle,fetch_key_bundle
from app.dependencies import get_active_user, get_current_token_payload, require_recovery_token
from app.models import User

router = APIRouter(
    prefix="/keys",
    tags=['keys']
)

@router.post('/upload',status_code=201)
def upload_keys(
    payload: KeyBundleUpload,
    db:Session = Depends(get_db),
    current_user: User = Depends(get_active_user),
    token_payload: dict = Depends(get_current_token_payload),
):
    upload_key_bundle(db,current_user.id,payload, device_id=token_payload.get("device_id"))
    return {"message":"Key bundle uploaded successfully"}


@router.post('/bundle',status_code=201)
def upload_recovery_keys(
    payload: KeyBundleUpload,
    recovery_payload: dict = Depends(require_recovery_token),
    db: Session = Depends(get_db),
):
    user_id = int(recovery_payload["sub"])
    upload_key_bundle(db, user_id, payload, device_id=recovery_payload.get("device_id"))
    return {"message":"Key bundle uploaded successfully"}

@router.get("/{user_id}",response_model=KeyBundleResponse)
def get_keys(
    user_id:int,
    db:Session= Depends(get_db),
    current_user:User = Depends(get_active_user)
):
    return fetch_key_bundle(db,user_id)
