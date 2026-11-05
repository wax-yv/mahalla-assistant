from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.deps import client_ip
from app.core.errors import APIError, too_many_requests, unauthenticated
from app.core.security import (
    dummy_password_hash,
    hash_password,
    hash_token,
    needs_rehash,
    new_csrf_token,
    new_session_token,
    session_expiry,
    verify_password,
)
from app.models import RateLimit, Session as SessionModel
from app.models import User

LOGIN_LIMIT = 8
LOGIN_WINDOW_MINUTES = 15
LOGIN_IP_LIMIT = 30

def _window_start(minutes: int) -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(second=0, microsecond=0) - timedelta(
        minutes=now.minute % max(1, minutes)
    )

def _count_for(db: Session, key: str, window: datetime) -> int:
    value = db.execute(
        select(RateLimit.count)
        .where(RateLimit.key == key, RateLimit.window_start == window)
        .limit(1)
    ).scalars().first()
    return int(value or 0)

def check_rate_limit(
    db: Session,
    *,
    key: str,
    limit: int,
    window_minutes: int = LOGIN_WINDOW_MINUTES,
) -> None:
    window = _window_start(window_minutes)
    if _count_for(db, key, window) >= limit:
        raise too_many_requests(
            f"Juda ko'p urinish. {window_minutes} daqiqadan keyin qayta urinib ko'ring."
        )

def _upsert_counter(db: Session, key: str, window: datetime) -> None:
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else ""
    if dialect == "postgresql":
        statement = pg_insert(RateLimit).values(
            key=key, window_start=window, count=1
        )
    elif dialect == "sqlite":
        statement = sqlite_insert(RateLimit).values(
            key=key, window_start=window, count=1
        )
    else:  # pragma: no cover - boshqa dialektlar
        statement = None

    if statement is not None:
        statement = statement.on_conflict_do_update(
            index_elements=[RateLimit.key, RateLimit.window_start],
            set_={"count": RateLimit.count + 1},
        )
        db.execute(statement)
        return

    row = db.execute(
        select(RateLimit).where(
            RateLimit.key == key, RateLimit.window_start == window
        )
    ).scalars().first()
    if row is not None:
        row.count += 1
        return
    db.add(RateLimit(key=key, window_start=window, count=1))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        row = db.execute(
            select(RateLimit).where(
                RateLimit.key == key, RateLimit.window_start == window
            )
        ).scalars().first()
        if row is not None:
            row.count += 1
            db.flush()

def record_failure(
    key: str, window_minutes: int = LOGIN_WINDOW_MINUTES
) -> None:
    window = _window_start(window_minutes)
    with SessionLocal() as session:
        try:
            _upsert_counter(session, key, window)
            session.commit()
        except IntegrityError:
            session.rollback()
            _upsert_counter(session, key, window)
            session.commit()

def reset_failures(keys: list[str], window_minutes: int = LOGIN_WINDOW_MINUTES) -> None:
    window = _window_start(window_minutes)
    with SessionLocal() as session:
        for key in keys:
            row = session.execute(
                select(RateLimit).where(
                    RateLimit.key == key, RateLimit.window_start == window
                )
            ).scalars().first()
            if row is not None:
                row.count = 0
        session.commit()

def record_login_failure(
    *,
    username: str,
    ip: str,
    request_id: str | None = None,
    reason: str = "invalid_credentials",
) -> None:
    normalized = (username or "").strip().lower()[:200]
    with SessionLocal() as session:
        try:
            write_audit(
                session,
                action="auth.login_failed",
                entity_type="user",
                entity_id=None,
                actor_id=None,
                actor_type="anonymous",
                new_value={"username": normalized, "reason": reason},
                request_id=request_id,
                ip=ip,
                result="failure",
            )
            session.commit()
        except Exception:
            session.rollback()

def login_keys(ip: str, username: str) -> list[str]:
    normalized = (username or "").strip().lower()
    return [f"login:ip:{ip}", f"login:user:{normalized}"]

def authenticate(db: Session, username: str, password: str, request: Request) -> User:
    ip = client_ip(request)
    normalized = username.strip().lower()
    keys = login_keys(ip, normalized)
    request_id = getattr(request.state, "request_id", None)

    try:
        check_rate_limit(db, key=keys[0], limit=LOGIN_IP_LIMIT)
        check_rate_limit(db, key=keys[1], limit=LOGIN_LIMIT)
    except APIError:
        db.rollback()
        record_login_failure(
            username=normalized,
            ip=ip,
            request_id=request_id,
            reason="rate_limited",
        )
        raise

    user = db.execute(
        select(User).where(User.username == normalized)
    ).scalar_one_or_none()
    password_ok = (
        verify_password(user.password_hash, password)
        if user is not None
        else verify_password(dummy_password_hash(), password)
    )
    if user is None or not user.is_active or not password_ok:
        db.rollback()
        for key in keys:
            record_failure(key)
        record_login_failure(
            username=normalized,
            ip=ip,
            request_id=request_id,
            reason="invalid_credentials",
        )
        raise unauthenticated("Login yoki parol noto'g'ri.")

    reset_failures(keys)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
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
    from app.core.config import assert_admin_password_allowed

    assert_admin_password_allowed()
    username = (settings.admin_username or "wax").strip().lower()
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        user = User(
            username=username,
            display_name="Mahalla administratori",
            password_hash=hash_password(settings.admin_password or "waxs"),
            role="admin",
            permissions=["reports.approve"],
        )
        db.add(user)
        db.flush()
    elif not verify_password(user.password_hash, settings.admin_password or "waxs"):
        user.password_hash = hash_password(settings.admin_password or "waxs")
        db.flush()
    permissions = list(user.permissions or [])
    if "reports.approve" not in permissions:
        permissions.append("reports.approve")
        user.permissions = permissions
        db.flush()
    return user
