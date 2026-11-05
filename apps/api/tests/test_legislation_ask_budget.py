from __future__ import annotations

import time

import pytest
from app.services import legislation as service


def test_ask_does_not_sync_by_default(monkeypatch):
    calls: list[str] = []

    def _fail_sync(*args, **kwargs):
        calls.append("sync")
        raise AssertionError("so'rov yo'lida sinxron ishga tushmasligi kerak")

    monkeypatch.setattr(service, "sync_query", _fail_sync)
    monkeypatch.setattr(service, "search_chunks", lambda db, query, limit=6: [])

    result = service.ask(None, "test savol")

    assert not calls, "sinxron avtomatik ishga tushdi"
    assert result["sources"] == []
    assert "sinxron" in result["answer"].lower()

def test_router_default_is_no_auto_sync():
    from app.routers.legislation import LegislationQuestion

    assert LegislationQuestion(question="test").sync_if_empty is False

def test_explicit_sync_still_supported(monkeypatch):
    calls: list[str] = []

    def _fake_sync(db, query, limit=3, actor=None, budget_seconds=20):
        calls.append(query)
        return []

    monkeypatch.setattr(service, "sync_query", _fake_sync)
    monkeypatch.setattr(service, "search_chunks", lambda db, query, limit=6: [])

    service.ask(None, "ijara qoidalari", sync_if_empty=True)

    assert calls == ["ijara qoidalari"], f"sinxron chaqirilmadi: {calls}"

def test_sync_query_respects_time_budget(monkeypatch):
    calls: list[float] = []

    def _fake_ingest(db, url, *, actor=None, timeout=25):
        calls.append(timeout)
        time.sleep(0.3)
        raise RuntimeError("sinov uchun")

    monkeypatch.setattr(service, "ingest_document", _fake_ingest)
    monkeypatch.setattr(
        service,
        "search_lex",
        lambda query, limit=5, timeout=25: [
            {"url": f"https://lex.uz/docs/{index}", "title": f"hujjat {index}"}
            for index in range(5)
        ],
    )

    with pytest.raises(Exception):
        service.sync_query(
            None, "test", limit=5, actor="tester", budget_seconds=1.4
        )

    assert calls, "ingest_document umuman chaqirilmadi"
    assert len(calls) < 5, f"vaqt chegarasi qo'llanmadi: {len(calls)} ta chaqiruv"
    assert all(timeout <= 1.4 for timeout in calls), (
        f"chaqiruvlarga berilgan timeout chegaradan katta: {calls}"
    )

def test_budget_constant_is_20_seconds():
    assert service.SYNC_BUDGET_SECONDS == 20
