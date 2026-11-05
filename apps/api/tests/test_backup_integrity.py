"""J-8: zaxira nusxa — saqlanishi, sha256 va yuklab olishning to'g'riliği.

Muqova:
- `POST /admin/backups` butun baza RAM'da JSON qilardi va hech qayerda
  saqlanmasdi (`inline:sha256` — yolg'on signal).
- `GET /admin/backups/{id}/download` har safar **yangi** backup yaratib,
  o'sha yangi faylni qaytarardi — `sha256` boshqa nusxaga tegishli edi.
- Yuklab olishda `actor_id` "system" bo'lib qolardi.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import BackupRun


@pytest.fixture()
def clean_backups():
    def _cleanup():
        with SessionLocal() as db:
            db.execute(
                delete(BackupRun).where(BackupRun.kind == "unit-test")
            )
            db.commit()

    _cleanup()
    yield
    _cleanup()


def _create_backup(db, actor: str = "tester"):
    from app.services import admin

    return admin.create_backup(db, actor)


def test_backup_bytes_are_stored(clean_backups):
    """J-8: zaxira baytlari bazada saqlanishi kerak."""
    with SessionLocal() as db:
        summary, digest = _create_backup(db)
        backup_id = summary["backup_id"]

        backup = db.get(BackupRun, backup_id)
        assert backup is not None
        assert backup.data, "zaxira baytlari saqlanmadi"
        assert backup.size_bytes == len(bytes(backup.data))
        assert digest in backup.location

        # sha256 saqlangan baytlar bilan mos kelishi kerak.
        assert hashlib.sha256(bytes(backup.data)).hexdigest() == digest


def test_backup_contains_full_coverage(clean_backups):
    """Restore uchun asosiy jadvallar (fuqaro, mahalla, hujjat, foydalanuvchi...) kiritilishi kerak."""
    with SessionLocal() as db:
        summary, _ = _create_backup(db)
        backup = db.get(BackupRun, summary["backup_id"])
        assert backup is not None
        payload = json.loads(bytes(backup.data).decode("utf-8"))

    for key in (
        "citizens",
        "families",
        "houses",
        "streets",
        "mahallas",
        "cases",
        "tasks",
        "work_logs",
        "reports",
        "documents",
        "users",
        "audit_logs",
        "memory_items",
    ):
        assert key in payload, f"{key} zaxirada yo'q"
        assert isinstance(payload[key], list)

    if payload["citizens"]:
        citizen = payload["citizens"][0]
        # K-1 holatida kesilib qolgan maydonlar qaytarilishi kerak.
        assert "education" in citizen
        assert "profession" in citizen


def test_backup_is_valid_json(clean_backups):
    """Yozilgan fayl JSON formatida bo'lishi kerak (buzilgan bo'lishi mumkin emas)."""
    with SessionLocal() as db:
        summary, _ = _create_backup(db)
        backup = db.get(BackupRun, summary["backup_id"])
        assert backup is not None
        payload = json.loads(bytes(backup.data).decode("utf-8"))
    assert payload["backup_id"] == summary["backup_id"]
    assert payload["generated_at"] == summary["generated_at"]


def test_download_returns_stored_backup(auth):
    """Yuklab olish saqlangan faylni qaytarishi kerak (yangi backup yaratmasligi kerak)."""
    client, token = auth
    headers = {"X-CSRF-Token": token}

    created = client.post("/api/v1/admin/backups", headers=headers)
    assert created.status_code == 200, created.text
    backup_id = created.json()["backup_id"]
    sha256 = created.json()["sha256"]

    with SessionLocal() as db:
        before = db.execute(select(BackupRun)).scalars().all()
        count_before = len(before)

    download = client.get(f"/api/v1/admin/backups/{backup_id}/download")
    assert download.status_code == 200, download.text
    body = download.content
    assert hashlib.sha256(body).hexdigest() == sha256
    assert download.headers.get("x-backup-sha256") == sha256
    payload = json.loads(body.decode("utf-8"))
    assert payload["backup_id"] == backup_id

    # Yuklab olish yangi backup yaratmadi.
    with SessionLocal() as db:
        count_after = len(db.execute(select(BackupRun)).scalars().all())
    assert count_after == count_before

    with SessionLocal() as db:
        db.execute(delete(BackupRun).where(BackupRun.id == backup_id))
        db.commit()


def test_download_detects_tampered_backup(auth):
    """Baza'dagi baytlar buzilgan bo'lsa, yuklab olish rad etishi kerak."""
    client, token = auth
    headers = {"X-CSRF-Token": token}

    created = client.post("/api/v1/admin/backups", headers=headers)
    assert created.status_code == 200, created.text
    backup_id = created.json()["backup_id"]

    with SessionLocal() as db:
        backup = db.get(BackupRun, backup_id)
        assert backup is not None
        backup.data = b'{"tampered": true}'
        db.commit()

    download = client.get(f"/api/v1/admin/backups/{backup_id}/download")
    assert download.status_code == 400, download.text

    with SessionLocal() as db:
        db.execute(delete(BackupRun).where(BackupRun.id == backup_id))
        db.commit()


def test_download_unknown_backup_returns_404(auth):
    client, _ = auth
    response = client.get("/api/v1/admin/backups/BAK-nonexistent/download")
    assert response.status_code == 404, response.text


def test_backup_records_real_actor(auth):
    """Audit yozuvida haqiqiy foydalanuvchi ID bo'lishi kerak."""
    from app.models import AuditLog

    client, token = auth
    headers = {"X-CSRF-Token": token}
    created = client.post("/api/v1/admin/backups", headers=headers)
    assert created.status_code == 200, created.text
    backup_id = created.json()["backup_id"]

    with SessionLocal() as db:
        audit = db.execute(
            select(AuditLog).where(
                AuditLog.action == "backup.created",
                AuditLog.entity_id == backup_id,
            )
        ).scalars().first()
        assert audit is not None
        assert audit.actor_id and audit.actor_id != "system"
        db.execute(delete(BackupRun).where(BackupRun.id == backup_id))
        db.commit()
