from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Invite, User
from ..schemas import InviteAcceptRequest, InvitePreview
from ..security import hash_password

router = APIRouter(tags=["invites"])


def _load_valid_invite(invite_id: str, db: Session) -> Invite:
    invite = db.get(Invite, invite_id)
    if not invite:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found")
    if invite.accepted_at is not None:
        raise HTTPException(status.HTTP_410_GONE, "Invite already used")
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_410_GONE, "Invite expired")
    return invite


@router.get("/invite/{invite_id}", response_model=InvitePreview)
def preview_invite(invite_id: str, db: Session = Depends(get_db)):
    invite = _load_valid_invite(invite_id, db)
    return InvitePreview(email=invite.email, role=invite.role.value, expires_at=invite.expires_at.isoformat())


@router.post("/invite/{invite_id}/accept")
def accept_invite(invite_id: str, payload: InviteAcceptRequest, db: Session = Depends(get_db)):
    invite = _load_valid_invite(invite_id, db)
    user = db.query(User).filter(User.email == invite.email).one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No account is waiting on this invite")

    user.password_hash = hash_password(payload.password)
    invite.accepted_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
