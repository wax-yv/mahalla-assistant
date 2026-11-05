"""D-12: `provider_status(live=True)` so'rov ichida tarmoqqa chiqmasligi kerak.

Muammo (audit D-12): `agent_status` har chatda provayderlarga sinxron
HTTP so'rov yuborardi (2 provayder × 8 s timeout) — chat kechikardi.
O-9 bilan `/models` natijasi keshga yozilgan (muvaffaqiyat — 1 soat,
xato — 60 s). Bu test kesh ishlashini va ikkinchi chaqiruvda tarmoq
so'rovi yo'qligini tasdiqlaydi.
"""

from __future__ import annotations

import pytest

from app.services import ai_gateway


@pytest.fixture()
def _clean_cache():
    ai_gateway._provider_models_cache.clear()
    yield
    ai_gateway._provider_models_cache.clear()


class _FakeResponse:
    status_code = 200

    def json(self) -> dict:
        return {"data": [{"id": "test/model-1"}, {"id": "test/model-2"}]}


class _FakeClient:
    created = 0

    def __init__(self, *args, **kwargs):
        type(self).created += 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, *args, **kwargs):
        return _FakeResponse()


def test_provider_status_second_call_has_no_network(_clean_cache, monkeypatch):
    """Ikkinchi chaqiruv tarmoqqa chiqmasligi kerak (kesh ishlaydi)."""
    monkeypatch.setattr(ai_gateway.httpx, "Client", _FakeClient)
    _FakeClient.created = 0

    first = ai_gateway.provider_status(live=True)
    requests_after_first = _FakeClient.created
    second = ai_gateway.provider_status(live=True)

    assert requests_after_first <= 2, f"kutilmagan so'rovlar: {requests_after_first}"
    assert _FakeClient.created == requests_after_first, "ikkinchi chaqiruv tarmoqqa chiqdi"
    assert first == second


def test_error_cache_ttl_is_short(_clean_cache, monkeypatch):
    """Xatolik bilan tugagan tekshiruv 60 s keshlanadi (doimiy emas)."""
    assert ai_gateway.LIVE_MODELS_ERROR_TTL_SECONDS == 60
    assert ai_gateway.LIVE_MODELS_TTL_SECONDS >= 3600


def test_provider_status_without_keys_is_network_free(_clean_cache, monkeypatch):
    """API kaliti sozlanmagan bo'lsa — tarmoq so'rovi umuman yo'q."""
    monkeypatch.setattr(ai_gateway.settings, "nvidia_nim_api_key", "")
    monkeypatch.setattr(ai_gateway.settings, "openrouter_api_key", "")

    def _fail(*args, **kwargs):
        raise AssertionError("tarmoq so'rovi bo'lmasligi kerak")

    monkeypatch.setattr(ai_gateway.httpx, "Client", _fail)
    result = ai_gateway.provider_status(live=True)
    assert result, "provayderlar ro'yxati bo'sh emas"
    assert all(not item["configured"] for item in result)
