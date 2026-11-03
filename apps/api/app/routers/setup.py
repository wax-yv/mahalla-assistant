from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import Base, engine, get_db
from app.core.errors import forbidden
from app.models import Citizen, User
from app.services.auth import ensure_admin

router = APIRouter(tags=["setup"])


@router.post("/setup")
def setup(
    x_setup_token: str | None = Header(default=None, alias="X-Setup-Token"),
    db: Session = Depends(get_db),
):
    Base.metadata.create_all(bind=engine)  # explicit setup always ensures full schema
    users = int(db.execute(select(func.count()).select_from(User)).scalar_one())
    citizens = int(db.execute(select(func.count()).select_from(Citizen)).scalar_one())
    is_first_run = users == 0
    needs_seed = citizens == 0
    expected = (settings.setup_token or "").strip()
    token_ok = bool(
        expected
        and expected != "change-me"
        and x_setup_token
        and secrets.compare_digest(x_setup_token, expected)
    )
    if not is_first_run and not token_ok:
        raise forbidden("Setup uchun to'g'ri X-Setup-Token kerak.")
    if not needs_seed:
        ensure_admin(db)
        db.commit()
        return {"ok": True, "seeded": False, "message": "Ma'lumotlar allaqachon yuklangan."}
    from app import seed

    seed.run()
    return {
        "ok": True,
        "seeded": True,
        "message": "Baza yaratildi va demo ma'lumotlar yuklandi.",
        "citizens": int(db.execute(select(func.count()).select_from(Citizen)).scalar_one()),
    }


@router.get("/setup/status")
def setup_status(db: Session = Depends(get_db)):
    try:
        users = int(db.execute(select(func.count()).select_from(User)).scalar_one())
        citizens = int(db.execute(select(func.count()).select_from(Citizen)).scalar_one())
    except Exception as error:
        db.rollback()
        return {"database": "error", "detail": str(error)[:300], "setup_required": True}
    return {
        "database": "ok",
        "users": users,
        "citizens": citizens,
        "setup_required": users == 0 or citizens == 0,
    }
