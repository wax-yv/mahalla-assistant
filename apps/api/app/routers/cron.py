from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.errors import forbidden, service_unavailable
from app.core.security import secure_compare
from app.services import scheduler

router = APIRouter(prefix="/cron", tags=["cron"])

DISABLED_SECRETS = {"", "change-me", "changeme", "none", "null"}

def require_cron_secret(authorization: str | None) -> None:
    secret = (settings.cron_secret or "").strip()
    if secret.lower() in DISABLED_SECRETS:
        raise service_unavailable(
            "Cron endpoint sozlanmagan: CRON_SECRET muhit o'zgaruvchisi o'rnatilmagan."
        )
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token or not secure_compare(token, secret):
        raise forbidden("Cron token noto'g'ri.")

@router.get("/run-due")
def run_due(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_cron_secret(authorization)
    return {"items": scheduler.run_due_jobs(db)}
