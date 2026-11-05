from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import Report, User

GENERATOR = "o16-generator"
APPROVER = "o16-approver"
ADMIN = "o16-admin"
ADMIN_GRANTED = "o16-admin-granted"
PASSWORD = "test-pass-123"
REPORT_MARKER = "O16 sinov hisobati"

def _ensure_user(username: str, role: str, permissions: list[str]) -> str:
    from app.core.security import hash_password

    with SessionLocal() as db:
        user = db.execute(select(User).where(User.username == username)).scalars().first()
        if user is None:
            user = User(
                username=username,
                display_name=username,
                password_hash=hash_password(PASSWORD),
                role=role,
                permissions=permissions,
            )
            db.add(user)
        else:
            user.role = role
            user.permissions = permissions
            user.is_active = True
        db.flush()
        db.commit()
        return user.id

def _cleanup() -> None:
    with SessionLocal() as db:
        db.execute(delete(Report).where(Report.title.like(f"{REPORT_MARKER}%")))
        db.execute(
            delete(User).where(
                User.username.in_([GENERATOR, APPROVER, ADMIN, ADMIN_GRANTED])
            )
        )
        db.commit()

@pytest.fixture()
def users():
    _cleanup()
    ids = {
        "generator": _ensure_user(GENERATOR, "operator", ["reports.generate"]),
        "approver": _ensure_user(
            APPROVER, "operator", ["reports.generate", "reports.approve"]
        ),
        "admin": _ensure_user(ADMIN, "admin", []),
        "admin_granted": _ensure_user(ADMIN_GRANTED, "admin", ["reports.approve"]),
    }
    yield ids
    _cleanup()

def _make_report(created_by: str | None) -> str:
    with SessionLocal() as db:
        report = Report(
            type="daily",
            period_start=date(2024, 5, 1),
            period_end=date(2024, 5, 31),
            filters={},
            status="draft",
            title=f"{REPORT_MARKER} {created_by or 'anon'}",
            summary="",
            metrics={},
            narrative="",
            sources=[],
            created_by=created_by,
        )
        db.add(report)
        db.flush()
        report_id = report.id
        db.commit()
        return report_id

def _login(client, username: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]

def _approve(client, token: str, report_id: str):
    return client.post(
        f"/api/v1/reports/{report_id}/approve",
        headers={"X-CSRF-Token": token},
        json={"note": "Sinov izohi"},
    )

def test_approve_permission_is_registered():
    from app.core.constants import PERMISSIONS

    assert "reports.approve" in PERMISSIONS
    assert "reports.generate" in PERMISSIONS

def test_generator_cannot_approve_report(client, users):
    report_id = _make_report(users["approver"])
    token = _login(client, GENERATOR)
    response = _approve(client, token, report_id)
    assert response.status_code == 403, response.text

def test_approver_can_approve_other_report(client, users):
    report_id = _make_report(users["generator"])
    token = _login(client, APPROVER)
    response = _approve(client, token, report_id)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"

def test_author_cannot_approve_own_report(client, users):
    report_id = _make_report(users["approver"])
    token = _login(client, APPROVER)
    response = _approve(client, token, report_id)
    assert response.status_code == 403, response.text

    with SessionLocal() as db:
        report = db.get(Report, report_id)
        assert report.status == "draft", "hisobot tasdiqlangan bo'lib ketdi"

def test_admin_role_alone_does_not_grant_approve(client, users):
    report_id = _make_report(users["generator"])
    token = _login(client, ADMIN)
    response = _approve(client, token, report_id)
    assert response.status_code == 403, response.text

def test_admin_with_explicit_grant_can_approve(client, users):
    report_id = _make_report(users["generator"])
    token = _login(client, ADMIN_GRANTED)
    response = _approve(client, token, report_id)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"

def test_admin_with_explicit_grant_can_approve_own_report(client, users):
    report_id = _make_report(users["admin_granted"])
    token = _login(client, ADMIN_GRANTED)
    response = _approve(client, token, report_id)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"

def test_seeded_admin_has_approve_permission():
    from app.core.security import hash_password

    with SessionLocal() as db:
        admin = db.execute(
            select(User).where(User.username == "o16-seed-admin")
        ).scalars().first()
        if admin is None:
            admin = User(
                username="o16-seed-admin",
                display_name="Sinov admini",
                password_hash=hash_password(PASSWORD),
                role="admin",
                permissions=[],
            )
            db.add(admin)
            db.flush()
            db.commit()

    try:
        from app.services.auth import ensure_admin

        with SessionLocal() as db:
            user = ensure_admin(db)
            assert "reports.approve" in (user.permissions or []), (
                f"ruxsat yo'q: {user.permissions}"
            )
            db.commit()
    finally:
        with SessionLocal() as db:
            db.execute(delete(User).where(User.username == "o16-seed-admin"))
            db.commit()

def test_migration_script_grants_approve_to_admins():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    script = (root / "scripts" / "migrate.sql").read_text(encoding="utf-8")
    assert "reports.approve" in script, (
        "migrate.sql da reports.approve ruxsati berilmadi"
    )
