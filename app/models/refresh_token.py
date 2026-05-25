from app.database import Base
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String, ForeignKey("devices.id", ondelete="CASCADE"), nullable=True, index=True)
    token_hash = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    expires_at = Column(BigInteger, nullable=False)
    revoked_at = Column(BigInteger, nullable=True)
