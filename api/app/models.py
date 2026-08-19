import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Role(str, enum.Enum):
    parent = "parent"
    admin = "admin"
    super_admin = "super_admin"


class OverrideKind(str, enum.Enum):
    grant = "grant"
    revoke = "revoke"


class SessionEventType(str, enum.Enum):
    login = "login"
    token_issued = "token_issued"
    token_denied = "token_denied"
    window_closed = "window_closed"


class HealthEventType(str, enum.Enum):
    offline = "offline"
    recovered = "recovered"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Null until the invite is accepted - the parent sets it themselves, never the admin.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.parent)
    display_name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Admin/super_admin only - lets each of them get their own Pushover alerts.
    pushover_user_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    grants: Mapped[list["AccessGrant"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    overrides: Mapped[list["ScheduleOverride"]] = relationship(
        foreign_keys="ScheduleOverride.user_id", back_populates="user", cascade="all, delete-orphan"
    )


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.parent)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    label: Mapped[str] = mapped_column(String(120))
    mediamtx_path: Mapped[str] = mapped_column(String(120), unique=True)
    # Lives here for MediaMTX/admin config only - never returned by any API response.
    rtsp_source: Mapped[str] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    grants: Mapped[list["AccessGrant"]] = relationship(back_populates="camera", cascade="all, delete-orphan")


class AccessGrant(Base):
    __tablename__ = "access_grants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    camera_id: Mapped[str] = mapped_column(String(36), ForeignKey("cameras.id"))
    days_of_week: Mapped[int] = mapped_column(Integer)  # bit 0 = Monday ... bit 6 = Sunday
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="grants")
    camera: Mapped["Camera"] = relationship(back_populates="grants")


class ScheduleOverride(Base):
    __tablename__ = "schedule_overrides"
    __table_args__ = (UniqueConstraint("user_id", "camera_id", "date", name="uq_override_per_day"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    camera_id: Mapped[str] = mapped_column(String(36), ForeignKey("cameras.id"))
    date: Mapped[date] = mapped_column(Date)
    kind: Mapped[OverrideKind] = mapped_column(Enum(OverrideKind))
    # Only meaningful for kind = grant; null means "the same hours as a normal day."
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(foreign_keys=[user_id], back_populates="overrides")


class SessionEvent(Base):
    __tablename__ = "session_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    camera_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("cameras.id"), nullable=True)
    event: Mapped[SessionEventType] = mapped_column(Enum(SessionEventType))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CameraHealthEvent(Base):
    __tablename__ = "camera_health_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(String(36), ForeignKey("cameras.id"))
    event: Mapped[HealthEventType] = mapped_column(Enum(HealthEventType))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # One alert per outage, not one per health check poll - see app/health.py.
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
