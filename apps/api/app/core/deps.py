from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Annotated, Callable

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.db import get_db
from app.core.errors import APIError, forbidden, unauthenticated
from app.core.security import CSRF_HEADER, SESSION_COOKIE, hash_token, secure_compare
from app.core.config import settings
from app.models import Session as SessionModel
from app.models import User


def client_ip(request: Request) -> str:
    """Mijoz manzilini ishonchli manzildan aniqlaydi (O-1).

    X-Forwarded-For sarlavhasiga **ishonmaydi** — mijoz uni o'zi yozishi
    mumkin. `TRUSTED_PROXY_HOPS` sozlamasi proksi zanjirining uzunligini
    bildiradi: XFF'ning o'ng tomonidan shu N-chi element haqiqiy mijoz
    manzili bo'lib hisoblanadi. Sozlama 0 bo'lsa (yoki o'zgarmagan bo'lsa)
    XFF butunlay e'tiborsiz qoldiriladi va `request.client.host` ishlatiladi.
    """
    direct = (request.client.host if request.client else "unknown")[:64]
    try:
        hops = int(getattr(settings, "trusted_proxy_hops", 0) or 0)
    except (TypeError, ValueError):
        hops = 0
    if hops <= 0:
        return direct
    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return direct
    parts = [item.strip() for item in forwarded.split(",") if item.strip()]
    if len(parts) < hops:
        # Ishonchli proksi sonidan kam qiymat bor — XFF'ga ishonib bo'lmaydi.
        return direct
    return parts[-hops][:64]


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or ""


def get_current_session(
    request: Request,
    db: Annotated[DbSession, Depends(get_db)],
) -> SessionModel:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise unauthenticated()
    token_hash = hash_token(token)
    session = db.execute(
        select(SessionModel).where(SessionModel.token_hash == token_hash)
    ).scalar_one_or_none()
    if session is None:
        raise unauthenticated("Sessiya topilmadi. Qaytadan kiring.")
    now = datetime.now(timezone.utc)
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if session.revoked_at is not None or expires <= now:
        raise unauthenticated("Sessiya muddati tugagan. Qaytadan kiring.")
    session.last_seen_at = now
    db.flush()
    return session


def get_current_user(
    request: Request,
    db: Annotated[DbSession, Depends(get_db)],
    session: Annotated[SessionModel, Depends(get_current_session)],
) -> User:
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise unauthenticated("Foydalanuvchi faol emas.")
    return user


def enforce_csrf(
    request: Request,
    session: Annotated[SessionModel, Depends(get_current_session)],
) -> None:
    header = request.headers.get(CSRF_HEADER, "")
    if not header or not secure_compare(header, session.csrf_token):
        raise APIError(403, "CSRF_FAILED", "Xavfsizlik tekshiruvi muvaffaqiyatsiz. Sahifani yangilang.")


# O-16: "segregation of duties" — bu permission'lar foydalanuvchi ro'yxatida
# **aniq** ko'rsatilishi shart. `admin` roli ularni avtomatik bermaydi:
# kim hisobotni yozsa, o'sha o'zini tasdiqlay olmasin.
EXPLICIT_ONLY_PERMISSIONS: frozenset[str] = frozenset({"reports.approve"})


def has_permission(user: User, permission: str) -> bool:
    if permission in EXPLICIT_ONLY_PERMISSIONS:
        return permission in (user.permissions or [])
    return user.role == "admin" or permission in (user.permissions or [])


def require_permission(permission: str) -> Callable:
    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not has_permission(user, permission):
            raise forbidden()
        return user

    return dependency


def require_csrf_and_permission(permission: str) -> Callable:
    def dependency(
        request: Request,
        user: Annotated[User, Depends(get_current_user)],
        session: Annotated[SessionModel, Depends(get_current_session)],
    ) -> User:
        if not has_permission(user, permission):
            raise forbidden()
        enforce_csrf(request, session)
        return user

    return dependency


CurrentUser = Annotated[User, Depends(get_current_user)]
DbDep = Annotated[DbSession, Depends(get_db)]


def stable_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
