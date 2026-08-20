import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone

# Deliberately not pulled through MediaMTX - MediaMTX has no built-in still-
# frame endpoint, and a path's RTSP pull only starts on-demand once a viewer
# connects, so there'd be nothing to grab from until something else asked
# for the stream first. This connects to the camera directly instead.

SNAPSHOT_TTL = timedelta(seconds=15)
GRAB_TIMEOUT_SECONDS = 12

_cache: dict[str, tuple[bytes, datetime]] = {}


def _grab_frame(rtsp_source: str) -> bytes | None:
    """
    Grabbing the very first frame off a fresh RTSP connection (`-frames:v 1`
    right away) tends to land on a partial frame decoded before a full
    reference exists - shows up as a flat grey tile or block artifacts. The
    standard fix: let the decoder run for a couple of seconds, continuously
    overwriting one output file (`-update 1`), and read back whatever's
    there at the end - by then it's had time to stabilize on a real frame.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = os.path.join(tmp_dir, "frame.jpg")
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-rtsp_transport",
                    "tcp",
                    "-i",
                    rtsp_source,
                    "-t",
                    "2",
                    "-vf",
                    "fps=1",
                    "-update",
                    "1",
                    "-q:v",
                    "4",
                    out_path,
                ],
                capture_output=True,
                timeout=GRAB_TIMEOUT_SECONDS,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None

        if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            return None
        with open(out_path, "rb") as f:
            return f.read()


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
