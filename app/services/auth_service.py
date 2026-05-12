from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings


# bcrypt giới hạn 72 bytes secret. Truncate cứng để tránh ValueError với
# password dài (cũng tương thích với hành vi cũ của passlib < 1.7.4).
_BCRYPT_MAX_BYTES = 72


def _to_secret_bytes(password: str) -> bytes:
    data = password.encode("utf-8")
    if len(data) > _BCRYPT_MAX_BYTES:
        data = data[:_BCRYPT_MAX_BYTES]
    return data


def hash_password(password: str) -> str:
    secret = _to_secret_bytes(password)
    hashed = bcrypt.hashpw(secret, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    secret = _to_secret_bytes(password)
    try:
        return bcrypt.checkpw(secret, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(*, user_id: int) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=int(s.jwt_access_token_minutes))
    payload = {"sub": str(user_id), "iat": int(now.timestamp()), "exp": exp}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
