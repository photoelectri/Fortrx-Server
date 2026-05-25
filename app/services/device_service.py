import hashlib
from hmac import compare_digest
import secrets

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Device, KeyBundle, PairingCode, RefreshToken, User
from app.services.audit_service import write_audit_log
from app.services.auth_service import (
    create_or_update_device,
    issue_login_tokens,
    now_ms,
    persist_action_token,
    verify_stored_action_token,
)


PAIRING_TTL_MS = 5 * 60 * 1000


def _exp_to_ms(exp_value) -> int:
    if hasattr(exp_value, "timestamp"):
        return int(exp_value.timestamp() * 1000)
    if isinstance(exp_value, (int, float)):
        return int(exp_value * 1000)
    return now_ms() + PAIRING_TTL_MS


def list_devices(db: Session, user: User, current_device_id: str | None) -> list[dict]:
    devices = (
        db.query(Device)
        .filter(Device.user_id == user.id, Device.revoked_at.is_(None))
        .order_by(Device.created_at.asc())
        .all()
    )
    return [
        {
            "id": device.id,
            "name": device.name,
            "created_at": device.created_at,
            "last_seen": device.last_seen,
            "current": device.id == current_device_id,
        }
        for device in devices
    ]


def revoke_device(db: Session, user: User, device_id: str) -> None:
    device = db.query(Device).filter(Device.id == device_id, Device.user_id == user.id).first()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    now = now_ms()
    (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.device_id == device_id, RefreshToken.revoked_at.is_(None))
        .update({"revoked_at": now}, synchronize_session=False)
    )
    db.query(KeyBundle).filter(KeyBundle.user_id == user.id, KeyBundle.device_id == device_id).delete(synchronize_session=False)
    device.revoked_at = now
    write_audit_log(db, actor=user.id, action="device_revoke", meta={"device_id": device_id})
    db.commit()


def start_device_link(db: Session, user: User) -> dict:
    raw_code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = hashlib.sha256(raw_code.encode("utf-8")).digest()
    pairing_token, expires_at = create_device_link_token(db, user)
    row = PairingCode(
        code_hash=code_hash,
        user_id=user.id,
        expires_at=expires_at,
        used_at=None,
    )
    db.add(row)
    db.commit()
    return {
        "pairing_token": pairing_token,
        "numeric_code": f"{raw_code[:3]} {raw_code[3:]}",
        "pairing_uri": f"{settings.PUBLIC_BASE_URL}/link-device",
        "expires_at": row.expires_at,
    }


def create_device_link_token(db: Session, user: User) -> tuple[str, int]:
    return create_device_link_action_token(db, user)


def create_device_link_action_token(db: Session, user: User) -> tuple[str, int]:
    from app.crypto import create_action_token
    token = create_action_token(user.id, token_type="device_link", expires_minutes=5, action="pair_device")
    payload = persist_action_token(db, token, user.id, token_type="device_link", action="pair_device")
    return token, _exp_to_ms(payload.get("exp"))


def complete_device_link(db: Session, pairing_token: str, code: str, identity_pub: str, device_name: str) -> dict:
    pairing_payload = verify_stored_action_token(db, pairing_token, expected_type="device_link", mark_used=False)
    user_id = int(pairing_payload["sub"])
    normalized = "".join(ch for ch in code if ch.isdigit())
    if len(normalized) != 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pairing code")
    submitted_hash = hashlib.sha256(normalized.encode("utf-8")).digest()
    now = now_ms()
    candidates = (
        db.query(PairingCode)
        .filter(
            PairingCode.user_id == user_id,
            PairingCode.used_at.is_(None),
            PairingCode.expires_at > now,
        )
        .all()
    )
    matched = None
    for candidate in candidates:
        if compare_digest(candidate.code_hash, submitted_hash):
            matched = candidate
            break
    if matched is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid pairing code")

    user = db.query(User).filter(User.id == matched.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    device = create_or_update_device(db, user, device_name=device_name, identity_pub=identity_pub)
    matched.used_at = now
    verify_stored_action_token(db, pairing_token, expected_type="device_link", user_id=user.id, mark_used=True)
    db.commit()
    tokens = issue_login_tokens(db, user, device_name=device.name, device_id=device.id, identity_pub=identity_pub)
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "device_id": tokens["device_id"],
        "access_expires_at": tokens.get("access_expires_at"),
        "refresh_expires_at": tokens.get("refresh_expires_at"),
    }
