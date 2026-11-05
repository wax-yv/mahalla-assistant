from __future__ import annotations

import pytest

from app.core.errors import APIError

def test_setup_status_returns_only_setup_required(client):
    response = client.get("/api/v1/setup/status")
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data.keys()) == {"setup_required"}
    assert isinstance(data["setup_required"], bool)

class _BrokenDB:
    def execute(self, *args, **kwargs):
        raise RuntimeError("connection to db.internal:5432 failed (secret password)")

    def rollback(self):
        return None

def test_setup_status_does_not_leak_database_error(client, monkeypatch):
    from app.core.db import get_db
    from app.main import app

    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: _BrokenDB())
    try:
        response = client.get("/api/v1/setup/status")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, response.text
    assert response.json() == {"setup_required": True}
    assert "secret" not in response.text
    assert "detail" not in response.json()
    assert "database" not in response.json()

def test_health_does_not_expose_environment_or_demo_mode(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200, response.text
    data = response.json()
    assert "environment" not in data
    assert "demo_mode" not in data
    assert "status" in data

def test_ready_does_not_expose_environment_or_demo_mode(client):
    response = client.get("/api/v1/ready")
    assert response.status_code == 200, response.text
    data = response.json()
    assert "environment" not in data
    assert "demo_mode" not in data

class _ScalarResult:
    def __init__(self, value: int):
        self._value = value

    def scalar_one(self) -> int:
        return self._value

class _EmptyDB:
    def execute(self, *args, **kwargs):
        return _ScalarResult(0)

    def commit(self) -> None:
        return None

def test_production_setup_requires_token(monkeypatch):
    from app.routers import setup as setup_router

    class _FakeSettings:
        is_production = True
        setup_token = "unit-test-setup-token"

    monkeypatch.setattr(setup_router, "settings", _FakeSettings())

    with pytest.raises(APIError) as error:
        setup_router.setup(x_setup_token=None, db=_EmptyDB())
    assert error.value.status_code == 403

def test_development_first_setup_still_allowed(monkeypatch):
    from app.routers import setup as setup_router

    class _FakeSettings:
        is_production = False
        setup_token = "change-me"

    monkeypatch.setattr(setup_router, "settings", _FakeSettings())

    called = {"seed": False}

    def _fake_seed_run() -> None:
        called["seed"] = True

    import app.seed as seed_module

    monkeypatch.setattr(seed_module, "run", _fake_seed_run)

    result = setup_router.setup(x_setup_token=None, db=_EmptyDB())
    assert result["ok"] is True
    assert called["seed"] is True
