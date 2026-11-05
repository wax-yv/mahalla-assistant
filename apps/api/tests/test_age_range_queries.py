"""Yosh oralig'i savollari — diapazon to'liq o'qiladi va chegaralar aniq.

Xato (foydalanuvchi hisoboti):
  * «6 yoshdan 10 yoshgacha bolalar» — javob «yosh: 10 gacha» (0–10),
    pastki chegara (6) YO'QOLGAN edi;
  * «0 yoshdan 10 yoshgacha?» — data_stats'ga yuborilmay, smalltalk'ga
    ketardi;
  * «10 yoshgacha» hisobida aynan 10 yoshli bolalar tushib qolardi
    (off-by-one: `birth > bugun-10y` yosh ≤ 9 ni beradi).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.core.db import SessionLocal
from app.core.time import minus_years
from app.models import AuditLog, Citizen

MARKER = "YoshSinov"


def _cleanup() -> None:
    with SessionLocal() as db:
        ids = db.execute(
            select(Citizen.id).where(Citizen.full_name.like(f"{MARKER}%"))
        ).scalars().all()
        db.execute(delete(AuditLog).where(AuditLog.entity_id.in_(ids)))
        db.execute(delete(Citizen).where(Citizen.id.in_(ids)))
        db.commit()


@pytest.fixture()
def clean():
    _cleanup()
    yield
    _cleanup()


# ---------------------------------------------------------------- parse


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("0 yoshdan 5 yoshgacha bo'lgan bolalar bor?", (0, 5)),
        ("6 yoshdan 10 yoshgacha nechta bola bor?", (6, 10)),
        ("0 yoshdan 10 yoshgacha?", (0, 10)),
        ("5 yoshdan 10yoshgacha bo'lgan nechta bola bor?", (5, 10)),
        ("6-10 yoshdagi bolalar", (6, 10)),
        ("6–10 yosh bolalar soni", (6, 10)),
        ("10 yoshgacha bolalar", (None, 10)),
        ("6 yoshdan katta bolalar", (6, None)),
        ("6 yoshdan kichik bolalar", (None, 5)),
        ("10 yoshli bolalar", (10, 10)),
        ("0 dan 10 gacha yosh bolalar", (0, 10)),
    ],
)
def test_age_range_parsing(message, expected):
    from app.services import data_query

    assert data_query._match_age(data_query.normalize(message)) == expected


# ---------------------------------------------------------------- routing


def test_age_range_question_routes_to_data_stats():
    """«0 yoshdan 10 yoshgacha?» — smalltalk'ga emas, statistikaga."""
    from app.services.agents import detect_intent

    intent, intents = detect_intent("0 yoshdan 10 yoshgacha?")
    assert intent == "data_stats", (intent, intents)


def test_exact_age_person_lookup_still_routes_to_lookup():
    """«10 yoshli Ali haqida ma'lumot ber» — fuqaro qidiruvi bo'lib qoladi."""
    from app.services.agents import detect_intent

    intent, _intents = detect_intent("10 yoshli Ali haqida malumot ber")
    assert intent == "citizen_lookup", intent


# ---------------------------------------------------------------- chegara


def _add_citizen(birth: date, phone_tail: str) -> None:
    with SessionLocal() as db:
        db.add(
            Citizen(
                full_name=f"{MARKER} bola {phone_tail}",
                gender="Erkak",
                birth_date=birth,
                phone=f"+9989000{phone_tail}",
            )
        )
        db.commit()


def test_upper_bound_includes_exact_age_children(clean):
    """«10 yoshgacha» — aynan 10 yoshli bola ham sanaladi (off-by-one)."""
    from app.services import data_query

    with SessionLocal() as db:
        baseline = data_query.build_answer(db, "10 yoshgacha bolalar nechta?").total

    today = date.today()
    # Bugun 10 yoshga to'ldi (birthday = bugun - 10 yil).
    _add_citizen(minus_years(today, 10), "101")
    # Ertaga 11 bo'ladi — hozir 10 yosh (bugun - 11 yil + 1 kun).
    _add_citizen(minus_years(today, 11) + timedelta(days=1), "102")
    # 11 yosh — kirmasin.
    _add_citizen(minus_years(today, 11), "103")

    with SessionLocal() as db:
        facets = data_query.analyze(db, "10 yoshgacha bolalar nechta?")
        answer = data_query.build_answer(db, "10 yoshgacha bolalar nechta?")

    assert (facets.age_min, facets.age_max) == (None, 10), facets
    assert answer.total == baseline + 2, (
        f"10 yoshli bolalar tushib qoldi: baseline={baseline}, total={answer.total}"
    )


def test_range_query_counts_only_inside_bounds(clean):
    """«6 yoshdan 10 yoshgacha» — 6..10, 0–5 va 11+ kirmasin."""
    from app.services import data_query

    with SessionLocal() as db:
        baseline = data_query.build_answer(
            db, "6 yoshdan 10 yoshgacha bolalar nechta?"
        ).total

    today = date.today()
    _add_citizen(minus_years(today, 3), "201")          # 3 yosh — tashqarida
    _add_citizen(minus_years(today, 6) + timedelta(days=1), "202")   # 5 yosh — tashqarida
    _add_citizen(minus_years(today, 6), "203")          # 6 yosh — ichida
    _add_citizen(minus_years(today, 10), "204")         # 10 yosh — ichida
    _add_citizen(minus_years(today, 11) - timedelta(days=1), "205")  # 11 yosh — tashqarida

    with SessionLocal() as db:
        facets = data_query.analyze(db, "6 yoshdan 10 yoshgacha bolalar nechta?")
        answer = data_query.build_answer(db, "6 yoshdan 10 yoshgacha bolalar nechta?")

    assert (facets.age_min, facets.age_max) == (6, 10), facets
    assert answer.total == baseline + 2, (baseline, answer.total)

    # SQL bilan solishtirish (mustaqil hisob).
    with SessionLocal() as db:
        expected = int(
            db.execute(
                select(func.count()).select_from(Citizen).where(
                    Citizen.birth_date <= minus_years(today, 6),
                    Citizen.birth_date > minus_years(today, 11),
                )
            ).scalar_one()
        )
    assert answer.total == expected
