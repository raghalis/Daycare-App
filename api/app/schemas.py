from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class CameraSummary(BaseModel):
    id: str
    label: str


class MeResponse(BaseModel):
    display_name: str
    role: str
    cameras: list[CameraSummary]


class StreamTokenRequest(BaseModel):
    camera_id: str


class StreamTokenResponse(BaseModel):
    token: str
    stream_url: str
    expires_at: str
    window_end: str | None = None


class SessionStatusResponse(BaseModel):
    allowed: bool
    reason: str
    window_end: str | None = None
    camera_online: bool


class InviteAcceptRequest(BaseModel):
    password: str


class InvitePreview(BaseModel):
    email: str
    role: str
    expires_at: str


class AdminInviteRequest(BaseModel):
    email: EmailStr
    role: str = "parent"
    display_name: str


class GrantCreate(BaseModel):
    user_id: str
    camera_id: str
    days_of_week: int
    start_time: str  # "HH:MM"
    end_time: str


class OverrideCreate(BaseModel):
    user_id: str
    camera_id: str
    date: str  # "YYYY-MM-DD"
    kind: str  # "grant" | "revoke"
    start_time: str | None = None
    end_time: str | None = None
    reason: str | None = None
