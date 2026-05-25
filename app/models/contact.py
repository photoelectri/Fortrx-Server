from sqlalchemy import Column, Integer, UniqueConstraint

from app.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    contact_user_id = Column(Integer, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("user_id", "contact_user_id", name="uq_user_contact"),
    )
