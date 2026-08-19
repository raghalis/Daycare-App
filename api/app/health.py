from datetime import datetime, timedelta, timezone

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings
from .database import SessionLocal
from .models import Camera, CameraHealthEvent, HealthEventType
from .notifications import notify_admins

_scheduler = BackgroundScheduler(timezone="UTC")
_unready_since: dict[str, datetime] = {}
OFFLINE_DEBOUNCE = timedelta(seconds=30)  # ignore a single dropped frame during e.g. a Protect reboot


def _current_state(db, camera_id: str) -> HealthEventType | None:
    last = (
        db.query(CameraHealthEvent)
        .filter(CameraHealthEvent.camera_id == camera_id)
        .order_by(CameraHealthEvent.occurred_at.desc())
        .first()
    )
    return last.event if last else None


def poll_camera_health() -> None:
    db = SessionLocal()
    try:
        cameras = db.query(Camera).filter(Camera.is_active.is_(True)).all()
        if not cameras:
            return

        try:
            resp = httpx.get(f"{settings.mediamtx_api_url}/v3/paths/list", timeout=10)
            resp.raise_for_status()
            paths = {p["name"]: p for p in resp.json().get("items", [])}
        except httpx.HTTPError:
            paths = {}  # MediaMTX itself is unreachable - treat every camera as unready this tick

        now = datetime.now(timezone.utc)
        for camera in cameras:
            ready = bool(paths.get(camera.mediamtx_path, {}).get("ready"))
            current_state = _current_state(db, camera.id)

            if ready:
                _unready_since.pop(camera.id, None)
                if current_state == HealthEventType.offline:
                    db.add(CameraHealthEvent(camera_id=camera.id, event=HealthEventType.recovered, notified_at=now))
                    notify_admins(db, f"{camera.label} is back online.", title="Camera recovered")
                    db.commit()
                continue

            first_seen = _unready_since.setdefault(camera.id, now)
            if now - first_seen >= OFFLINE_DEBOUNCE and current_state != HealthEventType.offline:
                db.add(CameraHealthEvent(camera_id=camera.id, event=HealthEventType.offline, notified_at=now))
                notify_admins(db, f"{camera.label} has gone offline.", title="Camera offline", priority=1)
                db.commit()
    finally:
        db.close()


def start_health_scheduler() -> None:
    _scheduler.add_job(poll_camera_health, "interval", seconds=20, id="camera_health_poll", replace_existing=True)
    _scheduler.start()
