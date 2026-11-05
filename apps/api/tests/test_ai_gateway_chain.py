"""J-1/J-2/J-3: AI zanjiri — vaqt chegarasi, reasoning_content va token sarfi.

Muqova:
- J-1: 12 model × 55 s = 660 s (Vercel limiti 60 s) -> foydalanuvchi 504.
- J-2: `reasoning_content` javob sifatida qaytarilardi.
- J-3: token sarfi chaqiruvchining tranzaksiyasi bilan birga rollback bo'lardi
  -> kunlik byudjet nazorati ishlamasdi.
"""

from __future__ import annotations

import time

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import AIUsage


def _rows(agent: str = "test-j"):
    with SessionLocal() as db:
        return [
            (row.status, row.total_tokens)
            for row in db.execute(select(AIUsage).where(AIUsage.agent == agent)).scalars().all()
        ]


def _cleanup(agent: str = "test-j"):
    with SessionLocal() as db:
        db.execute(delete(AIUsage).where(AIUsage.agent == agent))
        db.commit()


@pytest.fixture(autouse=True)
def clean_usage():
    _cleanup()
    yield
    _cleanup()


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = "fake"

    def json(self):
        return self._payload


class _FakeClient:
    """Har chaqiruvda javobni qaytaradi va kechikishni simulyatsiya qiladi."""

    calls: list[float] = []
    responses: list = []

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, json=None):
        _FakeClient.calls.append(self.timeout)
        index = min(len(_FakeClient.calls) - 1, len(_FakeClient.responses) - 1)
        response = _FakeClient.responses[index]
        if isinstance(response, Exception):
            raise response
        if isinstance(response, float):
            time.sleep(response)
            response = _FakeClient.responses[min(index + 1, len(_FakeClient.responses) - 1)]
        return response


@pytest.fixture()
def fake_client(monkeypatch):
    _FakeClient.calls = []
    _FakeClient.responses = []
    monkeypatch.setattr(httpx, "Client", _FakeClient)
    return _FakeClient


def _ok(content: str = "Salom", tokens: int = 100) -> _FakeResponse:
    return _FakeResponse(
        {
            "model": "test-model",
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": tokens, "completion_tokens": tokens, "total_tokens": tokens * 2},
        }
    )


def test_chain_respects_attempt_limit(monkeypatch, fake_client):
    """J-1: modellarning soni cheklangan bo'lishi kerak."""
    from app.services import ai_gateway

    monkeypatch.setattr(ai_gateway, "available_models", lambda: [
        {"id": f"m{i}", "provider": "nvidia", "label": f"m{i}", "context": 1000, "free": True, "capabilities": ["chat"], "rank": i}
        for i in range(12)
    ])
    fake_client.responses = [_ok() for _ in range(12)]

    with SessionLocal() as db:
        result = ai_gateway.chat_completion(db, messages=[{"role": "user", "content": "salom"}], agent="test-j")

    assert result.content == "Salom"
    # 12 ta emas, faqat `ai_max_attempts` ta urinish
    assert len(fake_client.calls) <= settings.ai_max_attempts


def test_attempt_timeout_is_capped(monkeypatch, fake_client):
    """J-1: bitta urinishning timeout'i `ai_attempt_timeout_seconds` dan oshmasligi kerak."""
    from app.services import ai_gateway

    monkeypatch.setattr(ai_gateway, "available_models", lambda: [
        {"id": "m1", "provider": "nvidia", "label": "m1", "context": 1000, "free": True, "capabilities": ["chat"], "rank": 1}
    ])
    fake_client.responses = [_ok()]

    with SessionLocal() as db:
        ai_gateway.chat_completion(db, messages=[{"role": "user", "content": "salom"}], agent="test-j")

    assert fake_client.calls[0] <= float(settings.ai_attempt_timeout_seconds)


def test_reasoning_content_is_not_used_as_answer(monkeypatch, fake_client):
    """J-2: modelning ichki mulohazasi javob bo'lib qaytarilmasligi kerak."""
    from app.core.errors import APIError
    from app.services import ai_gateway

    monkeypatch.setattr(ai_gateway, "available_models", lambda: [
        {"id": "m1", "provider": "nvidia", "label": "m1", "context": 1000, "free": True, "capabilities": ["chat"], "rank": 1}
    ])
    fake_client.responses = [
        _FakeResponse(
            {
                "model": "test-model",
                "choices": [{"message": {"content": "", "reasoning_content": "Ichki mulohaza..."}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        )
    ]

    with SessionLocal() as db:
        with pytest.raises(APIError):
            ai_gateway.chat_completion(
                db, messages=[{"role": "user", "content": "salom"}], agent="test-j"
            )


def test_json_mode_rejects_non_json(monkeypatch, fake_client):
    """J-2: JSONMode'da JSON bo'lmagan javob qabul qilinmasligi kerak."""
    from app.core.errors import APIError
    from app.services import ai_gateway

    monkeypatch.setattr(ai_gateway, "available_models", lambda: [
        {"id": "m1", "provider": "nvidia", "label": "m1", "context": 1000, "free": True, "capabilities": ["chat"], "rank": 1}
    ])
    fake_client.responses = [_ok("Bu JSON emas")]

    with SessionLocal() as db:
        with pytest.raises(APIError):
            ai_gateway.chat_completion(
                db,
                messages=[{"role": "user", "content": "salom"}],
                agent="test-j",
                json_mode=True,
            )


def test_usage_is_committed_in_separate_session(monkeypatch, fake_client):
    """J-3: sarf alohida sessiyada yoziladi — rollback'dan qat'i nazar."""
    from app.services import ai_gateway

    monkeypatch.setattr(ai_gateway, "available_models", lambda: [
        {"id": "m1", "provider": "nvidia", "label": "m1", "context": 1000, "free": True, "capabilities": ["chat"], "rank": 1}
    ])
    fake_client.responses = [_ok(tokens=100)]

    with SessionLocal() as db:
        result = ai_gateway.chat_completion(
            db, messages=[{"role": "user", "content": "salom"}], agent="test-j"
        )
        db.rollback()  # chaqiruvchi tranzaksiyasi bekor qilindi

    rows = _rows()
    assert rows, "token sarfi saqlanmadi"
    assert ("success", result.total_tokens) in rows


def test_failed_attempt_is_recorded(monkeypatch, fake_client):
    """J-3: muvaffaqiyatsiz urinish ham hisoblanishi kerak."""
    from app.core.errors import APIError
    from app.services import ai_gateway

    monkeypatch.setattr(ai_gateway, "available_models", lambda: [
        {"id": "m1", "provider": "nvidia", "label": "m1", "context": 1000, "free": True, "capabilities": ["chat"], "rank": 1}
    ])
    fake_client.responses = [_FakeResponse({"error": {"message": "boom"}}, status_code=500)]

    with SessionLocal() as db:
        with pytest.raises(APIError):
            ai_gateway.chat_completion(
                db, messages=[{"role": "user", "content": "salom"}], agent="test-j"
            )

    statuses = [status for status, _ in _rows()]
    assert "error" in statuses


def test_timeout_attempt_is_recorded(monkeypatch, fake_client):
    """J-3: timeout urinish `timeout` holati bilan yozilishi kerak."""
    from app.core.errors import APIError
    from app.services import ai_gateway

    monkeypatch.setattr(ai_gateway, "available_models", lambda: [
        {"id": "m1", "provider": "nvidia", "label": "m1", "context": 1000, "free": True, "capabilities": ["chat"], "rank": 1}
    ])
    fake_client.responses = [httpx.TimeoutException("timeout")]

    with SessionLocal() as db:
        with pytest.raises(APIError):
            ai_gateway.chat_completion(
                db, messages=[{"role": "user", "content": "salom"}], agent="test-j"
            )

    statuses = [status for status, _ in _rows()]
    assert "timeout" in statuses
