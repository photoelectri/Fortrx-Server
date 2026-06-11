from pydantic import BaseModel

from app.schemas.user import TokenResponse


class ReauthRequest(BaseModel):
    password: str


class ReauthResponse(BaseModel):
    reauth_token: str
    expires_at: int


class ResetPasswordRequest(BaseModel):
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(TokenResponse):
    pass
