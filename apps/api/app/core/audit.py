from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog

_SECRET_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "cookie",
    "csrf",
)

_MAX_STRING = 4000


def sanitize(value: Any, depth: int = 0) -> Any:
    """Remove secrets and truncate long values before writing an audit record."""
    if depth > 6:
        return "[…]"
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SECRET_MARKERS):
                result[str(key)] = "[redacted]"
            else:
                result[str(key)] = sanitize(item, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize(item, depth + 1) for item in value[:200]]
    if isinstance(value, str):
        return value[:_MAX_STRING] + ("…" if len(value) > _MAX_STRING else "")
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:_MAX_STRING]


def model_snapshot(obj: Any, fields: list[str] | None = None) -> dict | None:
    if obj is None:
        return None
    if fields is None:
        fields = [column.name for column in obj.__table__.columns]
    data = {}
    for field in fields:
        if hasattr(obj, field):
            data[field] = sanitize(getattr(obj, field))
    return data


def write_audit(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None,
    actor_id: str | None = None,
    actor_type: str = "user",
    old_value: Any = None,
    new_value: Any = None,
    request_id: str | None = None,
    workflow_id: str | None = None,
    source: str = "api",
    ip: str | None = None,
    result: str = "success",
) -> AuditLog:
    entry = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        actor_type=actor_type,
        old_value=sanitize(old_value) if old_value is not None else None,
        new_value=sanitize(new_value) if new_value is not None else None,
        request_id=request_id,
        workflow_id=workflow_id,
        source=source,
        ip=ip,
        result=result,
    )
    db.add(entry)
    db.flush()
    return entry
