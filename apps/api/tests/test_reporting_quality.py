"""K-9: hisobot agenti ma'lumot sifati ko'rsatkichini to'g'ri o'qishi.

Muammo: `reports.compute_metrics` kalitni `data_quality` deb yozadi,
`_reporting` esa `quality` kalitini o'qirdi -> har doim `{}` -> "Ma'lumot
sifati: 0 foiz; to'ldirilmagan: 0 ta" (doimiy yolg'on ko'rsatkich).
"""

from __future__ import annotations

from app.services import reports


def _period():
    from app.core.time import today_local

    today = today_local()
    return today, today


def test_compute_metrics_uses_data_quality_key():
    from app.core.db import SessionLocal

    start, end = _period()
    with SessionLocal() as db:
        metrics = reports.compute_metrics(db, "daily", start, end, {})

    assert "data_quality" in metrics
    assert "score" in metrics["data_quality"]
    assert "incomplete" in metrics["data_quality"]


def test_reporting_agent_reads_data_quality_key():
    """Agent matni haqiqiy ko'rsatkichni ko'rsatishi kerak (0 foiz emas)."""
    from app.core.db import SessionLocal
    from app.services.agents import _reporting

    start, end = _period()
    with SessionLocal() as db:
        metrics = reports.compute_metrics(db, "daily", start, end, {})
        result = _reporting(db, "Bugungi ko'rsatkichlar", {})

    quality = metrics["data_quality"]
    text = result["text"]
    assert f"Ma'lumot sifati: {quality['score']} foiz" in text
    assert f"to'ldirilmagan yozuvlar: {quality['incomplete']} ta" in text
    # Hisobot agenti hisob-kitob metrikasidan foydalanadi
    assert result["data"].get("metrics", {}).get("data_quality", {}).get(
        "score"
    ) == quality["score"]


def test_reporting_agent_does_not_use_wrong_key():
    """`quality` kaliti ishlatilmasligi kerak (source of truth — `data_quality`)."""
    import inspect

    from app.services import agents

    source = inspect.getsource(agents._reporting)
    assert 'metrics.get("data_quality"' in source
    assert 'metrics.get("quality"' not in source
