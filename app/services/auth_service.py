import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from hmac import compare_digest

from fastapi import HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.config import settings
from app.crypto import (
    create_action_token,
    create_refresh_token,
    create_token_for_user,
    decode_access_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.models import ActionToken, Device, RefreshToken, User
from app.repositories.user_repo import create_user, get_user_by_email, get_user_by_username
from app.services.pubsub import get_redis

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_ms() -> int:
    return int(_now_utc().timestamp() * 1000)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _exp_to_ms(exp_value) -> int:
    if hasattr(exp_value, "timestamp"):
        return int(exp_value.timestamp() * 1000)
    if isinstance(exp_value, (int, float)):
        return int(exp_value * 1000)
    return 0


def register_user(db: Session, username: str, email: str, password: str):
    if get_user_by_username(db, username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    if get_user_by_email(db, email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )
    hashed_password = hash_password(password)
    return create_user(
        db,
        username=username,
        email=email,
        hashed_password=hashed_password
    )


def verify_user_password(db: Session, username: str, password: str) -> User:
    user_indb = get_user_by_username(db, username)
    if not user_indb or not verify_password(password, user_indb.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Credentials"
        )
    if password_needs_rehash(user_indb.hashed_password):
        user_indb.hashed_password = hash_password(password)
        db.commit()
    return user_indb


def create_or_update_device(
    db: Session,
    user: User,
    device_name: str,
    device_id: str | None = None,
    identity_pub: str | None = None,
) -> Device:
    device = None
    if device_id:
        device = (
            db.query(Device)
            .filter(Device.id == device_id, Device.user_id == user.id)
            .first()
        )
    if device is None:
        device = Device(
            id=device_id or f"dev_{secrets.token_urlsafe(9)}",
            user_id=user.id,
            name=device_name or "Unnamed Device",
            identity_pub=identity_pub,
            created_at=now_ms(),
            last_seen=now_ms(),
            revoked_at=None,
        )
        db.add(device)
    else:
        device.name = device_name or device.name
        if identity_pub:
            device.identity_pub = identity_pub
        device.last_seen = now_ms()
        if device.revoked_at is not None:
            device.revoked_at = None
    db.flush()
    return device


def issue_login_tokens(
    db: Session,
    user: User,
    device_name: str,
    device_id: str | None = None,
    identity_pub: str | None = None,
) -> dict:
    device = create_or_update_device(db, user, device_name, device_id=device_id, identity_pub=identity_pub)
    access_token = create_token_for_user(user.id, user.username, device.id)
    refresh_token = create_refresh_token(user.id, device.id, expires_days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    access_payload = decode_access_token(access_token) or {}
    refresh_payload = decode_access_token(refresh_token) or {}
    refresh_row = RefreshToken(
        user_id=user.id,
        device_id=device.id,
        token_hash=token_hash(refresh_token),
        created_at=now_ms(),
        expires_at=_exp_to_ms(refresh_payload.get("exp")),
        revoked_at=None,
    )
    db.add(refresh_row)
    db.commit()
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
        "device_id": device.id,
        "access_expires_at": _exp_to_ms(access_payload.get("exp")),
        "refresh_expires_at": _exp_to_ms(refresh_payload.get("exp")),
    }


def login_user(
    db: Session,
    username: str,
    password: str,
    device_name: str,
    device_id: str | None = None,
):
    user = verify_user_password(db, username, password)
    return issue_login_tokens(db, user, device_name=device_name, device_id=device_id)


def rotate_refresh_token(
    db: Session,
    refresh_token: str,
    device_name: str | None = None,
    identity_pub: str | None = None,
) -> dict:
    payload = decode_access_token(refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = int(payload.get("sub", 0))
    device_id = payload.get("device_id")
    if user_id <= 0 or not device_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    row = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user_id,
            RefreshToken.device_id == device_id,
            RefreshToken.revoked_at.is_(None),
        )
        .all()
    )
    matched = next((candidate for candidate in row if compare_digest(candidate.token_hash, token_hash(refresh_token))), None)
    if matched is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token not recognized")
    if matched.expires_at <= now_ms():
        matched.revoked_at = now_ms()
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account Disabled")

    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.user_id == user_id)
        .first()
    )
    if device is None or device.revoked_at is not None:
        matched.revoked_at = now_ms()
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Device not active")

    matched.revoked_at = now_ms()
    db.flush()
    refreshed = issue_login_tokens(
        db,
        user,
        device_name=device_name or device.name,
        device_id=device.id,
        identity_pub=identity_pub or device.identity_pub,
    )
    return refreshed


def persist_action_token(
    db: Session,
    token: str,
    user_id: int,
    token_type: str,
    action: str | None = None,
    device_id: str | None = None,
) -> dict:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=500, detail="Could not decode token payload")
    expires_at = _exp_to_ms(payload.get("exp"))
    row = ActionToken(
        jti=payload["jti"],
        user_id=user_id,
        token_type=token_type,
        action=action,
        device_id=device_id,
        expires_at=expires_at,
        used_at=None,
    )
    db.merge(row)
    db.commit()
    return payload


def create_reauth_token(db: Session, user: User) -> tuple[str, int]:
    token = create_action_token(user.id, token_type="reauth", expires_minutes=5, action="sensitive")
    payload = persist_action_token(db, token, user.id, token_type="reauth", action="sensitive")
    expires_at = _exp_to_ms(payload.get("exp")) or now_ms() + 300_000
    return token, expires_at


def create_recovery_token(db: Session, user: User) -> tuple[str, int]:
    token = create_action_token(user.id, token_type="recovery", expires_minutes=10, action="recovery")
    payload = persist_action_token(db, token, user.id, token_type="recovery", action="recovery")
    expires_at = _exp_to_ms(payload.get("exp")) or now_ms() + 600_000
    return token, expires_at


def verify_stored_action_token(
    db: Session,
    token: str,
    expected_type: str,
    user_id: int | None = None,
    mark_used: bool = False,
) -> dict:
    payload = decode_access_token(token)
    if payload is None or payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    token_user_id = int(payload.get("sub", 0))
    if user_id is not None and token_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token does not belong to user")
    jti = payload.get("jti")
    row = db.query(ActionToken).filter(ActionToken.jti == jti).first()
    if row is None or row.token_type != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token not recognized")
    if row.used_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token already used")
    if row.expires_at and row.expires_at < now_ms():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    if mark_used:
        row.used_at = now_ms()
        db.commit()
    return payload


def revoke_current_device_refresh_tokens(db: Session, token_payload: dict) -> None:
    device_id = token_payload.get("device_id")
    user_id = int(token_payload.get("sub", 0))
    if not device_id or not user_id:
        return
    (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user_id,
            RefreshToken.device_id == device_id,
            RefreshToken.revoked_at.is_(None),
        )
        .update({"revoked_at": now_ms()}, synchronize_session=False)
    )
    db.commit()


def revoke_all_refresh_tokens(db: Session, user_id: int) -> None:
    (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .update({"revoked_at": now_ms()}, synchronize_session=False)
    )
    db.commit()


def touch_device_last_seen(db: Session, user_id: int, device_id: str | None) -> None:
    if not device_id:
        return
    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.user_id == user_id)
        .first()
    )
    if device is None or device.revoked_at is not None:
        return
    device.last_seen = now_ms()
    db.commit()


def ensure_active_device(db: Session, user_id: int, device_id: str | None) -> Device | None:
    if not device_id:
        return None
    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.user_id == user_id)
        .first()
    )
    if device is None or device.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device not active",
        )
    return device


async def touch_device_last_seen_redis(user_id: int, device_id: str | None) -> None:
    if not device_id:
        return
    redis = get_redis()
    try:
        # Use a key to track last seen in Redis with a 24h TTL
        # This avoids a DB write on every request.
        key = f"device:last_seen:{user_id}:{device_id}"
        await redis.set(key, str(now_ms()), ex=86400)
    except (OSError, RedisError):
        # Presence bookkeeping must not break authenticated requests.
        return
    finally:
        await redis.aclose()
