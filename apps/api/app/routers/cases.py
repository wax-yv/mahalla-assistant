from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_csrf_and_permission, require_permission
from app.models import User
from app.schemas import (
    CaseCreate,
    CaseUpdate,
    TaskCompleteRequest,
    TaskCreate,
    TaskUpdate,
    WorkLogCreate,
)
from pydantic import BaseModel, Field

from app.services import cases as service

router = APIRouter(tags=["cases"])


class TaskCancelBody(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.get("/cases")
def list_cases(
    q: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    citizen_id: str | None = None,
    family_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_permission("tasks.read")),
):
    rows, meta = service.list_cases(
        db,
        q=q,
        status=status,
        priority=priority,
        category=category,
        citizen_id=citizen_id,
        family_id=family_id,
        page=page,
        page_size=page_size,
    )
    return {"items": rows, "meta": meta.model_dump()}


@router.get("/cases/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db), _=Depends(require_permission("tasks.read"))):
    return service.get_case(db, case_id)


@router.post("/cases", status_code=201)
def create_case(
    payload: CaseCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("tasks.create")),
):
    row = service.create_case(db, payload, user.id, getattr(request.state, "request_id", None))
    return service.get_case(db, row.id)


@router.patch("/cases/{case_id}")
def update_case(
    case_id: str,
    payload: CaseUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("tasks.update")),
):
    service.update_case(db, case_id, payload, user.id, getattr(request.state, "request_id", None))
    return service.get_case(db, case_id)


@router.get("/tasks")
def list_tasks(
    q: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    citizen_id: str | None = None,
    family_id: str | None = None,
    case_id: str | None = None,
    assignee: str | None = None,
    timeframe: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_permission("tasks.read")),
):
    rows, meta = service.list_tasks(
        db,
        q=q,
        status=status,
        priority=priority,
        category=category,
        citizen_id=citizen_id,
        family_id=family_id,
        case_id=case_id,
        assignee=assignee,
        timeframe=timeframe,
        page=page,
        page_size=page_size,
    )
    return {"items": rows, "meta": meta.model_dump()}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db), _=Depends(require_permission("tasks.read"))):
    return service.get_task(db, task_id)


@router.post("/tasks", status_code=201)
def create_task(
    payload: TaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("tasks.create")),
):
    row = service.create_task(db, payload, user.id, getattr(request.state, "request_id", None))
    return service.get_task(db, row.id)


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: str,
    payload: TaskUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("tasks.update")),
):
    service.update_task(db, task_id, payload, user.id, getattr(request.state, "request_id", None))
    return service.get_task(db, task_id)


@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: str,
    payload: TaskCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("tasks.complete")),
):
    service.complete_task(db, task_id, payload, user.id, getattr(request.state, "request_id", None))
    return service.get_task(db, task_id)


@router.post("/tasks/{task_id}/cancel")
def cancel_task(
    task_id: str,
    payload: TaskCancelBody,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("tasks.complete")),
):
    service.cancel_task(db, task_id, payload.reason, user.id, getattr(request.state, "request_id", None))
    return service.get_task(db, task_id)


@router.get("/work-logs")
def list_work_logs(
    q: str | None = None,
    citizen_id: str | None = None,
    family_id: str | None = None,
    case_id: str | None = None,
    task_id: str | None = None,
    type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_permission("tasks.read")),
):
    rows, meta = service.list_work_logs(
        db,
        q=q,
        citizen_id=citizen_id,
        family_id=family_id,
        case_id=case_id,
        task_id=task_id,
        type=type,
        page=page,
        page_size=page_size,
    )
    return {"items": rows, "meta": meta.model_dump()}


@router.post("/work-logs", status_code=201)
def create_work_log(
    payload: WorkLogCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("tasks.create")),
):
    row = service.create_work_log(db, payload, user.id, getattr(request.state, "request_id", None))
    return {
        "id": row.id,
        "citizen_id": row.citizen_id,
        "family_id": row.family_id,
        "case_id": row.case_id,
        "task_id": row.task_id,
        "type": row.type,
        "title": row.title,
        "description": row.description,
        "occurred_at": row.occurred_at,
        "author_id": row.author_id,
        "source": row.source,
        "approval_status": row.approval_status,
        "created_at": row.created_at,
    }
