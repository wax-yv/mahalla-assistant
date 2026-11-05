from __future__ import annotations

import functools
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)

SESSION_COOKIE = "mahalla_session"
CSRF_HEADER = "X-CSRF-Token"


@functools.lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """Soxta xesh (D-4).

    Foydalanuvchi topilmasa ham `verify_password` chaqiriladi — aks holda
    javob vaqti username mavjudligini oshkor qiladi (timing attack).
    """
    return _hasher.hash("mahalla-assistant-dummy-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return True


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def secure_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def session_expiry(hours: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)
