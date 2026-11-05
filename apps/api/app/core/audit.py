from __future__ import annotations

import re
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

_PII_NAME_KEYS = {
    "full_name",
    "fullname",
    "citizen_name",
    "f.i.sh",
    "fish",
    "fio",
    "ism_familiya",
}
_PII_PHONE_KEYS = {
    "phone",
    "phone_number",
    "mobile",
    "telefon",
    "telefon_raqami",
}
_PII_BIRTH_KEYS = {
    "birth_date",
    "birthdate",
    "dob",
    "tug'ilgan_sana",
    "tugilgan_sana",
}

_MAX_STRING = 4000

def _pii_kind(key: str) -> str | None:
    lowered = str(key).strip().lower()
    if lowered in _PII_NAME_KEYS or lowered.endswith("_full_name"):
        return "name"
    if lowered in _PII_PHONE_KEYS or lowered.endswith("_phone"):
        return "phone"
    if lowered in _PII_BIRTH_KEYS or lowered.endswith("_birth_date"):
        return "birth_date"
    return None

def _mask_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts = [part for part in re.split(r"\s+", text) if part]
    return " ".join(f"{part[0].upper()}." for part in parts[:4])

def _mask_phone(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    digit_positions = [index for index, char in enumerate(text) if char.isdigit()]
    if not digit_positions:
        return "[masked]"
    visible = set(digit_positions[-4:])
    return "".join(
        char if (index in visible or not char.isdigit()) else "*"
        for index, char in enumerate(text)
    )

def _mask_birth_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"(\d{4})", text)
    return match.group(1) if match else "[masked]"

def _mask_pii(value: Any, kind: str) -> str:
    if kind == "name":
        return _mask_name(value)
    if kind == "phone":
        return _mask_phone(value)
    return _mask_birth_date(value)

def sanitize(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "[…]"
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SECRET_MARKERS):
                result[str(key)] = "[redacted]"
                continue
            pii_kind = _pii_kind(str(key))
            if pii_kind is not None and item is not None:
                result[str(key)] = _mask_pii(item, pii_kind)
                continue
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
