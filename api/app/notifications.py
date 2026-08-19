import httpx
from sqlalchemy.orm import Session

from .config import settings
from .models import Role, User

PUSHOVER_URL = "https://api.pushover.net/1/messages.json"


def send_pushover(user_key: str, message: str, title: str | None = None, priority: int = 0) -> None:
    if not settings.pushover_app_token:
        return
    data = {
        "token": settings.pushover_app_token,
        "user": user_key,
        "message": message,
        "priority": priority,
    }
    if title:
        data["title"] = title
    try:
        httpx.post(PUSHOVER_URL, data=data, timeout=10)
    except httpx.HTTPError:
        pass  # a failed alert should never take down whatever triggered it


def notify_admins(db: Session, message: str, title: str | None = None, priority: int = 0) -> None:
    admins = (
        db.query(User)
        .filter(User.role.in_([Role.admin, Role.super_admin]))
        .filter(User.is_active.is_(True))
        .filter(User.pushover_user_key.isnot(None))
        .all()
    )
    for admin in admins:
        send_pushover(admin.pushover_user_key, message, title=title, priority=priority)
