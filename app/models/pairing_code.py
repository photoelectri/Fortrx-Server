from app.database import Base
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, LargeBinary


class PairingCode(Base):
    __tablename__ = "pairing_codes"

    code_hash = Column(LargeBinary, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(BigInteger, nullable=False)
    used_at = Column(BigInteger, nullable=True)
