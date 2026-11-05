"""K-2: login urinishlar limiti.

Muqova: muvaffaqiyatsiz urinishlar 401 qaytarilganda ham saqlanib qolishi,
muvaffaqiyatli login esa hisoblagichni tozalashi.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import RateLimit


@pytest.fixture(autouse=True)
def _clean_rate_limits():
    """Har testdan oldin va keyin login hisoblagichini tozalaydi."""
    from tests.conftest import clear_login_limit

    clear_login_limit()
    yield
    clear_login_limit()


def _rate_limit_rows() -> list[tuple[str, int]]:
    with SessionLocal() as db:
        return [
            (row.key, int(row.count))
            for row in db.execute(select(RateLimit)).scalars().all()
        ]


def test_failed_login_is_persisted_after_401(client):
    """401 qaytarilgandan keyin ham hisob yozilgan bo'lishi kerak."""
    response = client.post(
        "/api/v1/auth/login", json={"username": "wax", "password": "nope123"}
    )
    assert response.status_code == 401

    rows = _rate_limit_rows()
    assert rows, "muvaffaqiyatsiz urinish saqlanmadi"
    assert any(key.startswith("login:user:wax") and count == 1 for key, count in rows)
    assert any(key.startswith("login:ip:") and count == 1 for key, count in rows)


def test_ninth_failed_attempt_is_blocked(client):
    """8 ta muvaffaqiyatsiz urinishdan keyin 9-chisi 429 beradi."""
    for attempt in range(8):
        response = client.post(
            "/api/v1/auth/login", json={"username": "wax", "password": "wrong-pass"}
        )
        assert response.status_code == 401, f"{attempt + 1}-urinish: {response.text}"

    blocked = client.post(
        "/api/v1/auth/login", json={"username": "wax", "password": "wrong-pass"}
    )
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"


def test_successful_login_is_not_blocked_and_resets_counter(client):
    """Muvaffaqiyatli login 429 bermasin va hisobni tozalasin."""
    for _ in range(7):
        response = client.post(
            "/api/v1/auth/login", json={"username": "wax", "password": "nope123"}
        )
        assert response.status_code == 401

    ok = client.post(
        "/api/v1/auth/login", json={"username": "wax", "password": "waxs"}
    )
    assert ok.status_code == 200, ok.text

    # Hisoblagich tozalandi — keyingi urinish yana 401 (429 emas)
    after = client.post(
        "/api/v1/auth/login", json={"username": "wax", "password": "nope123"}
    )
    assert after.status_code == 401, after.text


def test_successful_logins_are_not_rate_limited(client):
    """8 ta ketma-ket muvaffaqiyatli login 429 bermasin."""
    for _ in range(8):
        response = client.post(
            "/api/v1/auth/login", json={"username": "wax", "password": "waxs"}
        )
        assert response.status_code == 200, response.text


def test_rate_limit_is_per_username(client):
    """Boshqa foydalanuvchi nomi bloklanmasin."""
    for _ in range(8):
        client.post(
            "/api/v1/auth/login", json={"username": "wax", "password": "wrong-pass"}
        )
    blocked = client.post(
        "/api/v1/auth/login", json={"username": "wax", "password": "wrong-pass"}
    )
    assert blocked.status_code == 429

    other = client.post(
        "/api/v1/auth/login", json={"username": "boshqa-foydalanuvchi", "password": "wrong"}
    )
    assert other.status_code == 401, other.text


def test_record_failure_commits_in_separate_session(client):
    """`record_failure` alohida sessiyada yozadi — rollback uni yo'q qilmaydi."""
    from app.services import auth as auth_service

    auth_service.record_failure("login:test:unit")
    with SessionLocal() as db:
        row = db.execute(
            select(RateLimit).where(RateLimit.key == "login:test:unit")
        ).scalars().first()
    assert row is not None
    assert row.count == 1

    with SessionLocal() as db:
        db.execute(delete(RateLimit).where(RateLimit.key == "login:test:unit"))
        db.commit()
