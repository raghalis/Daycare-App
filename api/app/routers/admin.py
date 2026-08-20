from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
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
from ..schemas import (
    AdminInviteRequest,
    CameraCreate,
    CameraUpdate,
    GrantCreate,
    OverrideCreate,
    UserUpdate,
)
from ..timeutil import to_utc_iso

router = APIRouter(prefix="/api/admin", tags=["admin"])

admin_or_above = require_role(Role.admin, Role.super_admin)
super_admin_only = require_role(Role.super_admin)


def _not_found(label: str):
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")


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
    return {"user_id": user.id, "invite_id": invite.id, "invite_url_path": f"/accept-invite.html?id={invite.id}"}


@router.post("/users/{user_id}/reset-invite")
def reset_invite(user_id: str, db: Session = Depends(get_db), actor: User = Depends(admin_or_above)):
    """
    For a forgotten password, or to cut off a device/account that may be
    compromised: clears the current password (no one can log in with the old
    one anymore) and issues a fresh invite link to set a new one.
    """
    user = db.get(User, user_id)
    if not user:
        _not_found("User")
    if user.role != Role.parent and actor.role != Role.super_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a super admin can reset another admin's access")

    user.password_hash = None
    invite = Invite(
        email=user.email,
        role=user.role,
        created_by=actor.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.invite_ttl_days),
    )
    db.add(invite)
    db.commit()
    return {"invite_id": invite.id, "invite_url_path": f"/accept-invite.html?id={invite.id}"}


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_or_above)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "role": u.role.value,
            "is_active": u.is_active,
            "pushover_user_key": u.pushover_user_key,
            "has_password": u.password_hash is not None,
        }
        for u in users
    ]


@router.patch("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_db), _: User = Depends(admin_or_above)):
    user = db.get(User, user_id)
    if not user:
        _not_found("User")
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.pushover_user_key is not None:
        user.pushover_user_key = payload.pushover_user_key
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


@router.delete("/grants/{grant_id}")
def delete_grant(grant_id: str, db: Session = Depends(get_db), _: User = Depends(admin_or_above)):
    grant = db.get(AccessGrant, grant_id)
    if not grant:
        _not_found("Grant")
    db.delete(grant)
    db.commit()
    return {"ok": True}


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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An override already exists for that parent/camera/date")
    return {"id": override.id}


@router.get("/overrides")
def list_overrides(db: Session = Depends(get_db), _: User = Depends(admin_or_above)):
    overrides = db.query(ScheduleOverride).order_by(ScheduleOverride.date.desc()).all()
    return [
        {
            "id": o.id,
            "user_id": o.user_id,
            "camera_id": o.camera_id,
            "date": o.date.isoformat(),
            "kind": o.kind.value,
            "start_time": o.start_time.isoformat() if o.start_time else None,
            "end_time": o.end_time.isoformat() if o.end_time else None,
            "reason": o.reason,
        }
        for o in overrides
    ]


@router.delete("/overrides/{override_id}")
def delete_override(override_id: str, db: Session = Depends(get_db), _: User = Depends(admin_or_above)):
    override = db.get(ScheduleOverride, override_id)
    if not override:
        _not_found("Override")
    db.delete(override)
    db.commit()
    return {"ok": True}


@router.get("/cameras")
def list_cameras(db: Session = Depends(get_db), _: User = Depends(admin_or_above)):
    cameras = db.query(Camera).all()
    return [
        {"id": c.id, "label": c.label, "mediamtx_path": c.mediamtx_path, "is_active": c.is_active} for c in cameras
    ]


@router.post("/cameras")
def create_camera(payload: CameraCreate, db: Session = Depends(get_db), _: User = Depends(super_admin_only)):
    camera = Camera(label=payload.label, mediamtx_path=payload.mediamtx_path, rtsp_source=payload.rtsp_source)
    db.add(camera)
    db.commit()
    return {"id": camera.id}


@router.patch("/cameras/{camera_id}")
def update_camera(
    camera_id: str, payload: CameraUpdate, db: Session = Depends(get_db), _: User = Depends(super_admin_only)
):
    camera = db.get(Camera, camera_id)
    if not camera:
        _not_found("Camera")
    if payload.label is not None:
        camera.label = payload.label
    if payload.is_active is not None:
        camera.is_active = payload.is_active
    db.commit()
    return {"ok": True}


@router.delete("/cameras/{camera_id}")
def delete_camera(camera_id: str, db: Session = Depends(get_db), _: User = Depends(super_admin_only)):
    camera = db.get(Camera, camera_id)
    if not camera:
        _not_found("Camera")
    db.delete(camera)
    db.commit()
    return {"ok": True}


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
                "occurred_at": to_utc_iso(e.occurred_at),
                "ip_address": e.ip_address,
            }
            for e in events
        ],
        "camera_health_events": [
            {"id": h.id, "camera_id": h.camera_id, "event": h.event.value, "occurred_at": to_utc_iso(h.occurred_at)}
            for h in health
        ],
    }
