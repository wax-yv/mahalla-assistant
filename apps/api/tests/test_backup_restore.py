"""Backup restore (G-band): zaxiradan tiklash — merge/replace va yaxlitlik.

- `merge`: bazada yo'q id'lar qo'shiladi, mavjudlariga tegilmaydi;
- `users` hech qachon ustidan yozilmaydi (parol himoyasi);
- sha256 buzilgan zaxira rad etiladi;
- FK tartibi saqlanadi.
"""

from __future__ import annotations

import pytest
from app.core.db import SessionLocal
from app.models import AuditLog, BackupRun, Citizen, User
from sqlalchemy import delete, select

MARKER = "RSTsinov"


def _cleanup() -> None:
    with SessionLocal() as db:
        ids = db.execute(
            select(Citizen.id).where(Citizen.full_name.like(f"{MARKER}%"))
        ).scalars().all()
        db.execute(delete(AuditLog).where(AuditLog.entity_id.in_(ids)))
        db.execute(delete(Citizen).where(Citizen.id.in_(ids)))
        backups = db.execute(
            select(BackupRun.id).where(BackupRun.location.like(f"%{MARKER}%"))
        ).scalars().all()
        db.execute(delete(BackupRun).where(BackupRun.id.in_(backups)))
        db.commit()


@pytest.fixture(autouse=True)
def clean():
    _cleanup()
    yield
    _cleanup()


def _make_backup_file(citizen_id: str, citizen_name: str) -> bytes:
    import json

    return json.dumps(
        {
            "backup_id": f"{MARKER}-b1",
            "generated_at": "2026-11-06T10:00:00+00:00",
            "version": "1.0.0",
            "mahallas": [],
            "streets": [],
            "houses": [],
            "families": [],
            "citizens": [
                {
                    "id": citizen_id,
                    "full_name": citizen_name,
                    "gender": "Erkak",
                    "birth_date": "1992-05-05",
                    "phone": "+998900000777",
                }
            ],
            "cases": [],
            "tasks": [],
            "work_logs": [],
            "reports": [],
            "documents": [],
            "users": [],
            "audit_logs": [],
            "memory_items": [],
        }
    ).encode("utf-8")


def _store_backup(data: bytes, sha: str) -> str:
    import hashlib

    with SessionLocal() as db:
        backup = BackupRun(kind="logical", status="completed")
        backup.data = data
        digest = hashlib.sha256(data).hexdigest()
        backup.location = f"db:backup_runs.data:sha256:{digest}"
        backup.size_bytes = len(data)
        db.add(backup)
        db.commit()
        assert sha
        return backup.id


def test_restore_merge_inserts_missing_citizen(clean):
    from app.services import admin as service

    citizen_id = f"{MARKER}-c1"
    data = _make_backup_file(citizen_id, f"{MARKER} fuqaro")
    backup_id = _store_backup(data, "sha")

    with SessionLocal() as db:
        result = service.restore_backup(db, backup_id, "tester", None, mode="merge")
        db.commit()

    assert result["results"]["citizens"]["inserted"] == 1
    with SessionLocal() as db:
        assert db.get(Citizen, citizen_id) is not None

    # Idempotent — qayta tiklashda skip bo'ladi.
    with SessionLocal() as db:
        result2 = service.restore_backup(db, backup_id, "tester", None, mode="merge")
    assert result2["results"]["citizens"]["inserted"] == 0
    assert result2["results"]["citizens"]["skipped"] == 1


def test_restore_never_overwrites_users(clean):
    """users — merge: mavjud admin paroli ustidan yozilmaydi."""
    from app.services import admin as service

    with SessionLocal() as db:
        admin = db.execute(select(User).where(User.role == "admin")).scalars().first()
        admin_id = admin.id
        admin_hash = admin.password_hash
        admin_username = admin.username

    import json

    payload = {
        "backup_id": f"{MARKER}-b2",
        "users": [
            {
                "id": admin_id,
                "username": admin_username,
                "display_name": "ustidan yozilishi kerak emas",
                "password_hash": "BU_PAROL_YOZILMASIN",
                "role": "admin",
                "is_active": True,
            }
        ],
        "mahallas": [], "streets": [], "houses": [], "families": [], "citizens": [],
        "cases": [], "tasks": [], "work_logs": [], "reports": [], "documents": [],
        "audit_logs": [], "memory_items": [],
    }
    data = json.dumps(payload).encode("utf-8")
    backup_id = _store_backup(data, "sha")

    with SessionLocal() as db:
        result = service.restore_backup(db, backup_id, "tester", None, mode="merge")

    assert result["results"]["users"]["inserted"] == 0
    with SessionLocal() as db:
        admin = db.get(User, admin_id)
        assert admin.password_hash == admin_hash, "admin paroli ustidan yozilgan!"


def test_restore_rejects_corrupted_backup(clean):
    """sha256 mos kelmasa — rad etiladi."""
    from app.core.errors import APIError
    from app.services import admin as service

    data = _make_backup_file(f"{MARKER}-c2", f"{MARKER} buzilgan")
    backup_id = _store_backup(data, "sha")

    with SessionLocal() as db:
        backup = db.get(BackupRun, backup_id)
        backup.location = "db:backup_runs.data:sha256:" + "0" * 64  # noto'g'ri xesh
        db.commit()

        with SessionLocal() as db2:
            with pytest.raises(APIError) as exc:
                service.restore_backup(db2, backup_id, "tester", None, mode="merge")
        assert exc.value.status_code == 400
