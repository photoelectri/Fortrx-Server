from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.database import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(String, primary_key=True, index=True)
    recipient_id = Column(Integer, nullable=False, index=True)
    blob_key = Column(String, nullable=False, unique=True)
    file_name = Column(Text, nullable=False)
    mime_type = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    downloaded = Column(Boolean, nullable=False, default=False)
    downloaded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
