from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_csrf_and_permission, require_permission
from app.core.downloads import content_disposition
from app.models import User
from app.schemas import ReportApproveRequest, ReportGenerateRequest
from app.services import reports as service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def list_reports(
    type: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_permission("reports.read")),
):
    rows, meta = service.list_reports(db, type=type, status=status, page=page, page_size=page_size)
    return {"items": rows, "meta": meta.model_dump()}


@router.post("", status_code=201)
def generate_report(
    payload: ReportGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("reports.generate")),
):
    report = service.generate_report(
        db, payload, actor=user.id, request_id=getattr(request.state, "request_id", None)
    )
    return service.get_report(db, report.id)


@router.get("/{report_id}")
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_permission("reports.read")),
):
    return service.get_report(db, report_id)


@router.post("/{report_id}/approve")
def approve_report(
    report_id: str,
    payload: ReportApproveRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("reports.generate")),
):
    service.approve_report(
        db,
        report_id,
        user.id,
        payload.note,
        getattr(request.state, "request_id", None),
    )
    return service.get_report(db, report_id)


@router.get("/{report_id}/export")
def export_report(
    report_id: str,
    format: str = Query("docx"),
    db: Session = Depends(get_db),
    _=Depends(require_permission("reports.export")),
):
    data, filename, media_type = service.export_report(db, report_id, format)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": content_disposition(filename)},
    )
