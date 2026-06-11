from pydantic import BaseModel


class PresenceContactResponse(BaseModel):
    user_id: int
    username: str
    is_online: bool


class PresenceHeartbeatResponse(BaseModel):
    status: str
    ttl_seconds: int
