from sqlalchemy import Column,Integer,DateTime,Text
from datetime import datetime
from app.database import Base

class KeyBundle(Base):
    __tablename__ = "key_bundles"
    id = Column(Integer,primary_key=True,index=True)
    user_id = Column(Integer,nullable=False,index=True)
    identity_key = Column(Text)
    signing_public = Column(Text)
    signed_prekey = Column(Text)
    signed_prekey_signature = Column(Text)
    prekey_id = Column(Integer)
    one_time_prekeys = Column(Text)
    device_id = Column(Text, nullable=True, index=True)
    identity_version = Column(Integer, nullable=False, default=1)
    bundle_version = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime,default=datetime.utcnow)
    kyber_prekey_public = Column(Text,nullable=True)
    kyber_prekey_signature = Column(Text,nullable=True)
