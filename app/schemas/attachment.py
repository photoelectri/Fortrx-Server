from datetime import datetime

from pydantic import BaseModel, Field


class AttachmentUploadResponse(BaseModel):
    attachment_id: str
    created_at: datetime
    expires_at: datetime | None = None


class AttachmentAckResponse(BaseModel):
    deleted: bool = True
    attachment_id: str
    downloaded_at: datetime


class AttachmentDownloadHeaders(BaseModel):
    attachment_id: str
    file_name: str
    mime_type: str
    size_bytes: int = Field(gt=0)
    sha256: str
