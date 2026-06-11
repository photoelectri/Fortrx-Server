from pydantic import BaseModel


class BackupCodeRegisterRequest(BaseModel):
    backup_code_hash: str
    salt: str


class BackupCodeVerifyRequest(BaseModel):
    username: str
    backup_code_hash: str
    salt: str


class BackupCodeVerifyResponse(BaseModel):
    recovery_token: str
    expires_at: int


class DeleteAccountResponse(BaseModel):
    deleted: bool = True
