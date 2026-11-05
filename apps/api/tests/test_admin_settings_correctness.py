from __future__ import annotations

import pytest
from sqlalchemy import delete

from app.core.db import SessionLocal
from app.models import AppSetting, AuditLog

@pytest.fixture()
def _settings():
    with SessionLocal() as db:
        row = db.get(AppSetting, "app")
        backup = dict(row.value or {}) if row is not None else None
    yield
    with SessionLocal() as db:
        row = db.get(AppSetting, "app")
        if row is not None and backup is not None:
            row.value = backup
            db.commit()
        db.execute(delete(AuditLog).where(AuditLog.action == "settings.updated"))
        db.commit()

def test_update_settings_allows_null(_settings):
    from app.services import admin as service

    with SessionLocal() as db:
        service.update_settings(db, {"mahalla": None}, "tester", None)
        value = db.get(AppSetting, "app").value
    assert value.get("mahalla") is None

def test_update_settings_stores_value(_settings):
    from app.services import admin as service

    with SessionLocal() as db:
        service.update_settings(db, {"mahalla": "Test mahalla"}, "tester", None)
        value = db.get(AppSetting, "app").value
    assert value.get("mahalla") == "Test mahalla"

def test_ai_budget_below_limit_is_rejected(_settings):
    from app.core.errors import APIError
    from app.services import admin as service

    with SessionLocal() as db:
        with pytest.raises(APIError) as exc:
            service.update_settings(db, {"ai_budget": 500}, "tester", None)
    assert exc.value.status_code == 422

    with SessionLocal() as db:
        row = db.get(AppSetting, "app")
        assert (row.value or {}).get("ai_budget") != 500

def test_ai_budget_valid_value_accepted(_settings):
    from app.services import admin as service

    with SessionLocal() as db:
        service.update_settings(db, {"ai_budget": 5000}, "tester", None)
        value = db.get(AppSetting, "app").value
    assert value.get("ai_budget") == 5000

def test_ai_budget_non_integer_rejected(_settings):
    from app.core.errors import APIError
    from app.services import admin as service

    with SessionLocal() as db:
        with pytest.raises(APIError):
            service.update_settings(db, {"ai_budget": "ko'p"}, "tester", None)

def test_usage_summary_is_sql_aggregated(_settings):
    from app.services import admin as service

    with SessionLocal() as db:
        summary = service.usage_summary(db, days=14)
    assert "days" in summary and "models" in summary
    assert isinstance(summary["days"], list)
    assert all({"date", "prompt", "completion", "total", "requests"} <= set(item) for item in summary["days"])
    assert summary["total_requests"] >= 0

def test_system_info_storage_is_postgres():
    from app.services import admin as service

    with SessionLocal() as db:
        info = service.system_info(db)
    assert info["storage"] == "postgres"
    assert info["counts"]["citizens"] >= 0
