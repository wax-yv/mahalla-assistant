"""D-3: `X-Request-ID` validatsiyasi va 500 javobda CORS sarlavhalari.

Muammo (audit D-3):
- Mijoz bergan `X-Request-ID` tekshirilmasdan logga yozilardi — log
  inyeksiyasi va cheksiz uzunlik mumkin edi.
- `Exception` handler CORS middleware'sidan tashqarida ishlardi — 500
  javobda `Access-Control-Allow-Origin` sarlavhasi yo'q edi.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import install_middleware, request_id_for


class _FakeRequest:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


def test_valid_request_id_is_kept():
    """To'g'ri formatdagi ID qabul qilinadi."""
    request = _FakeRequest({"x-request-id": "req-12345678"})
    assert request_id_for(request) == "req-12345678"


def test_invalid_request_ids_are_replaced():
    """Noto'g'ri formatdagi IDlar server tomonda yangilanadi."""
    bad_values = [
        "short",                       # 8 belgidan kam
        "x" * 65,                      # 64 belgidan ko'p
        "req 123456",                  # bo'shliq
        "req\n1234567",                # yangi qator (log inyeksiyasi)
        "req<script>123",             # belgilar
        "req/1234567890",              # yo'l belgisi
    ]
    for value in bad_values:
        request = _FakeRequest({"x-request-id": value})
        generated = request_id_for(request)
        assert generated != value
        assert len(generated) == 32


def test_missing_request_id_is_generated():
    """ID berilmasa — yangisi yaratiladi."""
    generated = request_id_for(_FakeRequest({}))
    assert len(generated) == 32


def test_unhandled_error_response_has_cors_headers():
    """500 javob CORS sarlavhalari bilan qaytariladi."""
    application = FastAPI()
    install_middleware(application)

    @application.get("/__boom__")
    def boom():
        raise RuntimeError("sinov xatosi")

    origin = settings.cors_origins[0]
    client = TestClient(application, raise_server_exceptions=False)
    response = client.get("/__boom__", headers={"Origin": origin})
    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("x-request-id")
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


def test_invalid_request_id_header_is_replaced_in_response():
    """Xavfsiz bo'lmagan ID javob sarlavhasiga ko'chirilmaydi."""
    application = FastAPI()
    install_middleware(application)

    @application.get("/__ok__")
    def ok():
        return {"ok": True}

    client = TestClient(application)
    response = client.get("/__ok__", headers={"X-Request-ID": "bad id!"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] != "bad id!"
