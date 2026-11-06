"""F-band: qimmat endpointlarga rate limit (AI chat, Lex.uz so'rovi).

Muammo (audit F): faqat login endpointida rate limit bor edi — AI chat
va Lex.uz so'rovlari cheklanmasdi (token sarfi va tashqi tarmoq suiiste'moli).
"""

from __future__ import annotations

import pytest
from app.core.db import SessionLocal
from app.models import RateLimit


@pytest.fixture(autouse=True)
def _clean_rate_limits():
    with SessionLocal() as db:
        db.query(RateLimit).filter(RateLimit.key.like("chat:user:%")).delete(synchronize_session=False)
        db.query(RateLimit).filter(RateLimit.key.like("lex:user:%")).delete(synchronize_session=False)
        db.commit()
    yield
    with SessionLocal() as db:
        db.query(RateLimit).filter(RateLimit.key.like("chat:user:%")).delete(synchronize_session=False)
        db.query(RateLimit).filter(RateLimit.key.like("lex:user:%")).delete(synchronize_session=False)
        db.commit()


def test_chat_rate_limit_blocks_after_limit(auth, monkeypatch):
    """30-so'rovdan keyin 429 qaytadi."""
    from app.services import agents as agents_service

    monkeypatch.setattr(
        agents_service, "chat",
        lambda db, **kwargs: {
            "text": "ok", "sources": [], "draft_actions": [], "data": {},
            "message": type("M", (), {"id": "m1", "conversation_id": "c1", "role": "assistant",
                                       "content": "ok", "agent": "o", "workflow_id": None,
                                       "sources": [], "created_at": None})(),
        },
    )
    client, token = auth
    headers = {"X-CSRF-Token": token}
    statuses = []
    for _ in range(32):
        response = client.post(
            "/api/v1/agents/chat", headers=headers, json={"message": "salom"}
        )
        statuses.append(response.status_code)
    assert 429 in statuses, statuses[-5:]
    assert statuses.count(200) >= 25


def test_chat_message_length_capped(auth):
    """4000 belgidan uzun xabar — 422."""
    client, token = auth
    response = client.post(
        "/api/v1/agents/chat",
        headers={"X-CSRF-Token": token},
        json={"message": "a" * 5000},
    )
    assert response.status_code == 422
