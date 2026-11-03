from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_permission
from app.services import dashboard as service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _=Depends(require_permission("reports.read"))):
    return service.summary(db)


@router.get("/dashboard/activity")
def activity(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_permission("reports.read")),
):
    rows, meta = service.activity_page(db, page, page_size)
    return {"items": rows, "meta": meta.model_dump()}


@router.get("/dashboard/tasks")
def dashboard_tasks(db: Session = Depends(get_db), _=Depends(require_permission("tasks.read"))):
    return service.dashboard_tasks(db)


@router.get("/activity")
def activity_alias(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_permission("reports.read")),
):
    rows, meta = service.activity_page(db, page, page_size)
    return {"items": rows, "meta": meta.model_dump()}
