from pydantic import BaseModel


class DeviceResponse(BaseModel):
    id: str
    name: str
    created_at: int
    last_seen: int
    current: bool


class DeviceLinkStartResponse(BaseModel):
    pairing_token: str
    numeric_code: str
    expires_at: int
    pairing_uri: str


class DeviceLinkCompleteRequest(BaseModel):
    pairing_token: str
    code: str
    identity_pub: str
    device_name: str


class DeviceLinkCompleteResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    device_id: str
    access_expires_at: int | None = None
    refresh_expires_at: int | None = None
