from pydantic import BaseModel
from datetime import datetime

class UserCreate(BaseModel):
    username:str
    email:str
    password:str
    
class UserLogin(BaseModel):
    username:str
    password:str

class UserResponse(BaseModel):
    id:int
    username:str
    email:str
    is_active:bool
    created_at:datetime
    
    class Config():
        from_attribute=True

class TokenResponse(BaseModel):
    access_token:str
    token_type:str = "bearer"
    refresh_token:str | None = None
    device_id:str | None = None
    access_expires_at:int | None = None
    refresh_expires_at:int | None = None
