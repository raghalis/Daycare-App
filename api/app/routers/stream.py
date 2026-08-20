from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Camera, CameraHealthEvent, HealthEventType, Role, SessionEvent, SessionEventType, User
from ..schedule import AccessDecision, evaluate_access
from ..schemas import SessionStatusResponse, StreamTokenRequest, StreamTokenResponse
from ..security import create_stream_token, decode_stream_token

router = APIRouter(tags=["stream"])

ADMIN_ROLES = (Role.admin, Role.super_admin)
# The primary stream has no bandwidth/resolution of its own in the DB (it
# predates quality variants) - this is just an ABR hint for the player, high
# enough that it naturally sorts above any variant an admin adds.
PRIMARY_STREAM_BANDWIDTH_BPS = 4_000_000


def _camera_online(db: Session, camera_id: str) -> bool:
    last = (
        db.query(CameraHealthEvent)
        .filter(CameraHealthEvent.camera_id == camera_id)
        .order_by(CameraHealthEvent.occurred_at.desc())
        .first()
    )
    return last is None or last.event == HealthEventType.recovered


def _decide(db: Session, user: User, camera_id: str) -> AccessDecision:
    # Admins can preview any camera for setup/troubleshooting without needing
    # a parent-style schedule grant of their own - the schedule model exists
    # to gate parents, not to gate the people running the system.
    if user.role in ADMIN_ROLES:
        return AccessDecision(allowed=True, reason="admin_override")
    return evaluate_access(db, user.id, camera_id)


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

    decision = _decide(db, user, camera.id)
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

    if camera.streams:
        # Multiple quality tiers - hand back our own master-playlist URL
        # instead of MediaMTX's directly, so hls.js gets real ABR variants.
        stream_url = f"/hls-master/{camera.id}.m3u8?token={token}"
    else:
        stream_url = f"{settings.mediamtx_hls_base_url}/{camera.mediamtx_path}/index.m3u8?token={token}"

    return StreamTokenResponse(
        token=token,
        stream_url=stream_url,
        expires_at=expires_at.isoformat(),
        window_end=decision.window_end.isoformat() if decision.window_end else None,
    )


@router.get("/api/session-status", response_model=SessionStatusResponse)
def session_status(camera_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    decision = _decide(db, user, camera_id)
    return SessionStatusResponse(
        allowed=decision.allowed,
        reason=decision.reason,
        window_end=decision.window_end.isoformat() if decision.window_end else None,
        camera_online=_camera_online(db, camera_id),
    )


@router.get("/hls-master/{camera_id}.m3u8")
def hls_master_playlist(camera_id: str, token: str, db: Session = Depends(get_db)):
    """
    Fetched directly by hls.js, the same way it fetches MediaMTX's own
    .m3u8 - no session cookie involved, just the token in the query string,
    checked the same way MediaMTX's own auth hook checks it. Lists every
    quality tier as an HLS variant; hls.js parses this as a normal master
    playlist, giving bandwidth-adaptive auto-switching by default and a
    `hls.levels` array the player can expose as a manual picker.
    """
    claims = decode_stream_token(token)
    if not claims or claims.get("cam") != camera_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    camera = db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")

    lines = ["#EXTM3U"]

    def add_variant(path: str, label: str, bandwidth_bps: int, resolution: str | None) -> None:
        attrs = f'BANDWIDTH={bandwidth_bps},NAME="{label}"'
        if resolution:
            attrs += f",RESOLUTION={resolution}"
        lines.append(f"#EXT-X-STREAM-INF:{attrs}")
        lines.append(f"{settings.mediamtx_hls_base_url}/{path}/index.m3u8?token={token}")

    add_variant(camera.mediamtx_path, "High", PRIMARY_STREAM_BANDWIDTH_BPS, None)
    for s in camera.streams:
        add_variant(s.mediamtx_path, s.label, s.bandwidth_bps, s.resolution)

    return Response(content="\n".join(lines) + "\n", media_type="application/vnd.apple.mpegurl")
