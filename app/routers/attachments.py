from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_active_user
from app.models import User
from app.schemas import AttachmentAckResponse, AttachmentUploadResponse
from app.services.attachment_service import ack_attachment_download, stream_attachment_download, upload_attachment


router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("/upload", response_model=AttachmentUploadResponse, status_code=201)
async def upload_streamed_attachment(
    request: Request,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
    x_recipient_id: int = Header(..., alias="X-Recipient-Id"),
    x_file_name: str = Header(..., alias="X-File-Name"),
    x_mime_type: str = Header(..., alias="X-Mime-Type"),
    x_size_bytes: int = Header(..., alias="X-Size-Bytes"),
    x_sha256: str = Header(..., alias="X-Sha256"),
    x_ttl_seconds: int | None = Header(default=None, alias="X-Ttl-Seconds"),
):
    attachment = await upload_attachment(
        db=db,
        recipient_id=x_recipient_id,
        request=request,
        file_name=x_file_name,
        mime_type=x_mime_type,
        size_bytes=x_size_bytes,
        sha256=x_sha256,
        ttl_seconds=x_ttl_seconds,
    )
    return {
        "attachment_id": attachment.id,
        "created_at": attachment.created_at,
        "expires_at": attachment.expires_at,
    }


@router.get("/{attachment_id}/download")
def download_attachment(
    attachment_id: str,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    return stream_attachment_download(db, attachment_id, current_user.id)


@router.post("/{attachment_id}/ack", response_model=AttachmentAckResponse)
def ack_attachment(
    attachment_id: str,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    attachment = ack_attachment_download(db, attachment_id, current_user.id)
    return {
        "deleted": True,
        "attachment_id": attachment_id,
        "downloaded_at": attachment.downloaded_at,
    }


@router.delete("/{attachment_id}", status_code=204)
def delete_attachment(
    attachment_id: str,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    ack_attachment_download(db, attachment_id, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
