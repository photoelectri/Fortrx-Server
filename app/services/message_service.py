import base64
import binascii
from sqlalchemy.orm import Session
from fastapi import HTTPException,status
from app.config import settings
from app.repositories import contact_repo, message_repo,user_repo
from app.schemas import MessageSend
from app.services import generate_blob_key,upload_blob,download_blob,delete_blob
from app.services.connection_manager import manager
from datetime import datetime,timedelta,timezone

async def send_message(db:Session,sender_id:int,payload:MessageSend):
    recipient = user_repo.get_user_by_id(db,payload.recipient_id)
    if not recipient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Recipient not found")
    if payload.recipient_id == sender_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Self-send should stay local to the client")
    try:
        raw = base64.b64decode(payload.sealed_blob, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sealed blob") from exc
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty sealed blob")
    if len(raw) > settings.MAX_SEALED_BLOB_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Message too large")
    blob_key = generate_blob_key(payload.recipient_id)
    upload_blob(blob_key,raw)

    if payload.ttl_seconds is not None:
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0) + timedelta(seconds=payload.ttl_seconds)
    else:
        expires_at = None

    try:
        message = message_repo.save_message(
            db=db,
            recipient_id=payload.recipient_id,
            message_number=payload.message_number,
            sealed_blob=blob_key,
            expires_at = expires_at
        )
    except Exception:
        try:
            delete_blob(blob_key)
        except Exception:
            pass
        raise
    contact_repo.ensure_bidirectional_contact(db, sender_id, payload.recipient_id)
    
    await manager.send_to_user(
            payload.recipient_id,{
                "type":"message_available",
                "message_id":message.id,
                "message_number":payload.message_number,
                "expires_at":expires_at.isoformat() if expires_at else None
            }
        )
    return message

def fetch_inbox(db:Session,user_id:int):
    messages = message_repo.get_message_for_user(db,user_id)
    rows = []
    for msg in messages:
        try:
            raw = download_blob(msg.sealed_blob)
        except Exception:
            message_repo.delete_message(db, msg.id)
            continue
        msg.sealed_blob = base64.b64encode(raw).decode()
        rows.append(msg)
    return rows
        

def confirm_delivery(db:Session,message_id:int,user_id:int):
    message = message_repo.get_message_by_id(db, message_id)
    if not message:
        return {"message":"already_confirmed"}
    
    if message.recipient_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Not allowed")
    
    # delete the blob associated with the found message instance
    try:
        delete_blob(message.sealed_blob)
    except Exception:
        # best-effort: if blob deletion fails, still proceed to remove DB record
        pass

    message_repo.delete_message(db,message_id)
    return {"message":"deleted"}

def purge_expired_messages(db):
    expired = message_repo.get_expired_messages(db)
    deleted = 0
    for msg in expired:
        try:
            delete_blob(msg.sealed_blob)
        except Exception:
            pass
        message_repo.delete_message(db,msg.id)
        deleted += 1
    return deleted
