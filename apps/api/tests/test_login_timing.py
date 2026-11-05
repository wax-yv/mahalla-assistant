"""D-4: login vaqti username mavjudligini oshkor qilmasligi kerak.

Muammo (audit D-4): foydalanuvchi topilmasa argon2 `verify` chaqirilmasdi —
javob vaqti orqali "bu username bor" degan ma'lumot oqib chiqardi.
"""

from __future__ import annotations

import pytest

from app.core.db import SessionLocal
from app.core.security import dummy_password_hash, verify_password


class _FakeRequest:
    """`client_ip` va `request.state` uchun minimal so'rov obyekti."""

    def __init__(self, ip: str = "127.0.0.1"):
        self.client = type("Client", (), {"host": ip})()
        self.headers: dict[str, str] = {}
        self.state = type("State", (), {"request_id": "D4-sinov"})()


@pytest.fixture(autouse=True)
def _clean_rate_limits():
    from tests.conftest import clear_login_limit

    clear_login_limit()
    yield
    clear_login_limit()


def test_dummy_hash_is_a_valid_hash():
    """Soxta xesh haqiqiy xesh bo'lishi kerak (verify ishlaydi)."""
    value = dummy_password_hash()
    assert value.startswith("$argon2")
    assert verify_password(value, "mahalla-assistant-dummy-password") is True
    assert verify_password(value, "boshqa-parol") is False


def test_verify_runs_when_user_not_found(monkeypatch):
    """Foydalanuvchi topilmasa ham `verify_password` chaqiriladi."""
    from app.core.errors import APIError
    from app.services import auth as service

    calls: list[str] = []
    original = service.verify_password

    def _tracking(password_hash: str, password: str) -> bool:
        calls.append(password_hash)
        return original(password_hash, password)

    monkeypatch.setattr(service, "verify_password", _tracking)

    with SessionLocal() as db:
        with pytest.raises(APIError) as exc:
            service.authenticate(db, "d4-bunday-foydalanuvchi-yoq", "parol", _FakeRequest())

    assert exc.value.status_code == 401
    assert calls, "verify_password chaqirilmadi — vaqt orqali username oshkor bo'ladi"
    assert calls[0] == dummy_password_hash()


def test_verify_runs_for_existing_user(monkeypatch):
    """Mavjud foydalanuvchi uchun ham xesh tekshiruvi bajariladi."""
    from app.core.errors import APIError
    from app.services import auth as service

    calls: list[str] = []
    original = service.verify_password

    def _tracking(password_hash: str, password: str) -> bool:
        calls.append(password_hash)
        return original(password_hash, password)

    monkeypatch.setattr(service, "verify_password", _tracking)

    with SessionLocal() as db:
        with pytest.raises(APIError) as exc:
            service.authenticate(db, "wax", "not-the-password", _FakeRequest())

    assert exc.value.status_code == 401
    assert calls, "verify_password chaqirilmadi"
    assert calls[0] != dummy_password_hash()


def test_error_message_is_identical(client):
    """Xato matni foydalanuvchi yo'qligini oshkor qilmasligi kerak."""
    missing = client.post(
        "/api/v1/auth/login", json={"username": "d4-foydalanuvchi-yoq", "password": "parol"}
    )
    wrong = client.post(
        "/api/v1/auth/login", json={"username": "wax", "password": "not-the-password"}
    )
    assert missing.status_code == wrong.status_code == 401
    assert missing.json()["error"]["message"] == wrong.json()["error"]["message"]
