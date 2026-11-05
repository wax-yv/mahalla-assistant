"""O-13: hisobot matni — JSON qirqilishi va raqamlar tekshirilishi.

Muammo:
- `json.dumps(metrics, indent=2)[:12000]` — JSON uzun bo'lsa **o'rtasidan**
  qirqilardi; model buzuq kirish olardi va tasdiqlangan metrikalarni
  tushunmasdi.
- LLM yozgan matndagi raqamlar `metrics` bilan solishtirilmasdi — model
  "1258 ta fuqaro" o'rniga "1300 ta fuqaro" yozsa, u "tasdiqlangan
  metrikalar" yorlig'i bilan saqlanardi.

To'g'rilash:
- zich (kompakt) JSON — chegarasiz valid JSON;
- hajm chegadan oshsa — deterministik xulosaga qaytariladi;
- matndagi har bir son metrikada mavjud bo'lishi tekshiriladi, aks holda
  `_fallback_narrative` ishlatiladi.
"""

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


# ------------------------------------------------------- JSON yaxshiligi


def test_metrics_payload_is_valid_json():
    """Prompt uchun yig'ilgan JSON parse qilinishi kerak (kesilmasligi)."""
    payload = service._metrics_payload(METRICS)
    assert payload is not None
    parsed = json.loads(payload)
    assert parsed["totals"]["citizens"] == 1258


def test_metrics_payload_is_compact():
    """JSON zich bo'lishi kerak (chegaradan ko'p joy egallamasligi)."""
    payload = service._metrics_payload(METRICS)
    assert payload is not None
    assert "\n" not in payload, "JSON pretty-print qilingan (joy behuda)"


def test_oversized_metrics_return_none():
    """Hajm chegarasidan oshsa — AI chaqirilmaydi (`None`)."""
    huge = {f"key_{index}": "x" * 200 for index in range(200)}
    assert service._metrics_payload(huge) is None


# ------------------------------------------------- raqamlar tekshiruvi


def test_numbers_in_metrics_are_collected():
    """Metrikadagi sonlar to'plamga yig'ilishi kerak."""
    numbers = service._metric_numbers(METRICS)
    assert 1258 in numbers
    assert 62.5 in numbers
    assert 2024 in numbers, "sana ichidagi yil topilmadi"


def test_unknown_number_is_detected():
    """Metrikada yo'q son aniqlanishi kerak."""
    assert service._has_unknown_number("Jami 1258 nafar fuqaro bor.", METRICS) is False
    assert service._has_unknown_number("Jami 9999 nafar fuqaro bor.", METRICS) is True


def test_percentage_matches_metric():
    """Foiz metrikadagi qiymat bilan mos bo'lishi kerak."""
    assert service._has_unknown_number("Bandlik darajasi 62.5 foiz.", METRICS) is False
    assert service._has_unknown_number("Bandlik darajasi 99 foiz.", METRICS) is True


def test_thousand_separator_is_normalised():
    """`1 258` va `1,258` metrikadagi 1258 bilan mos kelishi kerak."""
    assert service._has_unknown_number("Jami 1 258 nafar.", METRICS) is False
    assert service._has_unknown_number("Jami 1,258 nafar.", METRICS) is False


# --------------------------------------------------- generate_report


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
    """Model o'ylab topgan son — hisobotga yozilmasligi kerak."""
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
    """Metrikaga tayangan matn saqlanishi kerak."""
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
    """Tekshirilgan matn `metrics.ai.verified` bilan belgilanishi kerak."""
    from app.services import ai_gateway

    monkeypatch.setattr(
        ai_gateway,
        "chat_completion",
        lambda *args, **kwargs: _FakeAIResult("Jami 1258 nafar fuqaro."),
    )
    _report_id, _narrative, metrics = _generate()
    assert metrics["ai"]["verified"] is True


def test_report_marks_unverified_narrative(patched_metrics, clean_reports, monkeypatch):
    """Tekshirilmagan matn `metrics.ai.verified = False` bilan belgilanadi."""
    from app.services import ai_gateway

    monkeypatch.setattr(
        ai_gateway,
        "chat_completion",
        lambda *args, **kwargs: _FakeAIResult("Jami 9999 nafar fuqaro."),
    )
    _report_id, _narrative, metrics = _generate()
    assert metrics["ai"]["verified"] is False


def test_oversized_metrics_skip_ai(patched_metrics, clean_reports, monkeypatch):
    """Hajm chegarasidan oshsa — AI chaqirilmaydi."""
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
