import subprocess
from datetime import datetime, timedelta, timezone

# Deliberately not pulled through MediaMTX - MediaMTX has no built-in still-
# frame endpoint, and a path's RTSP pull only starts on-demand once a viewer
# connects, so there'd be nothing to grab from until something else asked
# for the stream first. This connects to the camera directly instead.

SNAPSHOT_TTL = timedelta(seconds=15)
GRAB_TIMEOUT_SECONDS = 8

_cache: dict[str, tuple[bytes, datetime]] = {}


def _grab_frame(rtsp_source: str) -> bytes | None:
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-rtsp_transport",
                "tcp",
                "-i",
                rtsp_source,
                "-frames:v",
                "1",
                "-f",
                "image2",
                "-",
            ],
            capture_output=True,
            timeout=GRAB_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    return result.stdout


def get_snapshot(camera_id: str, rtsp_source: str) -> bytes | None:
    """Cached per camera so N browser tabs polling every 15s don't each
    trigger their own ffmpeg process - only the first request past the TTL
    does. Serves a stale frame rather than nothing if a fresh grab fails,
    since a slightly-old still is more useful than a blank tile."""
    now = datetime.now(timezone.utc)
    cached = _cache.get(camera_id)
    if cached and now - cached[1] < SNAPSHOT_TTL:
        return cached[0]

    frame = _grab_frame(rtsp_source)
    if frame:
        _cache[camera_id] = (frame, now)
        return frame
    return cached[0] if cached else None
