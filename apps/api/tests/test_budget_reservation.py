from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import AIUsage

AGENT = "test-j16"

def _cleanup() -> None:
    with SessionLocal() as db:
        db.execute(delete(AIUsage).where(AIUsage.agent == AGENT))
        db.commit()

@pytest.fixture(autouse=True)
def clean_usage():
    _cleanup()
    yield
    _cleanup()

def _used_tokens() -> int:
    with SessionLocal() as db:
        return int(
            db.execute(
                select(func.coalesce(func.sum(AIUsage.total_tokens), 0)).where(
                    AIUsage.agent == AGENT
                )
            ).scalar_one()
        )

def test_reservation_counts_toward_budget():
    from app.services import ai_gateway

    with SessionLocal() as db:
        before = ai_gateway.usage_today(db)["total_tokens"]

    reservation_id = ai_gateway._reserve_budget(agent=AGENT, estimate_tokens=1000)
    assert reservation_id is not None

    with SessionLocal() as db:
        after = ai_gateway.usage_today(db)["total_tokens"]
        row = db.get(AIUsage, reservation_id)
    assert after >= before + 1000
    assert row is not None
    assert row.status == "reserved"
    assert row.total_tokens == 1000

def test_settlement_releases_reservation():
    from app.services import ai_gateway

    reservation_id = ai_gateway._reserve_budget(agent=AGENT, estimate_tokens=500)
    assert reservation_id is not None
    ai_gateway._settle_reservation(reservation_id)

    with SessionLocal() as db:
        row = db.get(AIUsage, reservation_id)
    assert row.status == "settled"
    assert row.total_tokens == 0

def test_reservation_is_denied_when_budget_exhausted():
    from app.services import ai_gateway

    original = settings.ai_daily_token_budget
    try:
        settings.ai_daily_token_budget = 1000
        with SessionLocal() as db:
            db.execute(delete(AIUsage).where(AIUsage.agent == AGENT))
            db.commit()
        with SessionLocal() as db:
            db.add(
                AIUsage(
                    provider="-",
                    model="test",
                    agent=AGENT,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=900,
                    status="success",
                )
            )
            db.commit()
        reservation_id = ai_gateway._reserve_budget(agent=AGENT, estimate_tokens=500)
    finally:
        settings.ai_daily_token_budget = original
    assert reservation_id is None

def test_stale_reservations_are_expired():
    from datetime import datetime, timezone

    from app.services import ai_gateway

    reservation_id = ai_gateway._reserve_budget(agent=AGENT, estimate_tokens=300)
    assert reservation_id is not None

    with SessionLocal() as db:
        row = db.get(AIUsage, reservation_id)
        row.created_at = datetime.now(timezone.utc) - timedelta(
            minutes=ai_gateway.RESERVATION_TTL_MINUTES + 5
        )
        db.commit()

    next_id = ai_gateway._reserve_budget(agent=AGENT, estimate_tokens=300)
    assert next_id is not None

    with SessionLocal() as db:
        stale = db.get(AIUsage, reservation_id)
        fresh = db.get(AIUsage, next_id)
    assert stale.status == "expired"
    assert stale.total_tokens == 0
    assert fresh.status == "reserved"
