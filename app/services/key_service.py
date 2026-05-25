import json

from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import HTTPException,status
from app.models import KeyBundle, User
from app.repositories import get_bundle_by_user_id,create_bundle,update_bundle
from app.schemas import KeyBundleUpload,KeyBundleResponse

def _deserialize_bundle_otpks(bundle) -> list:
    """Read one_time_prekeys without mutating the ORM field to a Python object."""
    raw = bundle.one_time_prekeys
    if isinstance(raw, str):
        parsed = json.loads(raw or "[]")
    else:
        parsed = raw or []
    if isinstance(parsed, dict):
        parsed = list(parsed.values())
    if not isinstance(parsed, list):
        parsed = []
    return parsed

def upload_key_bundle(db:Session,user_id:int,payload:KeyBundleUpload, device_id: str | None = None):
    # SQLite Text column cannot store a Python list — serialize to JSON string
    one_time_prekeys_json = json.dumps(payload.one_time_prekeys)
    bundle = get_bundle_by_user_id(db,user_id, device_id=device_id)
    if bundle:
        identity_changed = bundle.identity_key != payload.identity_key
        bundle = update_bundle(
            db,bundle,
            identity_key=payload.identity_key,
            signing_public=payload.signing_public,
            signed_prekey=payload.signed_prekey,
            signed_prekey_signature=payload.signed_prekey_signature,
            prekey_id=payload.prekey_id,
            one_time_prekeys=one_time_prekeys_json,
            device_id=device_id,
            identity_version=(bundle.identity_version or 1) + (1 if identity_changed else 0),
            bundle_version=(bundle.bundle_version or 1) + 1,
            kyber_prekey_public=payload.kyber_prekey_public,
            kyber_prekey_signature=payload.kyber_prekey_signature)
    else:
        bundle = create_bundle(
            db,
            user_id=user_id,
            identity_key=payload.identity_key,
            signing_public=payload.signing_public,
            signed_prekey=payload.signed_prekey,
            signed_prekey_signature=payload.signed_prekey_signature,
            prekey_id=payload.prekey_id,
            one_time_prekeys=one_time_prekeys_json,
            device_id=device_id,
            identity_version=1,
            bundle_version=1,
            kyber_prekey_public=payload.kyber_prekey_public,
            kyber_prekey_signature=payload.kyber_prekey_signature
            )

    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.identity_public_key = payload.identity_key
        db.commit()
    return bundle

def fetch_key_bundle(db:Session,user_id:int):
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
        bundle = (
            db.query(KeyBundle)
            .filter(KeyBundle.user_id == user_id)
            .order_by(KeyBundle.updated_at.desc(), KeyBundle.id.desc())
            .first()
        )
    else:
        bundle = (
            db.query(KeyBundle)
            .filter(KeyBundle.user_id == user_id)
            .with_for_update()
            .order_by(KeyBundle.updated_at.desc(), KeyBundle.id.desc())
            .first()
        )
    if not bundle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Key Bundle not found")
    otpks = _deserialize_bundle_otpks(bundle)
    if not otpks:
        otp = None
    else:
        otp = otpks.pop(0)
        if isinstance(otp,bytes):
            otp = otp.decode()
        bundle.one_time_prekeys = json.dumps(otpks)
        db.add(bundle)
    db.commit()
    return KeyBundleResponse(
        user_id=bundle.user_id,
        device_id=bundle.device_id,
        identity_key=bundle.identity_key,
        identity_version=bundle.identity_version or 1,
        signing_public=bundle.signing_public,
        signed_prekey=bundle.signed_prekey,
        signed_prekey_signature=bundle.signed_prekey_signature,
        prekey_id=bundle.prekey_id,
        bundle_version=bundle.bundle_version or 1,
        one_time_prekey=otp,
        kyber_prekey_public=bundle.kyber_prekey_public,
        kyber_prekey_signature=bundle.kyber_prekey_signature
    )
