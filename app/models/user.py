from sqlalchemy import Integer, String, Column, DateTime, Boolean, BigInteger, LargeBinary
from datetime import datetime
from app.database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer,primary_key=True,index=True,autoincrement=True)
    username = Column(String,unique=True,nullable=False,index=True)
    email = Column(String,unique=True,nullable=False)
    hashed_password = Column(String,nullable=False)
    identity_public_key = Column(String,nullable=True)
    created_at = Column(DateTime,default=datetime.utcnow)
    is_active = Column(Boolean,default=True)
    backup_code_hash = Column(String, nullable=True)
    backup_code_salt = Column(LargeBinary, nullable=True)
    backup_code_server_salt = Column(LargeBinary, nullable=True)
    backup_code_failures = Column(Integer, nullable=False, default=0)
    backup_code_locked_until = Column(BigInteger, nullable=True)
