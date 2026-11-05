"""O-1/O-2: `client_ip` ishonchli proksi va cookie `Secure` belgisi.

Muqova:
- O-1: `client_ip` X-Forwarded-For ning **birinchi** qiymatiga ishonardi —
  mijoz sarlavharni o'zi yozib rate limitni aylanib o'tishi mumkin edi.
  Endi `TRUSTED_PROXY_HOPS` sozlama bo'yicha XFF'ning o'ng tomonidan
  N-chi element olinadi; sozlama yo'q bo'lsa `request.client.host`.
- O-2: Session cookie `Secure` faqat `APP_ENV=production` bo'lsa qo'yilardi —
  `APP_ENV` xato yozilsa cookie HTTP orqali ketardi.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core import deps
from app.core.config import settings


def _request(headers: list[tuple[bytes, bytes]], client_host: str = "10.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (client_host, 1234),
        "scheme": "http",
        "server": ("testserver", 80),
        "query_string": b"",
    }
    return Request(scope)


def test_client_ip_without_forwarded_header_uses_client_host():
    request = _request([])
    assert deps.client_ip(request) == "10.0.0.1"


def test_client_ip_ignores_forwarded_when_no_trusted_proxy(monkeypatch):
    """Sozlama yo'q bo'lsa XFF butunlay e'tiborsiz qoldiriladi."""
    monkeypatch.setattr(settings, "trusted_proxy_hops", 0)
    request = _request([(b"x-forwarded-for", b"1.2.3.4")])
    assert deps.client_ip(request) == "10.0.0.1"


def test_client_ip_takes_nth_from_right(monkeypatch):
    """XFF'ning o'ng tomonidan N-chi element olinadi."""
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    request = _request([(b"x-forwarded-for", b"9.9.9.9, 8.8.8.8, 7.7.7.7")])
    # 1 ta ishonchli proksi -> o'ngdan 1-chi = "7.7.7.7"
    assert deps.client_ip(request) == "7.7.7.7"


def test_client_ip_with_two_trusted_hops(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    request = _request([(b"x-forwarded-for", b"9.9.9.9, 8.8.8.8, 7.7.7.7")])
    assert deps.client_ip(request) == "8.8.8.8"


def test_client_ip_truncates_long_value(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    request = _request([(b"x-forwarded-for", b"x" * 300)])
    assert len(deps.client_ip(request)) <= 64


def test_client_ip_falls_back_when_header_too_short(monkeypatch):
    """XFF da yetarli element yo'q bo'lsa — mijoz manzili ishlatiladi."""
    monkeypatch.setattr(settings, "trusted_proxy_hops", 3)
    request = _request([(b"x-forwarded-for", b"1.2.3.4")], client_host="10.0.0.9")
    assert deps.client_ip(request) == "10.0.0.9"


def test_cookie_secure_flag_true_for_https_request(monkeypatch):
    """`https` so'rovi bo'lsa cookie `Secure` bo'lishi kerak."""
    from app.routers import auth as auth_router

    monkeypatch.setattr(settings, "app_env", "development")
    request = _request([])
    request.scope["scheme"] = "https"
    assert auth_router._cookie_secure(request) is True


def test_cookie_secure_flag_true_in_production(monkeypatch):
    from app.routers import auth as auth_router

    monkeypatch.setattr(settings, "app_env", "production")
    request = _request([])
    request.scope["scheme"] = "http"
    assert auth_router._cookie_secure(request) is True


def test_cookie_secure_flag_false_for_local_http(monkeypatch):
    from app.routers import auth as auth_router

    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.delenv("VERCEL", raising=False)
    request = _request([])
    request.scope["scheme"] = "http"
    assert auth_router._cookie_secure(request) is False


def test_cookie_secure_flag_true_on_vercel(monkeypatch):
    """Vercel'da HTTP ham bo'lsa `Secure` qo'yilishi kerak."""
    from app.routers import auth as auth_router

    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setenv("VERCEL", "1")
    request = _request([])
    request.scope["scheme"] = "http"
    assert auth_router._cookie_secure(request) is True


@pytest.mark.parametrize("value", ["", "abc", "-1", "not-a-number", "99"])
def test_trusted_proxy_hops_validation_rejects_bad_values(value):
    """Sozlama qiymati 0..10 oralig'ida butun son bo'lishi kerak."""
    from app.core.config import Settings

    with pytest.raises(Exception):
        Settings(trusted_proxy_hops=value)


def test_trusted_proxy_hops_accepts_zero():
    """0 — ishonchli proksi yo'q (XFF butunlay e'tiborsiz)."""
    from app.core.config import Settings

    assert Settings(trusted_proxy_hops=0).trusted_proxy_hops == 0
