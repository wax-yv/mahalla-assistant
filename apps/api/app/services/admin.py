from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.config import settings
from app.core.errors import validation_error
from app.core.pagination import PageMeta, paginate
from app.core.search import like_pattern
from app.models import (
    AIUsage,
    AuditLog,
    BackupRun,
    Case,
    Citizen,
    Document,
    Family,
    House,
    Mahalla,
    MemoryItem,
    Program,
    Report,
    Street,
    Task,
    User,
    WorkLog,
)
from app.services import ai_gateway

ALLOWED_SETTINGS = {
    "theme",
    "language",
    "timezone",
    "ai_provider",
    "ai_model",
    "ai_budget",
    "agents_enabled",
    "scheduler_time",
    "demo_mode",
    "mahalla",
    "district",
    "region",
}

def get_settings(db: Session) -> dict[str, Any]:
    from app.models import AppSetting

    row = db.get(AppSetting, "app")
    value = dict(row.value or {}) if row else {}
    defaults = {
        "theme": "system",
        "language": "uz-Latn",
        "timezone": "Asia/Tashkent",
        "ai_provider": settings.ai_default_provider,
        "ai_model": "",
        "ai_budget": settings.ai_daily_token_budget,
        "agents_enabled": {
            "document": True,
            "reporting": True,
            "legislation": True,
            "credit_subsidy": True,
            "plan_control": True,
        },
        "scheduler_time": "21:00",
        "demo_mode": settings.demo_mode,
        "mahalla": "Navbahor mahallasi",
        "district": "Urganch shahri",
        "region": "Xorazm viloyati",
    }
    defaults.update(value)
    defaults["usage"] = ai_gateway.usage_today(db)
    defaults["providers"] = ai_gateway.provider_status()
    return defaults

def update_settings(db: Session, updates: dict[str, Any], actor: str, request_id: str | None) -> dict[str, Any]:
    from app.models import AppSetting

    unknown = set(updates) - ALLOWED_SETTINGS
    if unknown:
        raise validation_error(
            "Quyidagi sozlamalar qo'llab-quvvatlanmaydi: " + ", ".join(sorted(unknown))
        )
    if "ai_model" in updates:
        requested = (updates.get("ai_model") or "").strip()
        if requested:
            known = {model["id"] for model in ai_gateway.available_models()}
            if requested not in known:
                raise validation_error(
                    "Tanlangan model mavjud emas. Model ro'yxatidan tanlang."
                )
    if "ai_budget" in updates:
        try:
            budget = int(updates["ai_budget"])
        except (TypeError, ValueError) as error:
            raise validation_error("AI budjeti butun son bo'lishi kerak.") from error
        if budget < 1000:
            raise validation_error("AI budjeti kamida 1000 token bo'lishi kerak.")
        updates["ai_budget"] = budget
    row = db.get(AppSetting, "app")
    if row is None:
        row = AppSetting(key="app", value={})
        db.add(row)
        db.flush()
    old = dict(row.value or {})
    value = {**old, **updates}
    row.value = value
    write_audit(
        db,
        action="settings.updated",
        entity_type="app_settings",
        entity_id="app",
        actor_id=actor,
        old_value={key: old.get(key) for key in updates},
        new_value=updates,
        request_id=request_id,
    )
    db.commit()
    return get_settings(db)

def audit_page(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 30,
    action: str | None = None,
    entity_type: str | None = None,
    actor_id: str | None = None,
    q: str | None = None,
) -> tuple[list[dict[str, Any]], PageMeta]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        stmt = stmt.where(AuditLog.action.ilike(like_pattern(action), escape="\\"))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if q:
        term = like_pattern(q.strip())
        stmt = stmt.where(
            or_(AuditLog.action.ilike(term, escape="\\"), AuditLog.entity_id.ilike(term, escape="\\"))
        )
    rows, meta = paginate(db, stmt, page, page_size)
    return [
        {
            "id": row.id,
            "actor_type": row.actor_type,
            "actor_id": row.actor_id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "old_value": row.old_value,
            "new_value": row.new_value,
            "request_id": row.request_id,
            "source": row.source,
            "ip": row.ip,
            "result": row.result,
            "created_at": row.created_at,
        }
        for row in rows
    ], meta

def usage_summary(db: Session, days: int = 14) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=max(1, min(90, days)))
    day_rows = db.execute(
        select(
            func.date(AIUsage.created_at).label("day"),
            func.coalesce(func.sum(AIUsage.prompt_tokens), 0),
            func.coalesce(func.sum(AIUsage.completion_tokens), 0),
            func.coalesce(func.sum(AIUsage.total_tokens), 0),
            func.count(),
        )
        .where(AIUsage.created_at >= since)
        .group_by(func.date(AIUsage.created_at))
        .order_by(func.date(AIUsage.created_at))
    ).all()
    model_rows = db.execute(
        select(
            AIUsage.model,
            AIUsage.provider,
            func.coalesce(func.sum(AIUsage.total_tokens), 0),
            func.count(),
        )
        .where(AIUsage.created_at >= since)
        .group_by(AIUsage.model, AIUsage.provider)
    ).all()
    by_day = [
        {
            "date": str(row[0]),
            "prompt": int(row[1]),
            "completion": int(row[2]),
            "total": int(row[3]),
            "requests": int(row[4]),
        }
        for row in day_rows
    ]
    by_model = [
        {"model": row[0] or "", "provider": row[1] or "", "tokens": int(row[2]), "requests": int(row[3])}
        for row in model_rows
    ]
    by_model.sort(key=lambda item: item["tokens"], reverse=True)
    total_rows = db.execute(
        select(func.count(), func.coalesce(func.sum(AIUsage.total_tokens), 0)).where(
            AIUsage.created_at >= since
        )
    ).one()
    return {
        "today": ai_gateway.usage_today(db),
        "days": by_day,
        "models": by_model,
        "total_requests": int(total_rows[0]),
        "total_tokens": int(total_rows[1]),
    }

def system_info(db: Session) -> dict[str, Any]:
    counts_row = db.execute(
        select(
            select(func.count()).select_from(Citizen).where(Citizen.archived_at.is_(None)).scalar_subquery(),
            select(func.count()).select_from(Family).scalar_subquery(),
            select(func.count()).select_from(House).scalar_subquery(),
            select(func.count()).select_from(Street).scalar_subquery(),
            select(func.count()).select_from(Case).scalar_subquery(),
            select(func.count()).select_from(Task).scalar_subquery(),
            select(func.count()).select_from(WorkLog).scalar_subquery(),
            select(func.count()).select_from(Document).scalar_subquery(),
            select(func.count()).select_from(Report).scalar_subquery(),
            select(func.count()).select_from(Program).scalar_subquery(),
            select(func.count()).select_from(User).scalar_subquery(),
        )
    ).one()
    counts = {
        "citizens": int(counts_row[0]),
        "families": int(counts_row[1]),
        "houses": int(counts_row[2]),
        "streets": int(counts_row[3]),
        "cases": int(counts_row[4]),
        "tasks": int(counts_row[5]),
        "work_logs": int(counts_row[6]),
        "documents": int(counts_row[7]),
        "reports": int(counts_row[8]),
        "programs": int(counts_row[9]),
        "users": int(counts_row[10]),
    }
    return {
        "version": settings.app_version,
        "environment": settings.app_env,
        "timezone": settings.scheduler_timezone,
        "demo_mode": settings.demo_mode,
        "database": "postgresql",
        "storage": "postgres",
        "ai": {
            "default_provider": settings.ai_default_provider,
            "providers": ai_gateway.provider_status(),
            "budget": ai_gateway.usage_today(db),
        },
        "counts": counts,
        "features": {
            "legislation_live": True,
            "scheduler": True,
            "import_export": True,
            "pwa": True,
        },
        "timestamp": datetime.now(timezone.utc),
    }

def _iso(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value

@lru_cache(maxsize=1)
def _backup_data_column_exists() -> bool:
    from app.core.db import engine

    try:
        with engine.connect() as conn:
            dialect = conn.dialect.name
            if dialect == "postgresql":
                value = conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = 'backup_runs' AND column_name = 'data'"
                    )
                ).scalar()
            elif dialect == "sqlite":
                rows = conn.execute(text('PRAGMA table_info("backup_runs")')).all()
                value = any(str(row[1]) == "data" for row in rows)
            else:
                value = False
    except Exception:
        value = False
    return bool(value)

def create_backup(db: Session, actor: str) -> tuple[dict[str, Any], str]:
    import hashlib
    import io

    generated_at = datetime.now(timezone.utc).isoformat()
    buffer = io.BytesIO()
    digest = hashlib.sha256()
    counts: dict[str, int] = {}

    def _write(text: str) -> None:
        data = text.encode("utf-8")
        digest.update(data)
        buffer.write(data)

    def _stream(key: str, rows: Any, serializer: Any) -> None:
        if counts:
            _write(",")
        _write(json.dumps(key) + ": [")
        count = 0
        for row in rows:
            if count:
                _write(", ")
            _write(json.dumps(serializer(row), ensure_ascii=False, default=str))
            count += 1
        _write("]")
        counts[key] = count

    backup = BackupRun(kind="logical", status="running")
    db.add(backup)
    db.flush()

    _write("{")
    _write('"backup_id": ' + json.dumps(backup.id) + ",")
    _write('"generated_at": ' + json.dumps(generated_at) + ",")
    _write('"version": ' + json.dumps(settings.app_version) + ",")

    _stream(
        "citizens",
        db.execute(select(Citizen)).scalars(),
        lambda row: {
            "id": row.id,
            "full_name": row.full_name,
            "gender": row.gender,
            "birth_date": _iso(row.birth_date),
            "phone": row.phone,
            "family_id": row.family_id,
            "family_role": row.family_role,
            "education": row.education,
            "employment_status": row.employment_status,
            "profession": row.profession,
            "social_status": row.social_status,
            "needs": row.needs,
            "notes": row.notes,
            "data_source": row.data_source,
            "last_verified_at": _iso(row.last_verified_at),
            "archived_at": _iso(row.archived_at),
            "created_at": _iso(row.created_at),
        },
    )
    _stream(
        "families",
        db.execute(select(Family)).scalars(),
        lambda row: {
            "id": row.id,
            "house_id": row.house_id,
            "family_type": row.family_type,
            "social_status": row.social_status,
            "family_head_citizen_id": row.family_head_citizen_id,
            "notes": row.notes,
            "created_at": _iso(row.created_at),
        },
    )
    _stream(
        "houses",
        db.execute(select(House)).scalars(),
        lambda row: {
            "id": row.id,
            "street_id": row.street_id,
            "house_number": row.house_number,
            "address_label": row.address_label,
        },
    )
    _stream(
        "streets",
        db.execute(select(Street)).scalars(),
        lambda row: {"id": row.id, "mahalla_id": row.mahalla_id, "name": row.name},
    )
    _stream(
        "mahallas",
        db.execute(select(Mahalla)).scalars(),
        lambda row: {
            "id": row.id,
            "name": row.name,
            "district": row.district,
            "region": row.region,
        },
    )
    _stream(
        "cases",
        db.execute(select(Case)).scalars(),
        lambda row: {
            "id": row.id,
            "citizen_id": row.citizen_id,
            "family_id": row.family_id,
            "category": row.category,
            "title": row.title,
            "description": row.description,
            "status": row.status,
            "priority": row.priority,
            "responsible_user": row.responsible_user,
            "target_date": _iso(row.target_date),
            "opened_at": _iso(row.opened_at),
            "closed_at": _iso(row.closed_at),
            "outcome": row.outcome,
            "evidence_refs": row.evidence_refs,
        },
    )
    _stream(
        "tasks",
        db.execute(select(Task)).scalars(),
        lambda row: {
            "id": row.id,
            "title": row.title,
            "description": row.description,
            "status": row.status,
            "priority": row.priority,
            "category": row.category,
            "due_date": _iso(row.due_date),
            "citizen_id": row.citizen_id,
            "family_id": row.family_id,
            "case_id": row.case_id,
            "assignee": row.assignee,
            "evidence_note": row.evidence_note,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
        },
    )
    _stream(
        "work_logs",
        db.execute(select(WorkLog)).scalars(),
        lambda row: {
            "id": row.id,
            "citizen_id": row.citizen_id,
            "case_id": row.case_id,
            "task_id": row.task_id,
            "type": row.type,
            "title": row.title,
            "description": row.description,
            "author_id": row.author_id,
            "occurred_at": _iso(row.occurred_at),
            "source": row.source,
            "approval_status": row.approval_status,
        },
    )
    _stream(
        "reports",
        db.execute(select(Report)).scalars(),
        lambda row: {
            "id": row.id,
            "type": row.type,
            "title": row.title,
            "status": row.status,
            "period_start": _iso(row.period_start),
            "period_end": _iso(row.period_end),
            "filters": row.filters,
            "metrics": row.metrics,
            "narrative": row.narrative,
            "summary": row.summary,
        },
    )
    _stream(
        "documents",
        db.execute(select(Document)).scalars(),
        lambda row: {
            "id": row.id,
            "filename": row.filename,
            "original_name": row.original_name,
            "mime_type": row.mime_type,
            "size": row.size,
            "content_hash": row.content_hash,
            "kind": row.kind,
            "status": row.status,
            "uploaded_by": row.uploaded_by,
            "meta": row.meta,
            "created_at": _iso(row.created_at),
        },
    )
    _stream(
        "users",
        db.execute(select(User)).scalars(),
        lambda row: {
            "id": row.id,
            "username": row.username,
            "display_name": row.display_name,
            "password_hash": row.password_hash,
            "role": row.role,
            "permissions": row.permissions,
            "is_active": row.is_active,
            "created_at": _iso(row.created_at),
            "last_login_at": _iso(row.last_login_at),
        },
    )
    _stream(
        "audit_logs",
        db.execute(select(AuditLog)).scalars(),
        lambda row: {
            "id": row.id,
            "actor_type": row.actor_type,
            "actor_id": row.actor_id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "old_value": row.old_value,
            "new_value": row.new_value,
            "request_id": row.request_id,
            "workflow_id": row.workflow_id,
            "source": row.source,
            "result": row.result,
            "created_at": _iso(row.created_at),
        },
    )
    _stream(
        "memory_items",
        db.execute(select(MemoryItem)).scalars(),
        lambda row: {
            "id": row.id,
            "conversation_id": row.conversation_id,
            "kind": row.kind,
            "key": row.key,
            "value": row.value,
            "source": row.source,
            "confidence": row.confidence,
            "created_at": _iso(row.created_at),
            "expires_at": _iso(row.expires_at),
        },
    )
    _write("}")

    raw = buffer.getbuffer()
    size_bytes = raw.nbytes
    sha256 = digest.hexdigest()
    if _backup_data_column_exists():
        backup.data = raw
        backup.location = f"db:backup_runs.data:sha256:{sha256}"
    else:
        backup.location = "inline:unmigrated"
    backup.status = "completed"
    backup.finished_at = datetime.now(timezone.utc)
    backup.size_bytes = size_bytes
    write_audit(
        db,
        action="backup.created",
        entity_type="backup_run",
        entity_id=backup.id,
        actor_id=actor,
        new_value={"size_bytes": size_bytes, "sha256": sha256, "counts": counts},
    )
    db.commit()
    db.refresh(backup)
    summary = {
        "backup_id": backup.id,
        "generated_at": generated_at,
        "counts": counts,
        "sha256": sha256,
        "size_bytes": size_bytes,
    }
    return summary, sha256

def list_backups(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    rows = db.execute(select(BackupRun).order_by(BackupRun.started_at.desc()).limit(limit)).scalars().all()
    return [
        {
            "id": row.id,
            "kind": row.kind,
            "status": row.status,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "size_bytes": row.size_bytes,
            "location": row.location,
            "error": row.error,
        }
        for row in rows
    ]
