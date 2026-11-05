from __future__ import annotations

from app.core.config import settings
from app.main import docs_paths


def test_docs_paths_closed_in_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    paths = docs_paths()
    assert paths["docs_url"] is None
    assert paths["redoc_url"] is None
    assert paths["openapi_url"] is None

def test_docs_paths_open_outside_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    paths = docs_paths()
    assert paths["docs_url"] == "/api/docs"
    assert paths["redoc_url"] == "/api/redoc"
    assert paths["openapi_url"] == "/api/openapi.json"

def test_app_has_no_docs_url_in_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    paths = docs_paths()
    assert all(value is None for value in paths.values())
