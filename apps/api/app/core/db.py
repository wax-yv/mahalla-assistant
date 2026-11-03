from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import JSON, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


def _json_default(value):
    """JSON serializer fallback for date/datetime/Decimal/UUID values."""
    import decimal
    import uuid
    from datetime import date as _date

    if isinstance(value, (_date, datetime)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


JSONType = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


engine_kwargs: dict = {
    "pool_pre_ping": True,
    "pool_recycle": 280,
    "future": True,
    "json_serializer": lambda value: __import__("json").dumps(
        value, ensure_ascii=False, default=_json_default
    ),
}

if settings.sqlalchemy_database_url.startswith("postgresql"):
    engine_kwargs.update({"pool_size": 5, "max_overflow": 5})

engine = create_engine(settings.sqlalchemy_database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import models so metadata is populated.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def schema_ready() -> bool:
    """Cheap check so serverless cold starts skip the full create_all."""
    from app import models  # noqa: F401

    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT to_regclass('public.app_settings')")).scalar_one() is not None
    except Exception:
        return False


def ensure_schema() -> None:
    if not schema_ready():
        Base.metadata.create_all(bind=engine)


@contextmanager
def advisory_lock(name: str) -> Generator[None, None, None]:
    """Cross-process lock used by bootstrap/seed. Postgres-only, no-op elsewhere."""
    if not settings.sqlalchemy_database_url.startswith("postgresql"):
        yield
        return
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(hashtext(:name))"), {"name": name})
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(hashtext(:name))"), {"name": name})
            conn.commit()
