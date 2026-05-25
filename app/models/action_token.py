from app.database import Base
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String


class ActionToken(Base):
    __tablename__ = "action_tokens"

    jti = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    token_type = Column(String, nullable=False, index=True)
    action = Column(String, nullable=True)
    device_id = Column(String, nullable=True)
    expires_at = Column(BigInteger, nullable=False)
    used_at = Column(BigInteger, nullable=True)
