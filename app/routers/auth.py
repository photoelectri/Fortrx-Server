from fastapi import APIRouter, Depends, Query, Request, Response, status, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import consume_reauth_header, get_active_user, get_current_token_payload, require_recovery_token
from app.middleware.rate_limit import limiter
from app.models.user import User
from app.schemas import RefreshRequest, ReauthRequest, ReauthResponse, ResetPasswordRequest, TokenResponse, UserCreate, UserResponse
from app.services.account_service import reset_password_with_recovery
from app.services.audit_service import write_audit_log
from app.services.auth_service import (
    create_reauth_token,
    login_user,
    rotate_refresh_token,
    register_user,
    revoke_all_refresh_tokens,
    revoke_current_device_refresh_tokens,
    verify_user_password,
)
from app.repositories.user_repo import get_user_by_username as repo_get_user_by_username, search_users_by_username


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit("5/minute")
def register(
    request: Request,
    payload: UserCreate,
    db: Session = Depends(get_db)
):
    return register_user(
        db,
        payload.username,
        payload.email,
        payload.password
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(
    request: Request,
    payload: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    token_payload = login_user(
        db,
        payload.username,
        payload.password,
        device_name=request.headers.get("X-Device-Name") or request.headers.get("User-Agent") or "Unnamed Device",
        device_id=request.headers.get("X-Device-Id"),
    )
    return token_payload


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")
def refresh(
    request: Request,
    payload: RefreshRequest,
    db: Session = Depends(get_db),
):
    return rotate_refresh_token(
        db,
        payload.refresh_token,
        device_name=request.headers.get("X-Device-Name") or request.headers.get("User-Agent"),
    )


@router.post("/reauth", response_model=ReauthResponse)
@limiter.limit("10/minute")
def reauth(
    request: Request,
    payload: ReauthRequest,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    if not verify_user_password(db, current_user.username, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Credentials")
    reauth_token, expires_at = create_reauth_token(db, current_user)
    return {"reauth_token": reauth_token, "expires_at": expires_at}


@router.post("/logout", status_code=204)
def logout(
    current_user: User = Depends(get_active_user),
    token_payload: dict = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
):
    revoke_current_device_refresh_tokens(db, token_payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=204)
def logout_all(
    current_user: User = Depends(get_active_user),
    _: dict = Depends(consume_reauth_header),
    db: Session = Depends(get_db),
):
    revoke_all_refresh_tokens(db, current_user.id)
    write_audit_log(db, actor=current_user.id, action="logout_all", commit=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reset-password", status_code=204)
def reset_password(
    payload: ResetPasswordRequest,
    recovery_payload: dict = Depends(require_recovery_token),
    db: Session = Depends(get_db),
):
    token = recovery_payload.get("raw_token")
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing recovery token")
    reset_password_with_recovery(db, token, payload.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_active_user)):
    return current_user


@router.get("/users/search")
@limiter.limit("30/minute")
def search_users(
    request: Request,
    q: str = Query(..., min_length=2, max_length=64),
    limit: int = Query(10, ge=1, le=25),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_active_user),
):
    return [
        {"id": user.id, "username": user.username}
        for user in search_users_by_username(db, q, limit=limit)
    ]


@router.get("/users/by-username/{username}")
def get_user_by_username(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_active_user),
):
    user = repo_get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "username": user.username,
    }


@router.get("/users/{user_id}")
def get_user_by_id(
    user_id:int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_active_user)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "username": user.username
    }
