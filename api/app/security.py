import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import settings

_hasher = PasswordHasher()
_session_serializer = URLSafeTimedSerializer(settings.session_secret, salt="session")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_session_cookie(user_id: str, role: str) -> str:
    return _session_serializer.dumps({"user_id": user_id, "role": role})


def read_session_cookie(cookie_value: str) -> dict | None:
    try:
        return _session_serializer.loads(cookie_value, max_age=settings.session_ttl_hours * 3600)
    except (BadSignature, SignatureExpired):
        return None


def create_stream_token(user_id: str, camera_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "cam": camera_id,
        "iat": now,
        "exp": now + timedelta(seconds=settings.stream_token_ttl_seconds),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.stream_token_secret, algorithm="HS256")


def decode_stream_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.stream_token_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
