from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import require_role
from ..models import (
    AccessGrant,
    Camera,
    CameraHealthEvent,
    Invite,
    OverrideKind,
    Role,
    ScheduleOverride,
    SessionEvent,
    User,
)
from ..schemas import AdminInviteRequest, GrantCreate, OverrideCreate

router = APIRouter(prefix="/api/admin", tags=["admin"])

admin_or_above = require_role(Role.admin, Role.super_admin)
super_admin_only = require_role(Role.super_admin)


@router.post("/invites")
def create_invite(payload: AdminInviteRequest, db: Session = Depends(get_db), actor: User = Depends(admin_or_above)):
    role = Role(payload.role)
    if role != Role.parent and actor.role != Role.super_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a super admin can invite another admin")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "That email already has an account")

    user = User(email=payload.email, display_name=payload.display_name, role=role, password_hash=None)
    db.add(user)
    db.flush()

    invite = Invite(
        email=payload.email,
        role=role,
        created_by=actor.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.invite_ttl_days),
    )
    db.add(invite)
    db.commit()
    return {"invite_id": invite.id, "invite_url_path": f"/invite/{invite.id}"}


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_or_above)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {"id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role.value, "is_active": u.is_active}
        for u in users
    ]


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    is_active: bool | None = None,
    pushover_user_key: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(admin_or_above),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if is_active is not None:
        user.is_active = is_active
    if pushover_user_key is not None:
        user.pushover_user_key = pushover_user_key
    db.commit()
    return {"ok": True}


@router.post("/grants")
def create_grant(payload: GrantCreate, db: Session = Depends(get_db), _: User = Depends(admin_or_above)):
    grant = AccessGrant(
        user_id=payload.user_id,
        camera_id=payload.camera_id,
        days_of_week=payload.days_of_week,
        start_time=time.fromisoformat(payload.start_time),
        end_time=time.fromisoformat(payload.end_time),
    )
    db.add(grant)
    db.commit()
    return {"id": grant.id}


@router.get("/grants")
def list_grants(db: Session = Depends(get_db), _: User = Depends(admin_or_above)):
    grants = db.query(AccessGrant).all()
    return [
        {
            "id": g.id,
            "user_id": g.user_id,
            "camera_id": g.camera_id,
            "days_of_week": g.days_of_week,
            "start_time": g.start_time.isoformat(),
            "end_time": g.end_time.isoformat(),
            "active": g.active,
        }
        for g in grants
    ]


@router.post("/overrides")
def create_override(payload: OverrideCreate, db: Session = Depends(get_db), actor: User = Depends(admin_or_above)):
    override = ScheduleOverride(
        user_id=payload.user_id,
        camera_id=payload.camera_id,
        date=datetime.strptime(payload.date, "%Y-%m-%d").date(),
        kind=OverrideKind(payload.kind),
        start_time=time.fromisoformat(payload.start_time) if payload.start_time else None,
        end_time=time.fromisoformat(payload.end_time) if payload.end_time else None,
        reason=payload.reason,
        created_by=actor.id,
    )
    db.add(override)
    db.commit()
    return {"id": override.id}


@router.get("/cameras")
def list_cameras(db: Session = Depends(get_db), _: User = Depends(admin_or_above)):
    cameras = db.query(Camera).all()
    return [
        {"id": c.id, "label": c.label, "mediamtx_path": c.mediamtx_path, "is_active": c.is_active} for c in cameras
    ]


@router.post("/cameras")
def create_camera(
    label: str,
    mediamtx_path: str,
    rtsp_source: str,
    db: Session = Depends(get_db),
    _: User = Depends(super_admin_only),
):
    camera = Camera(label=label, mediamtx_path=mediamtx_path, rtsp_source=rtsp_source)
    db.add(camera)
    db.commit()
    return {"id": camera.id}


@router.get("/audit")
def audit_log(db: Session = Depends(get_db), _: User = Depends(admin_or_above)):
    events = db.query(SessionEvent).order_by(SessionEvent.occurred_at.desc()).limit(200).all()
    health = db.query(CameraHealthEvent).order_by(CameraHealthEvent.occurred_at.desc()).limit(100).all()
    return {
        "session_events": [
            {
                "id": e.id,
                "user_id": e.user_id,
                "camera_id": e.camera_id,
                "event": e.event.value,
                "occurred_at": e.occurred_at.isoformat(),
                "ip_address": e.ip_address,
            }
            for e in events
        ],
        "camera_health_events": [
            {"id": h.id, "camera_id": h.camera_id, "event": h.event.value, "occurred_at": h.occurred_at.isoformat()}
            for h in health
        ],
    }
