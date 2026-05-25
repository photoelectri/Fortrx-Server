from app.database import Base
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text


class Device(Base):
    __tablename__ = "devices"

    id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    identity_pub = Column(Text, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    last_seen = Column(BigInteger, nullable=False)
    revoked_at = Column(BigInteger, nullable=True)
