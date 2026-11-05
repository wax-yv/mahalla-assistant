from __future__ import annotations

import inspect

from app.services import agents


def test_smalltalk_system_forbids_fabricating_facts():
    system = agents.SMALLTALK_SYSTEM
    lowered = system.lower()
    assert "bilmayman" in lowered, "'bilmayman' qoidasi yo'q"
    assert "mahalla" in lowered
    assert "kredit" in lowered or "subsidiya" in lowered
    assert "qonun" in lowered or "qonunchilik" in lowered

def test_smalltalk_rule_mentions_only_system_data():
    lowered = agents.SMALLTALK_SYSTEM.lower()
    assert "tizim ma'lumot" in lowered or "faqat tizim" in lowered

def test_credit_agent_discloses_saved_preference():
    source = inspect.getsource(agents._credit_subsidy)
    assert "preference_saved" in source, "javobda saqlangan tanlov ko'rsatilmadi"

def test_credit_agent_says_preference_was_saved():
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        result = agents._credit_subsidy(
            db, "Xalq banki krediti shartlari qanday?", {}
        )

    text = result["text"]
    assert "eslab" in text.lower(), f"tanlov saqlangani aytilmadi: {text[-300:]}"
    assert "preference_saved" in result["data"], (
        "`data.preference_saved` maydoni yo'q"
    )
