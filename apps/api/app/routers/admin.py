from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_csrf_and_permission, require_permission
from app.core.downloads import content_disposition
from app.models import User
from app.services import admin as service
from app.services import scheduler

router = APIRouter(prefix="/admin", tags=["admin"])

class SettingsUpdate(BaseModel):
    values: dict[str, Any]

@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _=Depends(require_permission("settings.manage"))):
    return service.get_settings(db)

@router.patch("/settings")
def update_settings(
    payload: SettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("settings.manage")),
):
    return service.update_settings(
        db, payload.values, user.id, getattr(request.state, "request_id", None)
    )

@router.get("/audit")
def audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    action: str | None = None,
    entity_type: str | None = None,
    actor_id: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_permission("audit.read")),
):
    rows, meta = service.audit_page(
        db,
        page=page,
        page_size=page_size,
        action=action,
        entity_type=entity_type,
        actor_id=actor_id,
        q=q,
    )
    return {"items": rows, "meta": meta.model_dump()}

@router.get("/usage")
def usage(
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
    _=Depends(require_permission("settings.manage")),
):
    return service.usage_summary(db, days=days)

@router.get("/system")
def system(db: Session = Depends(get_db), _=Depends(require_permission("settings.manage"))):
    return service.system_info(db)

@router.get("/jobs")
def jobs(db: Session = Depends(get_db), _=Depends(require_permission("settings.manage"))):
    return {"items": scheduler.list_jobs(db)}

@router.post("/jobs/{job_id}/run")
def run_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("settings.manage")),
):
    job = scheduler.get_job(db, job_id)
    return scheduler.run_job(db, job, actor=user.id)

@router.post("/jobs/run-due")
def run_due(
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("settings.manage")),
):
    return {"items": scheduler.run_due_jobs(db)}

@router.get("/backups")
def backups(
    db: Session = Depends(get_db),
    _=Depends(require_permission("settings.manage")),
):
    return {"items": service.list_backups(db)}

@router.post("/backups")
def create_backup(
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("settings.manage")),
):
    summary, digest = service.create_backup(db, user.id)
    return {
        "backup_id": summary["backup_id"],
        "sha256": digest,
        "generated_at": summary["generated_at"],
        "counts": summary["counts"],
    }

class BackupRestoreRequest(BaseModel):
    mode: Literal["merge", "replace"] = "merge"


@router.post("/backups/{backup_id}/restore")
def restore_backup(
    backup_id: str,
    payload: BackupRestoreRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("settings.manage")),
):
    from app.core.errors import bad_request, not_found
    from app.models import BackupRun

    backup = db.get(BackupRun, backup_id)
    if backup is None:
        raise not_found("Backup topilmadi.")
    if not backup.data:
        raise bad_request(
            "Bu zaxira nusxa saqlanmagan. Yangi zaxira nusxa yarating."
        )
    result = service.restore_backup(
        db, backup_id, user.id, getattr(request.state, "request_id", None), mode=payload.mode
    )
    return result

@router.get("/backups/{backup_id}/download")
def download_backup(
    backup_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("settings.manage")),
):
    import hashlib

    from fastapi.responses import Response

    from app.core.errors import bad_request, not_found
    from app.models import BackupRun

    backup = db.get(BackupRun, backup_id)
    if backup is None:
        raise not_found("Backup topilmadi.")
    if not backup.data:
        raise bad_request(
            "Bu zaxira nusxa saqlanmagan. Yangi zaxira nusxa yarating "
            "(migratsiya bajarilmagan bo'lsa, `scripts/migrate.sql` ni ishga tushiring)."
        )
    data = bytes(backup.data)
    digest = hashlib.sha256(data).hexdigest()
    expected = (backup.location or "").rsplit("sha256:", 1)[-1]
    if expected and expected != digest:
        raise bad_request("Zaxira nusxa yaxlitligi tekshiruvdan o'tmadi (sha256 mos kelmadi).")
    return Response(
        content=data,
        media_type="application/json",
        headers={
            "Content-Disposition": content_disposition(
                f"mahalla-backup-{backup_id}.json"
            ),
            "X-Backup-SHA256": digest,
        },
    )
