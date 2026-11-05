from __future__ import annotations

import json

import pytest

from app.core.db import SessionLocal
from app.schemas import ReportGenerateRequest
from app.services import reports as service

METRICS = {
    "period": {"start": "2024-05-01", "end": "2024-05-31"},
    "totals": {"citizens": 1258, "families": 285, "houses": 202, "streets": 12},
    "employment": {"employed": 640, "unemployed": 91, "employment_rate": 62.5},
    "tasks": {"total": 48, "completed": 31, "overdue": 5},
    "cases": {"total": 42, "open": 7},
    "data_quality": {"score": 78.0, "incomplete": 33, "complete": 1225, "updated_today": 12},
}

def test_metrics_payload_is_valid_json():
    payload = service._metrics_payload(METRICS)
    assert payload is not None
    parsed = json.loads(payload)
    assert parsed["totals"]["citizens"] == 1258

def test_metrics_payload_is_compact():
    payload = service._metrics_payload(METRICS)
    assert payload is not None
    assert "\n" not in payload, "JSON pretty-print qilingan (joy behuda)"

def test_oversized_metrics_return_none():
    huge = {f"key_{index}": "x" * 200 for index in range(200)}
    assert service._metrics_payload(huge) is None

def test_numbers_in_metrics_are_collected():
    numbers = service._metric_numbers(METRICS)
    assert 1258 in numbers
    assert 62.5 in numbers
    assert 2024 in numbers, "sana ichidagi yil topilmadi"

def test_unknown_number_is_detected():
    assert service._has_unknown_number("Jami 1258 nafar fuqaro bor.", METRICS) is False
    assert service._has_unknown_number("Jami 9999 nafar fuqaro bor.", METRICS) is True

def test_percentage_matches_metric():
    assert service._has_unknown_number("Bandlik darajasi 62.5 foiz.", METRICS) is False
    assert service._has_unknown_number("Bandlik darajasi 99 foiz.", METRICS) is True

def test_thousand_separator_is_normalised():
    assert service._has_unknown_number("Jami 1 258 nafar.", METRICS) is False
    assert service._has_unknown_number("Jami 1,258 nafar.", METRICS) is False

class _FakeAIResult:
    def __init__(self, content: str):
        self.content = content
        self.model = "test-model"
        self.provider = "test-provider"
        self.total_tokens = 100
        self.prompt_tokens = 50
        self.completion_tokens = 50
        self.latency_ms = 5
        self.fallback_used = False
        self.attempts = []

@pytest.fixture()
def patched_metrics(monkeypatch):
    monkeypatch.setattr(service, "compute_metrics", lambda *args, **kwargs: METRICS)

@pytest.fixture()
def clean_reports():
    from sqlalchemy import delete, select

    from app.models import Report, ReportRun

    def _cleanup():
        with SessionLocal() as db:
            ids = db.execute(
                select(Report.id).where(Report.title.like("%O13 sinov%"))
            ).scalars().all()
            if ids:
                db.execute(delete(ReportRun).where(ReportRun.report_id.in_(ids)))
                db.execute(delete(Report).where(Report.id.in_(ids)))
            db.commit()

    _cleanup()
    yield
    _cleanup()

def _generate():
    with SessionLocal() as db:
        report = service.generate_report(
            db,
            ReportGenerateRequest(type="daily"),
            actor="tester",
            request_id=None,
        )
        return report.id, report.narrative, report.metrics

def test_fabricated_number_falls_back(patched_metrics, clean_reports, monkeypatch):
    from app.services import ai_gateway

    monkeypatch.setattr(
        ai_gateway,
        "chat_completion",
        lambda *args, **kwargs: _FakeAIResult(
            "Davriy hisobot: jami 9999 nafar fuqaro qayd etilgan."
        ),
    )
    _report_id, narrative, _metrics = _generate()
    assert "9999" not in narrative, f"uydirilgan son saqlandi: {narrative[:200]}"
    assert "1258" in narrative, "deterministik xulosa ishlatilmadi"

def test_valid_numbers_are_kept(patched_metrics, clean_reports, monkeypatch):
    from app.services import ai_gateway

    monkeypatch.setattr(
        ai_gateway,
        "chat_completion",
        lambda *args, **kwargs: _FakeAIResult(
            "Davriy hisobot: jami 1258 nafar fuqaro qayd etilgan, "
            "bandlik darajasi 62.5 foizni tashkil etdi."
        ),
    )
    _report_id, narrative, _metrics = _generate()
    assert "1258" in narrative
    assert "62.5" in narrative

def test_report_marks_verified_narrative(patched_metrics, clean_reports, monkeypatch):
    from app.services import ai_gateway

    monkeypatch.setattr(
        ai_gateway,
        "chat_completion",
        lambda *args, **kwargs: _FakeAIResult("Jami 1258 nafar fuqaro."),
    )
    _report_id, _narrative, metrics = _generate()
    assert metrics["ai"]["verified"] is True

def test_report_marks_unverified_narrative(patched_metrics, clean_reports, monkeypatch):
    from app.services import ai_gateway

    monkeypatch.setattr(
        ai_gateway,
        "chat_completion",
        lambda *args, **kwargs: _FakeAIResult("Jami 9999 nafar fuqaro."),
    )
    _report_id, _narrative, metrics = _generate()
    assert metrics["ai"]["verified"] is False

def test_oversized_metrics_skip_ai(patched_metrics, clean_reports, monkeypatch):
    from app.services import ai_gateway

    huge = {f"key_{index}": "x" * 200 for index in range(200)}
    monkeypatch.setattr(service, "compute_metrics", lambda *args, **kwargs: huge)
    called: list[bool] = []

    def _boom(*args, **kwargs):
        called.append(True)
        raise AssertionError("AI chaqirilmamligi kerak")

    monkeypatch.setattr(ai_gateway, "chat_completion", _boom)
    _report_id, narrative, metrics = _generate()
    assert not called, "AI chaqirildi"
    assert metrics["ai"]["provider"] == "local"
    assert narrative
