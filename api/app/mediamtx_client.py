import httpx

from .config import settings

# MediaMTX's REST config API - separate from mediamtx.yml, lets paths be
# added/edited/removed at runtime instead of requiring a file edit + restart.
# Endpoint shapes below match the v3 API as of MediaMTX v1.20.1 (same version
# confirmed running in this deployment); if a different version is ever
# pulled and these start failing, the reference is inside the image itself:
#   docker exec access-window-mediamtx wget -qO- http://localhost:9997/v3/config/paths/list
# (or check the OpenAPI spec MediaMTX serves alongside its own API).
#
# Every call here is best-effort: a MediaMTX-side failure never blocks the
# database write. The camera row is the source of truth for this app; a sync
# failure is surfaced back to the caller as a warning; instead of a hard
# error, so an admin can add a camera and fix a MediaMTX-side hiccup after
# the fact rather than losing the whole action.


class MediaMTXSyncError(Exception):
    pass


def _base_url() -> str:
    return settings.mediamtx_api_url.rstrip("/")


def add_path(name: str, source: str) -> None:
    try:
        resp = httpx.post(
            f"{_base_url()}/v3/config/paths/add/{name}",
            json={"source": source, "sourceOnDemand": True},
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise MediaMTXSyncError(str(exc)) from exc


def patch_path(name: str, source: str) -> None:
    try:
        resp = httpx.patch(
            f"{_base_url()}/v3/config/paths/patch/{name}",
            json={"source": source},
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise MediaMTXSyncError(str(exc)) from exc


def remove_path(name: str) -> None:
    try:
        resp = httpx.delete(f"{_base_url()}/v3/config/paths/delete/{name}", timeout=10)
        if resp.status_code == 404:
            return  # already gone - fine, that's the desired end state
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise MediaMTXSyncError(str(exc)) from exc
