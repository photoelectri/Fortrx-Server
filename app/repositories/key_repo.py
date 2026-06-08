from sqlalchemy.orm import Session
import json
from app.models import KeyBundle


def get_bundle_by_user_id(db:Session,user_id:int, device_id: str | None = None):
    query = db.query(KeyBundle).filter(KeyBundle.user_id == user_id)
    if device_id is not None:
        query = query.filter(KeyBundle.device_id == device_id)
    return query.order_by(KeyBundle.updated_at.desc(), KeyBundle.id.desc()).first()

def create_bundle(
    db:Session,
    user_id:int,
    identity_key:str,
    signing_public:str,
    signed_prekey:str,
    signed_prekey_signature:str,
    prekey_id:int,
    one_time_prekeys:list[str],
    device_id: str | None = None,
    identity_version: int = 1,
    bundle_version: int = 1,
    kyber_prekey_public: str | None = None,
    kyber_prekey_signature: str | None = None
    ):
    bundle = KeyBundle(
        user_id=user_id,
        identity_key=identity_key,
        signing_public=signing_public,
        signed_prekey=signed_prekey,
        signed_prekey_signature=signed_prekey_signature,
        prekey_id=prekey_id,
        one_time_prekeys=one_time_prekeys,
        device_id=device_id,
        identity_version=identity_version,
        bundle_version=bundle_version,
        kyber_prekey_public=kyber_prekey_public,
        kyber_prekey_signature=kyber_prekey_signature
    )
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    return bundle

def update_bundle(db:Session,bundle:KeyBundle,**fields):
    for key,value in fields.items():
        if key == "one_time_prekeys" and isinstance(value,list):
            value = json.dumps(value)
        setattr(bundle,key,value)
    db.commit()
    db.refresh(bundle)
    return bundle

def pop_one_time_prekey(db:Session,bundle:KeyBundle):
    keys = json.loads(bundle.one_time_prekeys or "[]")
    if not keys:
        return None
    popped = keys.pop()
    bundle.one_time_prekeys = json.dumps(keys)
    db.commit()
    return popped
