from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

from app.config import settings

class MessageSend(BaseModel):
    recipient_id: int = Field(gt=0)
    sealed_blob: str = Field(min_length=1, max_length=settings.MAX_SEALED_BLOB_BYTES * 2)
    message_number: int = Field(ge=0)
    ttl_seconds: int | None = Field(default=None, ge=1, le=settings.MAX_MESSAGE_TTL_SECONDS)
    
class MessageResponse(BaseModel):
    id:int
    recipient_id:int
    message_number:int
    sealed_blob:str
    created_at:datetime
    expires_at: Optional[datetime]
    
    class Config():
        from_attributes=True
