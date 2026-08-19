from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Camera, CameraHealthEvent, HealthEventType, SessionEvent, SessionEventType, User
from ..schedule import evaluate_access
from ..schemas import SessionStatusResponse, StreamTokenRequest, StreamTokenResponse
from ..security import create_stream_token

router = APIRouter(tags=["stream"])


def _camera_online(db: Session, camera_id: str) -> bool:
    last = (
        db.query(CameraHealthEvent)
        .filter(CameraHealthEvent.camera_id == camera_id)
        .order_by(CameraHealthEvent.occurred_at.desc())
        .first()
    )
    return last is None or last.event == HealthEventType.recovered


@router.post("/api/stream-token", response_model=StreamTokenResponse)
def issue_stream_token(
    payload: StreamTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    camera = db.get(Camera, payload.camera_id)
    if not camera or not camera.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")

    decision = evaluate_access(db, user.id, camera.id)
    db.add(
        SessionEvent(
            user_id=user.id,
            camera_id=camera.id,
            event=SessionEventType.token_issued if decision.allowed else SessionEventType.token_denied,
            ip_address=request.client.host if request.client else None,
        )
    )
    db.commit()

    if not decision.allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, decision.reason)

    token = create_stream_token(user.id, camera.id)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.stream_token_ttl_seconds)
    return StreamTokenResponse(
        token=token,
        stream_url=f"{settings.mediamtx_hls_base_url}/{camera.mediamtx_path}/index.m3u8?token={token}",
        expires_at=expires_at.isoformat(),
        window_end=decision.window_end.isoformat() if decision.window_end else None,
    )


@router.get("/api/session-status", response_model=SessionStatusResponse)
def session_status(camera_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    decision = evaluate_access(db, user.id, camera_id)
    return SessionStatusResponse(
        allowed=decision.allowed,
        reason=decision.reason,
        window_end=decision.window_end.isoformat() if decision.window_end else None,
        camera_online=_camera_online(db, camera_id),
    )
