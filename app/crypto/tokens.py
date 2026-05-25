from datetime import datetime, timedelta, timezone
import secrets

from jose import jwt
from jose.exceptions import JWTError

from app.config import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(data:dict, expires_minutes:int | None = None)->str:
    to_encode = data.copy()
    expire = _utcnow().replace(microsecond=0) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode["exp"] = expire
    to_encode.setdefault("type", "access")
    to_encode.setdefault("jti", secrets.token_urlsafe(12))
    return jwt.encode(to_encode,settings.SECRET_KEY,algorithm=settings.ALGORITHM)


def create_refresh_token(user_id:int, device_id:str, expires_days:int = 30) -> str:
    return create_access_token(
        {
            "sub": str(user_id),
            "device_id": device_id,
            "type": "refresh",
        },
        expires_minutes=expires_days * 24 * 60,
    )


def create_action_token(
    user_id:int,
    token_type:str,
    expires_minutes:int,
    action:str | None = None,
    device_id:str | None = None,
) -> str:
    payload = {
        "sub": str(user_id),
        "type": token_type,
    }
    if action is not None:
        payload["action"] = action
    if device_id is not None:
        payload["device_id"] = device_id
    return create_access_token(payload, expires_minutes=expires_minutes)


def decode_access_token(token:str)->dict|None:
    try:
        payload = jwt.decode(token,settings.SECRET_KEY,algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None
    

def create_token_for_user(user_id:int,username:str, device_id:str | None = None)->str:
    return create_access_token({
        "sub":str(user_id),
        "username":username,
        "device_id": device_id,
        "type": "access",
        })
    
