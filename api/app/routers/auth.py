from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import SESSION_COOKIE_NAME, get_current_user
from ..models import SessionEvent, SessionEventType, User
from ..notifications import notify_admins
from ..ratelimit import MAX_ATTEMPTS_PER_EMAIL, clear_failures, is_locked_out, record_failure
from ..schemas import LoginRequest, MeResponse
from ..security import create_session_cookie, verify_password

router = APIRouter(tags=["auth"])


@router.post("/api/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None

    locked, retry_after = is_locked_out(payload.email, ip)
    if locked:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many attempts - try again in {max(retry_after // 60, 1)} minute(s).",
        )

    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        count = record_failure(payload.email, ip)
        if count == MAX_ATTEMPTS_PER_EMAIL:
            # Alert exactly once per lockout, not on every attempt while it's in effect.
            notify_admins(
                db,
                f"{MAX_ATTEMPTS_PER_EMAIL} failed login attempts for {payload.email} from {ip or 'unknown IP'}.",
                title="Possible brute force",
                priority=1,
            )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    # Seen this IP for this user before? If not, it's worth a heads-up -
    # cheap way to catch a shared or leaked password early.
    is_known_ip = (
        ip is not None
        and db.query(SessionEvent)
        .filter(
            SessionEvent.user_id == user.id,
            SessionEvent.event == SessionEventType.login,
            SessionEvent.ip_address == ip,
        )
        .first()
        is not None
    )

    clear_failures(payload.email)

    cookie = create_session_cookie(user.id, user.role.value)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        cookie,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    db.add(SessionEvent(user_id=user.id, event=SessionEventType.login, ip_address=ip))
    db.commit()

    if not is_known_ip and ip:
        notify_admins(db, f"{user.display_name} ({user.email}) logged in from a new location: {ip}", title="New login")

    return {"display_name": user.display_name, "role": user.role.value}


@router.post("/api/logout")
def logout(response: Response, user: User = Depends(get_current_user)):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/api/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    seen = {grant.camera.id: grant.camera for grant in user.grants if grant.active}
    return MeResponse(
        display_name=user.display_name,
        role=user.role.value,
        cameras=[{"id": c.id, "label": c.label} for c in seen.values()],
    )
