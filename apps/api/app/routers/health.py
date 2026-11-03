from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.db import SessionLocal


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    database = "ok"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as error:
        database = f"error: {type(error).__name__}"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "version": settings.app_version,
        "environment": settings.app_env,
        "database": database,
        "demo_mode": settings.demo_mode,
    }


@router.get("/ready")
def ready() -> dict:
    return health()
