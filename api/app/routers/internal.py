from urllib.parse import parse_qs

from fastapi import APIRouter, Request, Response, status

from ..database import SessionLocal
from ..models import Camera, Role, User
from ..schedule import evaluate_access
from ..security import decode_stream_token

router = APIRouter(tags=["internal"])


@router.post("/internal/validate")
async def validate(request: Request):
    """
    MediaMTX's auth hook (see mediamtx.yml authHTTPAddress) - called on every
    viewer connect and again on later segments, which is what makes the
    schedule cutoff real rather than a one-time check at handshake. Not
    reachable from the internet: only MediaMTX, over the `internal` Docker
    network, ever calls this. Publish (camera ingest) is excluded in config,
    so only 'read' actions land here.
    """
    body = await request.json()
    if body.get("action") != "read":
        return Response(status_code=status.HTTP_200_OK)

    token = parse_qs(body.get("query", "")).get("token", [None])[0]
    if not token:
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    claims = decode_stream_token(token)
    if not claims:
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    db = SessionLocal()
    try:
        camera = db.get(Camera, claims["cam"])
        if not camera:
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)
        valid_paths = {camera.mediamtx_path} | {s.mediamtx_path for s in camera.streams}
        if body.get("path") not in valid_paths:
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)

        requester = db.get(User, claims["sub"])
        if requester and requester.role in (Role.admin, Role.super_admin):
            return Response(status_code=status.HTTP_200_OK)

        decision = evaluate_access(db, claims["sub"], camera.id)
        if not decision.allowed:
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)
        return Response(status_code=status.HTTP_200_OK)
    finally:
        db.close()
