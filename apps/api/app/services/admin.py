from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.config import settings
from app.core.errors import validation_error
from app.core.pagination import PageMeta, paginate
from app.models import (
    AIUsage,
    AuditLog,
    BackupRun,
    Case,
    Citizen,
    Document,
    Family,
    House,
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
    defaults.update({key: val for key, val in value.items() if val is not None})
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
            updates["ai_budget"] = max(1000, int(updates["ai_budget"]))
        except (TypeError, ValueError) as error:
            raise validation_error("AI budjeti butun son bo'lishi kerak.") from error
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
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(AuditLog.action.ilike(term), AuditLog.entity_id.ilike(term)))
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
    rows = db.execute(
        select(AIUsage).where(AIUsage.created_at >= since).order_by(AIUsage.created_at)
    ).scalars().all()
    by_day: dict[str, dict[str, int]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    for row in rows:
        day = row.created_at.date().isoformat()
        bucket = by_day.setdefault(day, {"prompt": 0, "completion": 0, "total": 0, "requests": 0})
        bucket["prompt"] += row.prompt_tokens
        bucket["completion"] += row.completion_tokens
        bucket["total"] += row.total_tokens
        bucket["requests"] += 1
        model = by_model.setdefault(
            row.model,
            {"model": row.model, "provider": row.provider, "tokens": 0, "requests": 0},
        )
        model["tokens"] += row.total_tokens
        model["requests"] += 1
    return {
        "today": ai_gateway.usage_today(db),
        "days": [{"date": day, **value} for day, value in sorted(by_day.items())],
        "models": sorted(by_model.values(), key=lambda item: item["tokens"], reverse=True),
        "total_requests": len(rows),
        "total_tokens": sum(row.total_tokens for row in rows),
    }


def system_info(db: Session) -> dict[str, Any]:
    counts = {
        "citizens": int(db.execute(select(func.count()).select_from(Citizen).where(Citizen.archived_at.is_(None))).scalar_one()),
        "families": int(db.execute(select(func.count()).select_from(Family)).scalar_one()),
        "houses": int(db.execute(select(func.count()).select_from(House)).scalar_one()),
        "streets": int(db.execute(select(func.count()).select_from(Street)).scalar_one()),
        "cases": int(db.execute(select(func.count()).select_from(Case)).scalar_one()),
        "tasks": int(db.execute(select(func.count()).select_from(Task)).scalar_one()),
        "work_logs": int(db.execute(select(func.count()).select_from(WorkLog)).scalar_one()),
        "documents": int(db.execute(select(func.count()).select_from(Document)).scalar_one()),
        "reports": int(db.execute(select(func.count()).select_from(Report)).scalar_one()),
        "programs": int(db.execute(select(func.count()).select_from(Program)).scalar_one()),
        "users": int(db.execute(select(func.count()).select_from(User)).scalar_one()),
    }
    return {
        "version": settings.app_version,
        "environment": settings.app_env,
        "timezone": settings.scheduler_timezone,
        "demo_mode": settings.demo_mode,
        "database": "postgresql",
        "storage": "vercel_blob" if settings.blob_read_write_token else "postgres",
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
            "pwa": False,
        },
        "timestamp": datetime.now(timezone.utc),
    }


def create_backup(db: Session, actor: str) -> tuple[dict[str, Any], str]:
    import hashlib

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": settings.app_version,
        "citizens": [],
        "families": [],
        "houses": [],
        "streets": [],
        "cases": [],
        "tasks": [],
        "work_logs": [],
        "reports": [],
    }
    for row in db.execute(select(Citizen)).scalars().all():
        payload["citizens"].append(
            {
                "id": row.id,
                "full_name": row.full_name,
                "gender": row.gender,
                "birth_date": row.birth_date.isoformat() if row.birth_date else None,
                "phone": row.phone,
                "family_id": row.family_id,
                "family_role": row.family_role,
                "employment_status": row.employment_status,
                "social_status": row.social_status,
                "needs": row.needs,
                "data_source": row.data_source,
                "last_verified_at": row.last_verified_at.isoformat() if row.last_verified_at else None,
            }
        )
    for row in db.execute(select(Family)).scalars().all():
        payload["families"].append(
            {
                "id": row.id,
                "house_id": row.house_id,
                "family_type": row.family_type,
                "social_status": row.social_status,
                "family_head_citizen_id": row.family_head_citizen_id,
            }
        )
    for row in db.execute(select(House)).scalars().all():
        payload["houses"].append(
            {"id": row.id, "street_id": row.street_id, "house_number": row.house_number, "address_label": row.address_label}
        )
    for row in db.execute(select(Street)).scalars().all():
        payload["streets"].append({"id": row.id, "mahalla_id": row.mahalla_id, "name": row.name})
    for row in db.execute(select(Case)).scalars().all():
        payload["cases"].append(
            {
                "id": row.id,
                "citizen_id": row.citizen_id,
                "category": row.category,
                "title": row.title,
                "status": row.status,
                "priority": row.priority,
                "opened_at": row.opened_at.isoformat(),
                "outcome": row.outcome,
            }
        )
    for row in db.execute(select(Task)).scalars().all():
        payload["tasks"].append(
            {
                "id": row.id,
                "title": row.title,
                "status": row.status,
                "priority": row.priority,
                "due_date": row.due_date.isoformat() if row.due_date else None,
                "citizen_id": row.citizen_id,
                "case_id": row.case_id,
            }
        )
    for row in db.execute(select(WorkLog)).scalars().all():
        payload["work_logs"].append(
            {
                "id": row.id,
                "citizen_id": row.citizen_id,
                "type": row.type,
                "title": row.title,
                "occurred_at": row.occurred_at.isoformat(),
            }
        )
    for row in db.execute(select(Report)).scalars().all():
        payload["reports"].append(
            {
                "id": row.id,
                "type": row.type,
                "title": row.title,
                "status": row.status,
                "period_start": row.period_start.isoformat(),
                "period_end": row.period_end.isoformat(),
                "metrics": row.metrics,
                "narrative": row.narrative,
            }
        )
    encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    backup = BackupRun(
        kind="logical",
        status="completed",
        finished_at=datetime.now(timezone.utc),
        size_bytes=len(encoded),
        location=f"inline:sha256:{digest}",
    )
    db.add(backup)
    write_audit(
        db,
        action="backup.created",
        entity_type="backup_run",
        entity_id=backup.id,
        actor_id=actor,
        new_value={"size_bytes": len(encoded), "sha256": digest},
    )
    db.commit()
    db.refresh(backup)
    payload["backup_id"] = backup.id
    payload["sha256"] = digest
    return payload, digest


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
