from sqlalchemy.orm import Session

from app.models.contact import Contact


def ensure_contact_pair(db: Session, user_id: int, contact_user_id: int):
    if user_id == contact_user_id:
        return None

    existing = (
        db.query(Contact)
        .filter(
            Contact.user_id == user_id,
            Contact.contact_user_id == contact_user_id,
        )
        .first()
    )
    if existing:
        return existing

    row = Contact(user_id=user_id, contact_user_id=contact_user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def ensure_bidirectional_contact(db: Session, user_a: int, user_b: int):
    ensure_contact_pair(db, user_a, user_b)
    ensure_contact_pair(db, user_b, user_a)


def get_contact_ids(db: Session, user_id: int) -> list[int]:
    rows = db.query(Contact.contact_user_id).filter(Contact.user_id == user_id).all()
    return [row[0] for row in rows]
