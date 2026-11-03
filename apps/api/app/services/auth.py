from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.config import settings
from app.core.deps import client_ip
from app.core.errors import too_many_requests, unauthenticated
from app.core.security import (
    hash_password,
    hash_token,
    new_csrf_token,
    new_session_token,
    session_expiry,
    verify_password,
)
from app.models import RateLimit, Session as SessionModel
from app.models import User


def _window_start(minutes: int) -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(second=0, microsecond=0) - timedelta(
        minutes=now.minute % max(1, minutes)
    )


def check_rate_limit(
    db: Session,
    *,
    key: str,
    limit: int,
    window_minutes: int = 15,
) -> None:
    window = _window_start(window_minutes)
    row = db.execute(
        select(RateLimit).where(
            RateLimit.key == key, RateLimit.window_start == window
        )
    ).scalar_one_or_none()
    if row is None:
        row = RateLimit(key=key, window_start=window, count=1)
        db.add(row)
        db.flush()
        return
    if row.count >= limit:
        raise too_many_requests(
            f"Juda ko'p urinish. {window_minutes} daqiqadan keyin qayta urinib ko'ring."
        )
    row.count += 1
    db.flush()


def authenticate(db: Session, username: str, password: str, request: Request) -> User:
    ip = client_ip(request)
    normalized = username.strip().lower()
    check_rate_limit(db, key=f"login:{ip}:{normalized}", limit=8, window_minutes=15)
    user = db.execute(
        select(User).where(User.username == normalized)
    ).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(user.password_hash, password):
        raise unauthenticated("Login yoki parol noto'g'ri.")
    user.last_login_at = datetime.now(timezone.utc)
    db.flush()
    return user


def create_session(db: Session, user: User, request: Request) -> tuple[str, SessionModel]:
    token = new_session_token()
    session = SessionModel(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=new_csrf_token(),
        expires_at=session_expiry(settings.session_ttl_hours),
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400],
    )
    db.add(session)
    db.flush()
    write_audit(
        db,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        request_id=getattr(request.state, "request_id", None),
        ip=session.ip,
        new_value={"username": user.username},
    )
    return token, session


def revoke_session(db: Session, session: SessionModel, actor_id: str | None = None) -> None:
    session.revoked_at = datetime.now(timezone.utc)
    db.flush()
    write_audit(
        db,
        action="auth.logout",
        entity_type="session",
        entity_id=session.id,
        actor_id=actor_id or session.user_id,
        source="api",
    )


def ensure_admin(db: Session) -> User:
    username = (settings.admin_username or "wax").strip().lower()
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        user = User(
            username=username,
            display_name="Mahalla administratori",
            password_hash=hash_password(settings.admin_password or "waxs"),
            role="admin",
            permissions=[],
        )
        db.add(user)
        db.flush()
    elif not verify_password(user.password_hash, settings.admin_password or "waxs"):
        # Keep the demo credential in sync with the documented login when the
        # admin password is changed via environment variables.
        user.password_hash = hash_password(settings.admin_password or "waxs")
        db.flush()
    return user
