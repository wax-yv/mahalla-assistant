from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from app.core.audit import model_snapshot, sanitize, write_audit
from app.core.db import SessionLocal
from app.models import AuditLog, Citizen
from sqlalchemy import delete, select

TEST_USERNAME = "o14-kirish-sinovi"
TEST_CITIZEN_NAME = "O14 sinov fuqarosi Alisher"

def test_phone_is_masked_keeping_last_four():
    result = sanitize({"phone": "+998901234567"})
    masked = result["phone"]
    assert masked != "+998901234567", "telefon niqolanmadi"
    assert masked.endswith("4567"), f"oxirgi 4 raqam saqlanmadi: {masked}"
    assert "90123" not in masked, f"raqamlar ochiq qoldi: {masked}"

def test_birth_date_is_masked_keeping_year():
    result = sanitize({"birth_date": date(1990, 5, 15)})
    assert result["birth_date"] == "1990", result["birth_date"]

def test_birth_date_string_is_masked():
    result = sanitize({"birth_date": "1990-05-15"})
    assert result["birth_date"] == "1990", result["birth_date"]

def test_full_name_is_masked_to_initials():
    result = sanitize({"full_name": "Alisher Karimov"})
    masked = result["full_name"]
    assert masked != "Alisher Karimov", "ism niqolanmadi"
    assert "Alisher" not in masked, f"ism ochiq qoldi: {masked}"
    assert "Karimov" not in masked, f"familiya ochiq qoldi: {masked}"
    assert masked.startswith("A."), f"bosh harf noto'g'ri: {masked}"

def test_username_is_not_masked():
    result = sanitize({"username": "wax"})
    assert result["username"] == "wax"

def test_non_pii_fields_are_untouched():
    result = sanitize({"status": "open", "version": 3})
    assert result["status"] == "open"
    assert result["version"] == 3

@pytest.fixture()
def clean_audit_rows():
    def _cleanup():
        with SessionLocal() as db:
            rows = db.execute(
                select(AuditLog).where(AuditLog.action == "auth.login_failed")
            ).scalars().all()
            for row in rows:
                value = row.new_value or {}
                if isinstance(value, dict) and str(value.get("username", "")).startswith(
                    TEST_USERNAME
                ):
                    db.delete(row)
            db.commit()

    _cleanup()
    yield
    _cleanup()

def _make_citizen() -> str:
    with SessionLocal() as db:
        citizen = Citizen(
            full_name=TEST_CITIZEN_NAME,
            gender="Erkak",
            birth_date=date(1988, 3, 12),
            phone="+998901112233",
        )
        db.add(citizen)
        db.flush()
        citizen_id = citizen.id
        db.commit()
        return citizen_id

def _cleanup_citizen(citizen_id: str) -> None:
    with SessionLocal() as db:
        db.execute(delete(Citizen).where(Citizen.id == citizen_id))
        db.commit()

def test_write_audit_masks_pii_in_snapshot(clean_audit_rows):
    citizen_id = _make_citizen()
    try:
        with SessionLocal() as db:
            citizen = db.get(Citizen, citizen_id)
            write_audit(
                db,
                action="citizen.updated",
                entity_type="citizen",
                entity_id=citizen_id,
                actor_id="tester",
                old_value=model_snapshot(citizen),
                new_value=model_snapshot(citizen),
            )
            db.commit()

        with SessionLocal() as db:
            row = db.execute(
                select(AuditLog)
                .where(AuditLog.action == "citizen.updated")
                .where(AuditLog.entity_id == citizen_id)
                .order_by(AuditLog.created_at.desc())
                .limit(1)
            ).scalar_one()

        value = row.new_value or {}
        assert value["full_name"] != TEST_CITIZEN_NAME, "F.I.Sh. niqolanmadi"
        assert "Alisher" not in str(value["full_name"]), value["full_name"]
        assert value["phone"].endswith("2233"), f"telefon niqolanmadi: {value['phone']}"
        assert "90111" not in str(value["phone"]), value["phone"]
        assert value["birth_date"] == "1988", value["birth_date"]
    finally:
        _cleanup_citizen(citizen_id)

def test_model_snapshot_keeps_exact_values(clean_audit_rows):
    citizen_id = _make_citizen()
    try:
        with SessionLocal() as db:
            citizen = db.get(Citizen, citizen_id)
            snapshot = model_snapshot(citizen)
        assert snapshot["full_name"] == TEST_CITIZEN_NAME
        assert snapshot["phone"] == "+998901112233"
        assert str(snapshot["birth_date"]) == "1988-03-12", (
            "tug'ilgan sana niqolandi (rollback ma'lumotni buzadi)"
        )
    finally:
        _cleanup_citizen(citizen_id)

@pytest.fixture(autouse=True)
def _clean_login_limits(monkeypatch):
    from app.services import auth as auth_service

    fixed_window = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(auth_service, "_window_start", lambda minutes: fixed_window)

    from tests.conftest import clear_login_limit

    clear_login_limit()
    yield
    clear_login_limit()

def _failure_audits() -> list[AuditLog]:
    with SessionLocal() as db:
        rows = db.execute(
            select(AuditLog).where(AuditLog.action == "auth.login_failed")
        ).scalars().all()
        return [
            row
            for row in rows
            if isinstance(row.new_value, dict)
            and str(row.new_value.get("username", "")).startswith(TEST_USERNAME)
        ]

def test_failed_login_is_audited(client, clean_audit_rows):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USERNAME, "password": "noto'g'ri-parol"},
    )
    assert response.status_code == 401, response.text

    rows = _failure_audits()
    assert rows, "muvaffaqiyatsiz login audit qilinmadi"
    assert rows[-1].result == "failure"

def test_failed_login_audit_survives_rollback(client, clean_audit_rows):
    client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USERNAME, "password": "noto'g'ri-parol"},
    )
    rows = _failure_audits()
    assert rows, "audit yozuvi saqlanmadi"
    assert rows[-1].created_at is not None

def test_failed_login_audit_records_username_and_reason(client, clean_audit_rows):
    client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USERNAME, "password": "noto'g'ri-parol"},
    )
    rows = _failure_audits()
    assert rows, "audit yozuvi topilmadi"
    value = rows[-1].new_value or {}
    assert value.get("username") == TEST_USERNAME, value
    assert value.get("reason") == "invalid_credentials", value
    assert rows[-1].actor_type == "anonymous"
    assert rows[-1].ip, "IP manzili yozilmadi"

def test_failed_login_audit_never_stores_password(client, clean_audit_rows):
    client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USERNAME, "password": "JUMBO-PAROL-123"},
    )
    rows = _failure_audits()
    assert rows, "audit yozuvi topilmadi"
    assert "JUMBO-PAROL-123" not in str(rows[-1].new_value)
    assert "JUMBO-PAROL-123" not in str(rows[-1].old_value)

def test_blocked_login_is_audited(client, clean_audit_rows):
    for _ in range(8):
        response = client.post(
            "/api/v1/auth/login",
            json={"username": TEST_USERNAME, "password": "noto'g'ri-parol"},
        )
        assert response.status_code == 401, response.text

    blocked = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USERNAME, "password": "noto'g'ri-parol"},
    )
    assert blocked.status_code == 429, blocked.text

    rows = _failure_audits()
    assert rows, "bloklangan urinish audit qilinmadi"
    reasons = [str((row.new_value or {}).get("reason")) for row in rows]
    assert "rate_limited" in reasons, reasons

def test_successful_login_audit_is_unchanged(client, clean_audit_rows):
    response = client.post(
        "/api/v1/auth/login", json={"username": "wax", "password": "waxs"}
    )
    assert response.status_code == 200, response.text

    with SessionLocal() as db:
        row = db.execute(
            select(AuditLog)
            .where(AuditLog.action == "auth.login")
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        ).scalar_one()
    assert row.result == "success"
    assert (row.new_value or {}).get("username") == "wax"
