"""D-2: productionda API hujjatlari (Swagger/ReDoc/OpenAPI) yopiladi.

Muammo (audit D-2): `/api/docs`, `/api/redoc`, `/api/openapi.json`
productionda ochiq qolgan — API ta'rifi xavfsizlik chegarasini kengaytiradi.
"""

from __future__ import annotations

from app.core.config import settings
from app.main import docs_paths


def test_docs_paths_closed_in_production(monkeypatch):
    """Productionda hujjat manzillari `None` bo'lishi kerak."""
    monkeypatch.setattr(settings, "app_env", "production")
    paths = docs_paths()
    assert paths["docs_url"] is None
    assert paths["redoc_url"] is None
    assert paths["openapi_url"] is None


def test_docs_paths_open_outside_production(monkeypatch):
    """Development/test muhitida hujjatlar ochiq qoladi."""
    monkeypatch.setattr(settings, "app_env", "development")
    paths = docs_paths()
    assert paths["docs_url"] == "/api/docs"
    assert paths["redoc_url"] == "/api/redoc"
    assert paths["openapi_url"] == "/api/openapi.json"


def test_app_has_no_docs_url_in_production(monkeypatch):
    """Ilova yaratilgan paytdagi holat ham tekshiriladi."""
    monkeypatch.setattr(settings, "app_env", "production")
    paths = docs_paths()
    assert all(value is None for value in paths.values())
