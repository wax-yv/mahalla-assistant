from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import JSON, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _json_default(value):
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

def pool_options(url: str) -> dict:
    if not url.startswith("postgresql"):
        return {}
    if settings.db_pool_null:
        return {"poolclass": NullPool}
    return {
        "pool_size": max(1, int(settings.db_pool_size)),
        "max_overflow": max(0, int(settings.db_max_overflow)),
    }

engine_kwargs: dict = {
    "pool_pre_ping": True,
    "pool_recycle": 280,
    "future": True,
    "json_serializer": lambda value: __import__("json").dumps(
        value, ensure_ascii=False, default=_json_default
    ),
}

engine_kwargs.update(pool_options(settings.sqlalchemy_database_url))

engine = create_engine(settings.sqlalchemy_database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db() -> None:
    from app import models

    Base.metadata.create_all(bind=engine)

def schema_ready() -> bool:
    from app import models

    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT to_regclass('public.app_settings')")).scalar_one() is not None
    except Exception:
        return False

def ensure_schema() -> None:
    if not schema_ready():
        Base.metadata.create_all(bind=engine)

KNOWN_MIGRATION_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("conversations", "user_id", "K-8: suhbat egasi (IDOR himoyasi)"),
    ("citizens", "data_source", "J-6: import manba nomi (255 belgi)"),
    ("backup_runs", "data", "J-8: zaxira nusxa baytlari"),
)

def missing_migrations() -> list[str]:
    if not settings.sqlalchemy_database_url.startswith("postgresql"):
        return []
    missing: list[str] = []
    try:
        with engine.connect() as conn:
            for table, column, label in KNOWN_MIGRATION_COLUMNS:
                found = conn.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = :table "
                        "AND column_name = :column"
                    ),
                    {"table": table, "column": column},
                ).scalar_one()
                if not found:
                    missing.append(f"{label} — {table}.{column}")
    except Exception:
        return []
    return missing

@contextmanager
def advisory_lock(name: str) -> Generator[None, None, None]:
    if not settings.sqlalchemy_database_url.startswith("postgresql"):
        yield
        return
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:name)::bigint)"),
                {"name": name},
            )
            yield
            transaction.commit()
        except Exception:
            transaction.rollback()
            raise
