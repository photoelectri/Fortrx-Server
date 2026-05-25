from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.crypto import decode_access_token
from app.database import get_db
from app.models import User
from app.services.auth_service import ensure_active_device, touch_device_last_seen_redis, verify_stored_action_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_token_payload(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_access_token(token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    return payload


async def get_current_user(
    payload: dict = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
):
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    ensure_active_device(db, user.id, payload.get("device_id"))
    # Optimized: Use Redis for last_seen tracking to avoid DB write on every request
    await touch_device_last_seen_redis(user.id, payload.get("device_id"))
    return user


def get_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account Disabled"
        )
    return current_user


def require_recovery_token(
    authorization: str = Header(..., alias="Authorization"),
    db: Session = Depends(get_db),
) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    payload = verify_stored_action_token(db, token, expected_type="recovery", mark_used=False)
    payload["raw_token"] = token
    return payload


def consume_reauth_header(
    current_user: User = Depends(get_active_user),
    x_reauth: str = Header(..., alias="X-Reauth"),
    db: Session = Depends(get_db),
) -> dict:
    return verify_stored_action_token(db, x_reauth, expected_type="reauth", user_id=current_user.id, mark_used=True)
