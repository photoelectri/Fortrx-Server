from app.database import Base
from sqlalchemy import BigInteger, Column, Integer, JSON, Text


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    actor = Column(Integer, nullable=True, index=True)
    action = Column(Text, nullable=False)
    meta = Column(JSON, nullable=True)
    ts = Column(BigInteger, nullable=False)
