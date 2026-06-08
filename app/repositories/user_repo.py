from sqlalchemy.orm import Session
from sqlalchemy import case, func
from app.models.user import User

def get_user_by_id(db:Session,id:int):
    return db.query(User).filter(User.id == id).first()

def get_user_by_username(db:Session,username:str):
    normalized = username.strip()
    return db.query(User).filter(func.lower(User.username) == normalized.lower()).first()

def get_user_by_email(db:Session,email:str):
    return db.query(User).filter(User.email==email).first()

def create_user(db:Session,username:str,email:str,hashed_password:str):
    user = User(
        username = username,
        email = email,
        hashed_password=hashed_password
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def search_users_by_username(db: Session, query: str, limit: int = 10):
    needle = query.strip().lower()
    prefix = f"{needle}%"
    contains = f"%{needle}%"
    return (
        db.query(User)
        .filter(func.lower(User.username).like(contains))
        .order_by(
            case((func.lower(User.username).like(prefix), 0), else_=1),
            func.length(User.username),
            User.username.asc(),
        )
        .limit(limit)
        .all()
    )
    
