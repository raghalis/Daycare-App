from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import SESSION_COOKIE_NAME, get_current_user
from ..models import SessionEvent, SessionEventType, User
from ..schemas import LoginRequest, MeResponse
from ..security import create_session_cookie, verify_password

router = APIRouter(tags=["auth"])


@router.post("/api/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    cookie = create_session_cookie(user.id, user.role.value)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        cookie,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        httponly=True,
        secure=True,
        samesite="lax",
    )
    db.add(
        SessionEvent(
            user_id=user.id,
            event=SessionEventType.login,
            ip_address=request.client.host if request.client else None,
        )
    )
    db.commit()
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
