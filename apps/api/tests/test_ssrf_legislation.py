"""K-3: SSRF himoyasi — tashqi URL faqat ruxsat etilgan manzildan yuklanadi."""

from __future__ import annotations

import pytest

from app.core.errors import APIError
from app.core.urls import validate_lex_host, validate_lex_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8765/internal-admin",
        "http://127.0.0.1/docs/1",
        "https://evil.com/docs/1",
        "https://lex.uz.evil.com/docs/1",
        "https://lex.uz@evil.com/docs/1",
        "https://evil.com/lex.uz/docs/1",
        "https://lex.uz:8443/docs/1",
        "ftp://lex.uz/docs/1",
        "file:///etc/passwd",
    ],
)
def test_rejected_urls(url: str):
    with pytest.raises(APIError) as error:
        validate_lex_url(url)
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    "url",
    [
        "https://lex.uz/docs/123",
        "https://www.lex.uz/docs/123",
        "https://lex.uz/uz/docs/123",
        "https://lex.uz/ru/docs/5983",
        "https://lex.uz/oz/docs/1234",
    ],
)
def test_allowed_urls(url: str):
    assert validate_lex_url(url) == url


def test_non_document_path_is_rejected():
    with pytest.raises(APIError):
        validate_lex_url("https://lex.uz/uz/search/all?query=test")
    with pytest.raises(APIError):
        validate_lex_url("https://lex.uz/")


def test_host_validation_allows_other_lex_paths():
    assert validate_lex_host("https://lex.uz/uz/search/all?query=test")


def test_sync_request_schema_rejects_ssrf_url():
    from app.schemas import LegislationSyncRequest

    with pytest.raises(APIError) as error:
        LegislationSyncRequest(url="http://127.0.0.1:8765/internal-admin")
    assert error.value.status_code == 422


def test_sync_request_schema_accepts_lex_url():
    from app.schemas import LegislationSyncRequest

    request = LegislationSyncRequest(url="https://lex.uz/uz/docs/123")
    assert request.url == "https://lex.uz/uz/docs/123"


def test_fetch_document_validates_before_network(client, monkeypatch):
    """Tarmoqqa chiqishdan oldin manzil rad etilishi kerak."""
    from app.services import legislation as service

    called = {"hit": False}

    def _boom(*args, **kwargs):
        called["hit"] = True
        raise AssertionError("tarmoqqa chiqildi")

    monkeypatch.setattr(service, "_client", _boom)
    with pytest.raises(APIError):
        service.fetch_document("http://127.0.0.1:8765/internal-admin")
    assert called["hit"] is False


def test_sync_endpoint_rejects_ssrf_url(auth):
    api_client, token = auth
    response = api_client.post(
        "/api/v1/legislation/sync",
        headers={"X-CSRF-Token": token},
        json={"url": "http://127.0.0.1:8765/internal-admin"},
    )
    assert response.status_code in (401, 403, 422), response.text


def test_https_redirect_to_internal_is_blocked(auth, monkeypatch):
    """Redirect orqali ichki manzilga o'tishga urinish rad etilishi kerak."""
    import httpx

    from app.services import legislation as service

    api_client, token = auth

    def _fake_stream(*args, **kwargs):
        raise AssertionError("real tarmoqqa chiqildi")

    class _FakeResponse:
        status_code = 302
        headers = {"location": "http://127.0.0.1:8765/internal-admin"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _FakeClient:
        def stream(self, *args, **kwargs):
            return _FakeResponse()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(service, "_client", lambda *args, **kwargs: _FakeClient())
    with pytest.raises(APIError):
        service.fetch_document("https://lex.uz/uz/docs/123")
    assert httpx is not None
