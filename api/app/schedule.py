from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .config import settings
from .models import AccessGrant, OverrideKind, ScheduleOverride

TZ = ZoneInfo(settings.app_timezone)


@dataclass
class AccessDecision:
    allowed: bool
    reason: str
    window_end: datetime | None = None


def _today_bit(d: date) -> int:
    return 1 << d.weekday()  # Monday = bit 0 ... Sunday = bit 6


def evaluate_access(db: Session, user_id: str, camera_id: str, now: datetime | None = None) -> AccessDecision:
    """
    The single source of truth for "can this user watch this camera right
    now." Called at token issuance, on every MediaMTX auth-hook check, and
    for the viewer page's status polling - all three must agree, so they all
    call this instead of each doing their own window math.
    """
    now = (now or datetime.now(TZ)).astimezone(TZ)
    today = now.date()

    override = (
        db.query(ScheduleOverride)
        .filter(
            ScheduleOverride.user_id == user_id,
            ScheduleOverride.camera_id == camera_id,
            ScheduleOverride.date == today,
        )
        .one_or_none()
    )

    if override and override.kind == OverrideKind.revoke:
        return AccessDecision(allowed=False, reason="revoked_today")

    if override and override.kind == OverrideKind.grant:
        start = override.start_time or time.min
        end = override.end_time or time.max
        if start <= now.time() <= end:
            return AccessDecision(allowed=True, reason="override_grant", window_end=datetime.combine(today, end, TZ))
        return AccessDecision(allowed=False, reason="outside_override_window")

    grants = (
        db.query(AccessGrant)
        .filter(
            AccessGrant.user_id == user_id,
            AccessGrant.camera_id == camera_id,
            AccessGrant.active.is_(True),
        )
        .all()
    )
    bit = _today_bit(today)
    for grant in grants:
        if grant.days_of_week & bit and grant.start_time <= now.time() <= grant.end_time:
            return AccessDecision(
                allowed=True, reason="weekly_grant", window_end=datetime.combine(today, grant.end_time, TZ)
            )

    return AccessDecision(allowed=False, reason="no_matching_window")
