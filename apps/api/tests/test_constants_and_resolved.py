from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete

from app.core.constants import INTENTS, CASE_TRANSITIONS
from app.core.db import SessionLocal
from app.models import AuditLog, Case

MARKER = "N9sinov"

def test_intents_cover_all_intent_rules():
    from app.services.agents import INTENT_RULES

    for intent, _keywords in INTENT_RULES:
        assert intent in INTENTS, f"{intent} — INTENTS ro'yxatida yo'q"

def test_intents_cover_all_intent_agents():
    from app.services.agents import INTENT_AGENT

    for intent in INTENT_AGENT:
        assert intent in INTENTS, f"{intent} — INTENTS ro'yxatida yo'q"

def test_resolved_status_does_not_set_closed_at():
    from app.schemas import CaseUpdate
    from app.services import cases as service

    with SessionLocal() as db:
        case = Case(title=f"{MARKER} case", category="umumiy", status="open", priority="normal")
        db.add(case)
        db.commit()
        case_id = case.id
        version = case.version

    try:
        with SessionLocal() as db:
            case = db.get(Case, case_id)
            service.update_case(
                db, case_id, CaseUpdate(status="resolved", version=version), "tester", None
            )

        with SessionLocal() as db:
            case = db.get(Case, case_id)
            assert case.status == "resolved"
            assert case.closed_at is None, "`resolved` case yopilgan deb hisoblanmasligi kerak"

        with SessionLocal() as db:
            case = db.get(Case, case_id)
            service.update_case(
                db, case_id, CaseUpdate(status="closed", version=case.version), "tester", None
            )
        with SessionLocal() as db:
            case = db.get(Case, case_id)
            assert case.status == "closed"
            assert isinstance(case.closed_at, datetime)
    finally:
        with SessionLocal() as db:
            db.execute(delete(AuditLog).where(AuditLog.entity_id == case_id))
            db.execute(delete(Case).where(Case.id == case_id))
            db.commit()

def test_resolved_still_allows_reopening():
    assert "in_progress" in CASE_TRANSITIONS["resolved"]
