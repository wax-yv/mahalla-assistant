from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest
from sqlalchemy import delete, event, select

from app.core.db import SessionLocal, engine
from app.models import Citizen, Conversation, ConversationMessage, Family, House, Mahalla, Street

MARKER = "N1sinov"

@contextmanager
def count_queries():
    statements: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

def _cleanup() -> None:
    with SessionLocal() as db:
        street_ids = db.execute(select(Street.id).where(Street.name.like(f"{MARKER}%"))).scalars().all()
        mahalla_ids = db.execute(select(Mahalla.id).where(Mahalla.name.like(f"{MARKER}%"))).scalars().all()
        citizen_ids = db.execute(select(Citizen.id).where(Citizen.full_name.like(f"{MARKER}%"))).scalars().all()
        conversation_ids = db.execute(
            select(Conversation.id).where(Conversation.title.like(f"{MARKER}%"))
        ).scalars().all()
        db.execute(delete(ConversationMessage).where(ConversationMessage.conversation_id.in_(conversation_ids)))
        db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))
        db.execute(delete(Citizen).where(Citizen.id.in_(citizen_ids)))
        db.execute(
            delete(Family).where(
                Family.house_id.in_(select(House.id).where(House.street_id.in_(street_ids)))
            )
        )
        db.execute(delete(House).where(House.street_id.in_(street_ids)))
        db.execute(delete(Street).where(Street.id.in_(street_ids)))
        db.execute(delete(Mahalla).where(Mahalla.id.in_(mahalla_ids)))
        db.commit()

@pytest.fixture()
def dataset():
    _cleanup()
    with SessionLocal() as db:
        mahalla = Mahalla(name=f"{MARKER} mahalla", district="Test")
        db.add(mahalla)
        db.flush()
        for s in range(2):
            street = Street(mahalla_id=mahalla.id, name=f"{MARKER} ko'cha {s}")
            db.add(street)
            db.flush()
            for h in range(3):
                house = House(street_id=street.id, house_number=f"{MARKER}-{s}-{h}")
                db.add(house)
                db.flush()
                family = Family(house_id=house.id)
                db.add(family)
                db.flush()
                for c in range(2):
                    db.add(
                        Citizen(
                            family_id=family.id,
                            full_name=f"{MARKER} fuqaro {s}-{h}-{c}",
                            gender="Erkak",
                            birth_date=date(1990, 1, 1),
                            phone=f"+9989000000{s}{h}{c}",
                        )
                    )
        for index in range(5):
            conversation = Conversation(title=f"{MARKER} suhbat {index}")
            db.add(conversation)
            db.flush()
            for m in range(index + 1):
                db.add(
                    ConversationMessage(
                        conversation_id=conversation.id,
                        role="user",
                        content=f"{MARKER} xabar {m}",
                    )
                )
        db.commit()
    yield
    _cleanup()

def test_dashboard_summary_uses_few_queries(dataset):
    from app.services import dashboard as service

    with SessionLocal() as db, count_queries() as statements:
        service.summary(db)
    assert len(statements) <= 15, f"{len(statements)} so'rov bajarildi:\n" + "\n".join(
        statement[:120] for statement in statements
    )

def test_dashboard_summary_metrics_are_correct(dataset):
    from app.services import dashboard as service

    with SessionLocal() as db:
        payload = service.summary(db)
    metrics = {item["key"]: item["value"] for item in payload["metrics"]}
    with SessionLocal() as db:
        citizens = db.execute(
            select(Citizen.id).where(Citizen.full_name.like(f"{MARKER}%"))
        ).scalars().all()
    assert metrics["citizens"] >= len(citizens), metrics
    assert metrics["houses"] >= 6, metrics
    assert metrics["streets"] >= 2, metrics
    assert metrics["families"] >= 6, metrics
    quality = payload["data_quality"]
    assert quality["complete"] + quality["incomplete"] == metrics["citizens"], quality

def test_list_mahallas_uses_constant_queries(dataset):
    from app.services import hierarchy as service

    with SessionLocal() as db, count_queries() as statements:
        rows = service.list_mahallas(db)
    assert len(statements) <= 2, f"{len(statements)} so'rov:\n" + "\n".join(
        statement[:120] for statement in statements
    )
    target = next(row for row in rows if row["name"] == f"{MARKER} mahalla")
    assert target["street_count"] == 2, target
    assert target["house_count"] == 6, target
    assert target["family_count"] == 6, target
    assert target["citizen_count"] == 12, target

def test_list_streets_uses_constant_queries(dataset):
    from app.services import hierarchy as service

    with SessionLocal() as db, count_queries() as statements:
        rows = service.list_streets(db)
    assert len(statements) <= 2, f"{len(statements)} so'rov:\n" + "\n".join(
        statement[:120] for statement in statements
    )
    target = next(row for row in rows if row["name"].startswith(f"{MARKER} ko'cha"))
    assert target["house_count"] == 3, target
    assert target["family_count"] == 3, target
    assert target["citizen_count"] == 6, target

def test_list_houses_uses_constant_queries(dataset):
    from app.services import hierarchy as service

    with SessionLocal() as db:
        street_id = db.execute(
            select(Street.id).where(Street.name.like(f"{MARKER} ko'cha%")).order_by(Street.name)
        ).scalars().first()

    with SessionLocal() as db, count_queries() as statements:
        rows, _meta = service.list_houses(db, street_id=street_id, page_size=50)
    assert len(statements) <= 4, f"{len(statements)} so'rov:\n" + "\n".join(
        statement[:120] for statement in statements
    )
    target = next(row for row in rows if row["house_number"].startswith(MARKER))
    assert target["family_count"] == 1, target
    assert target["citizen_count"] == 2, target

def test_list_conversations_uses_constant_queries(dataset):
    from app.services import agents as service

    with SessionLocal() as db, count_queries() as statements:
        rows = service.list_conversations(db, limit=40, is_admin=True)
    assert len(statements) <= 2, f"{len(statements)} so'rov:\n" + "\n".join(
        statement[:120] for statement in statements
    )
    target = next(row for row in rows if row["title"] == f"{MARKER} suhbat 3")
    assert target["message_count"] == 4, target
    assert target["last_message"], target

def test_agent_status_uses_few_queries(dataset, monkeypatch):
    from app.services import ai_gateway, agents as service

    monkeypatch.setattr(ai_gateway, "provider_status", lambda live=True: [])

    with SessionLocal() as db, count_queries() as statements:
        payload = service.agent_status(db)
    assert len(statements) <= 6, f"{len(statements)} so'rov:\n" + "\n".join(
        statement[:120] for statement in statements
    )
    assert payload["agents"], payload
    assert all("tokens_today" in item for item in payload["agents"])
