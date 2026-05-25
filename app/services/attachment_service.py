import hashlib
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.models import Attachment
from app.services.storage_service import delete_blob, download_blob_stream, generate_blob_key, upload_blob_file


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


async def upload_attachment(
    db: Session,
    recipient_id: int,
    request: Request,
    file_name: str,
    mime_type: str,
    size_bytes: int,
    sha256: str,
    ttl_seconds: int | None = None,
) -> Attachment:
    if recipient_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recipient id must be positive")
    if size_bytes <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment size must be positive")

    attachment_id = str(uuid.uuid4())
    blob_key = generate_blob_key(recipient_id, prefix="attachments")
    digest = hashlib.sha256()
    written = 0

    fd, temp_path = tempfile.mkstemp(prefix="fortrx-attachment-", suffix=".blob")
    os.close(fd)
    try:
        with open(temp_path, "wb") as tmp:
            async for chunk in request.stream():
                if not chunk:
                    continue
                written += len(chunk)
                if written > size_bytes:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Attachment exceeded declared size")
                digest.update(chunk)
                tmp.write(chunk)

        if written != size_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment size mismatch")
        if digest.hexdigest() != sha256.lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment checksum mismatch")

        upload_blob_file(blob_key, temp_path, content_type="application/octet-stream")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    expires_at = _utcnow_naive() + timedelta(seconds=ttl_seconds) if ttl_seconds is not None else None
    attachment = Attachment(
        id=attachment_id,
        recipient_id=recipient_id,
        blob_key=blob_key,
        file_name=file_name,
        mime_type=mime_type,
        size_bytes=size_bytes,
        sha256=sha256.lower(),
        expires_at=expires_at,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


def stream_attachment_download(db: Session, attachment_id: str, user_id: int) -> StreamingResponse:
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    if attachment.recipient_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    if attachment.expires_at is not None and attachment.expires_at <= _utcnow_naive():
        try:
            delete_blob(attachment.blob_key)
        except Exception:
            pass
        db.delete(attachment)
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment expired")

    headers = {
        "X-Attachment-Id": attachment.id,
        "X-Attachment-File-Name": attachment.file_name,
        "X-Attachment-Mime-Type": attachment.mime_type,
        "X-Attachment-Size-Bytes": str(attachment.size_bytes),
        "X-Attachment-Sha256": attachment.sha256,
    }
    return StreamingResponse(
        download_blob_stream(attachment.blob_key),
        media_type="application/octet-stream",
        headers=headers,
    )


def ack_attachment_download(db: Session, attachment_id: str, user_id: int) -> Attachment:
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    if attachment.recipient_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    attachment.downloaded = True
    attachment.downloaded_at = _utcnow_naive()
    try:
        delete_blob(attachment.blob_key)
    finally:
        db.delete(attachment)
        db.commit()
    return attachment


def purge_expired_attachments(db: Session) -> int:
    now = _utcnow_naive()
    expired = db.query(Attachment).filter(Attachment.expires_at.is_not(None), Attachment.expires_at < now).all()
    deleted = 0
    for attachment in expired:
        try:
            delete_blob(attachment.blob_key)
        except Exception:
            pass
        db.delete(attachment)
        deleted += 1
    if deleted > 0:
        db.commit()
    return deleted
