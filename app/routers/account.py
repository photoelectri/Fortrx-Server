from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import consume_reauth_header, get_active_user
from app.middleware.rate_limit import limiter
from app.models import User
from app.schemas import (
    BackupCodeRegisterRequest,
    BackupCodeVerifyRequest,
    BackupCodeVerifyResponse,
)
from app.services.account_service import delete_account, register_backup_code, verify_backup_code


router = APIRouter(prefix="/account", tags=["account"])


@router.post("/backup-code/register", status_code=204)
def backup_code_register(
    payload: BackupCodeRegisterRequest,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    register_backup_code(db, current_user, payload.backup_code_hash, payload.salt)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/backup-code/verify", response_model=BackupCodeVerifyResponse)
@limiter.limit("5/hour")
def backup_code_verify(
    request: Request,
    payload: BackupCodeVerifyRequest,
    db: Session = Depends(get_db),
):
    recovery_token, expires_at = verify_backup_code(db, payload.username, payload.backup_code_hash, payload.salt)
    return {"recovery_token": recovery_token, "expires_at": expires_at}


@router.delete("", status_code=204)
@limiter.limit("3/hour")
@limiter.limit("1/day")
def delete_current_account(
    request: Request,
    current_user: User = Depends(get_active_user),
    _: dict = Depends(consume_reauth_header),
    db: Session = Depends(get_db),
):
    delete_account(db, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
