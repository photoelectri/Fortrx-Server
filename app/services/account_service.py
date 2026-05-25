import base64
import binascii
from hmac import compare_digest
import secrets

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.crypto import hash_password
from app.models import ActionToken, Attachment, Contact, Device, KeyBundle, Message, PairingCode, RefreshToken, User
from app.repositories.user_repo import get_user_by_username
from app.services.audit_service import write_audit_log
from app.services.auth_service import create_recovery_token, now_ms, verify_stored_action_token
from app.services.storage_service import delete_blob


BACKUP_LOCK_MS = 60 * 60 * 1000


def _decode_b64(value: str, field_name: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {field_name}") from exc


def _argon2_hasher(server_salt: bytes) -> Argon2id:
    return Argon2id(
        salt=server_salt,
        length=32,
        iterations=3,
        lanes=1,
        memory_cost=64 * 1024,
        secret=secrets.token_bytes(0) if False else None,
    )


def _backup_pepper() -> bytes:
    # Reuse the server secret as the pepper so the client prehash never stands on its own.
    from app.config import settings
    return settings.SECRET_KEY.encode("utf-8")


def _derive_backup_hash(client_prehash: bytes, server_salt: bytes) -> str:
    hasher = Argon2id(
        salt=server_salt,
        length=32,
        iterations=3,
        lanes=1,
        memory_cost=64 * 1024,
        secret=_backup_pepper(),
    )
    return hasher.derive_phc_encoded(client_prehash)


def register_backup_code(db: Session, user: User, backup_code_hash_b64: str, salt_b64: str) -> None:
    client_prehash = _decode_b64(backup_code_hash_b64, "backup_code_hash")
    salt = _decode_b64(salt_b64, "salt")
    server_salt = secrets.token_bytes(16)
    user.backup_code_hash = _derive_backup_hash(client_prehash, server_salt)
    user.backup_code_salt = salt
    user.backup_code_server_salt = server_salt
    user.backup_code_failures = 0
    user.backup_code_locked_until = None
    db.commit()


def _fail_backup_verification(db: Session, user: User | None) -> None:
    if user is None:
        return
    user.backup_code_failures = (user.backup_code_failures or 0) + 1
    if user.backup_code_failures >= 10:
        user.backup_code_locked_until = now_ms() + BACKUP_LOCK_MS
    db.commit()


def verify_backup_code(db: Session, username: str, backup_code_hash_b64: str, salt_b64: str) -> tuple[str, int]:
    user = get_user_by_username(db, username)
    if user is None or not user.backup_code_hash or not user.backup_code_salt:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid recovery credentials")
    if user.backup_code_locked_until and user.backup_code_locked_until > now_ms():
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Backup code verification temporarily locked")

    client_prehash = _decode_b64(backup_code_hash_b64, "backup_code_hash")
    supplied_salt = _decode_b64(salt_b64, "salt")
    if not compare_digest(supplied_salt, user.backup_code_salt):
        _fail_backup_verification(db, user)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid recovery credentials")

    try:
        Argon2id.verify_phc_encoded(client_prehash, user.backup_code_hash, secret=_backup_pepper())
    except InvalidKey as exc:
        _fail_backup_verification(db, user)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid recovery credentials") from exc

    user.backup_code_failures = 0
    user.backup_code_locked_until = None
    db.commit()
    write_audit_log(db, actor=user.id, action="backup_code_verify_success")
    token, expires_at = create_recovery_token(db, user)
    return token, expires_at


def reset_password_with_recovery(db: Session, recovery_token: str, password: str) -> None:
    payload = verify_stored_action_token(db, recovery_token, expected_type="recovery", mark_used=False)
    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.hashed_password = hash_password(password)
    db.commit()


def delete_account(db: Session, user: User) -> None:
    user_id = user.id
    attachments = db.query(Attachment).filter(Attachment.recipient_id == user_id).all()
    for attachment in attachments:
        try:
            delete_blob(attachment.blob_key)
        except Exception:
            pass
        db.delete(attachment)
    db.query(Message).filter(Message.recipient_id == user_id).delete(synchronize_session=False)
    db.query(KeyBundle).filter(KeyBundle.user_id == user_id).delete(synchronize_session=False)
    db.query(Contact).filter(
        or_(Contact.user_id == user_id, Contact.contact_user_id == user_id)
    ).delete(synchronize_session=False)
    db.query(PairingCode).filter(PairingCode.user_id == user_id).delete(synchronize_session=False)
    db.query(ActionToken).filter(ActionToken.user_id == user_id).delete(synchronize_session=False)
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete(synchronize_session=False)
    db.query(Device).filter(Device.user_id == user_id).delete(synchronize_session=False)
    write_audit_log(db, actor=user_id, action="delete_account")
    db.delete(user)
    db.commit()
