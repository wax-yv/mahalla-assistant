"""Data query keng qamrov — har qanday odatiy savolga aniq javob.

Foydalanuvchi talabi: AI assistent har qanday odatiy bazaga doir savolga
to'liq javob berishi kerak. Bu test matritsasi turli so'zlashuv
shakllarini qamrab oladi (entity, holat, taqsimot, reyting, agregat).
"""

from __future__ import annotations

import pytest
from sqlalchemy import and_, delete, func, or_, select

from app.core.db import SessionLocal
from app.models import AuditLog, Case, Citizen, Family, House, Street, Task

MARKER = "DQSinov"


def _cleanup() -> None:
    with SessionLocal() as db:
        ids = db.execute(
            select(Citizen.id).where(Citizen.full_name.like(f"{MARKER}%"))
        ).scalars().all()
        db.execute(delete(AuditLog).where(AuditLog.entity_id.in_(ids)))
        db.execute(delete(Citizen).where(Citizen.id.in_(ids)))
        db.commit()


@pytest.fixture(autouse=True)
def clean():
    _cleanup()
    yield
    _cleanup()


def _answer(message: str):
    from app.services import data_query

    with SessionLocal() as db:
        return data_query.build_answer(db, message)


# ---------------------------------------------------------------- entity


def test_singular_oila_counts_families():
    """«nechta oila bor?» — fuqaro emas, OILA soni (eski regex bug'i)."""
    answer = _answer("nechta oila bor?")
    assert answer.facets.entity == "families"
    assert answer.entity_label == "oila"
    with SessionLocal() as db:
        expected = int(db.execute(select(func.count()).select_from(Family)).scalar_one())
    assert answer.total == expected


def test_uy_counts_houses():
    """«nechta uy bor?» — uylar soni."""
    answer = _answer("nechta uy bor?")
    assert answer.facets.entity == "houses"
    assert answer.entity_label == "uy"
    with SessionLocal() as db:
        expected = int(db.execute(select(func.count()).select_from(House)).scalar_one())
    assert answer.total == expected


def test_kocha_counts_streets():
    """«nechta ko'cha bor?» — ko'chalar soni."""
    answer = _answer("nechta ko'cha bor?")
    assert answer.facets.entity == "streets"
    assert answer.entity_label == "ko'cha"
    with SessionLocal() as db:
        expected = int(db.execute(select(func.count()).select_from(Street)).scalar_one())
    assert answer.total == expected


def test_houses_on_street():
    """«X ko'chada nechta uy bor?» — o'sha ko'chadagi uylar."""

    with SessionLocal() as db:
        street = db.execute(
            select(Street).join(House, House.street_id == Street.id)
            .group_by(Street.id)
            .having(func.count(House.id) >= 2)
            .limit(1)
        ).scalar_one()
        expected = int(
            db.execute(
                select(func.count()).select_from(House).where(House.street_id == street.id)
            ).scalar_one()
        )
    answer = _answer(f"{street.name}da nechta uy bor?")
    assert answer.facets.entity == "houses"
    assert answer.facets.street == street.name, answer.facets.street
    assert answer.total == expected


# ---------------------------------------------------------------- social


def test_social_filter_on_families():
    """«temir daftarda nechta oila bor?» — a'zosi Temir daftarda bo'lgan OILALAR."""
    answer = _answer("temir daftarda nechta oila bor?")
    assert answer.facets.entity == "families"
    assert answer.facets.social == ["Temir daftar"]
    with SessionLocal() as db:
        expected = int(
            db.execute(
                select(func.count()).select_from(Family).where(
                    or_(
                        Family.social_status == "Temir daftar",
                        Family.members.any(
                            and_(
                                Citizen.social_status == "Temir daftar",
                                Citizen.archived_at.is_(None),
                            )
                        ),
                    )
                )
            ).scalar_one()
        )
    assert answer.total == expected
    assert answer.total > 0, "Temir daftar a'zolari bor oilalar topilishi kerak"


def test_social_filter_on_citizens():
    """«temir daftar fuqarolari ro'yxati» — fuqarolar (entity saqlanadi)."""
    answer = _answer("temir daftar fuqarolari ro'yxatini chiqarib ber")
    assert answer.facets.entity == "citizens"
    assert answer.facets.social == ["Temir daftar"]
    assert answer.total > 0


# ---------------------------------------------------------------- bandlik


def test_talabalar_map_to_oqiydi():
    """«talabalar nechta?» — O'qiydi bandligi (eski javob: butun baza)."""
    answer = _answer("talabalar nechta?")
    assert answer.facets.employment == ["O'qiydi"], answer.facets.employment
    with SessionLocal() as db:
        expected = int(
            db.execute(
                select(func.count()).select_from(Citizen).where(
                    Citizen.employment_status == "O'qiydi", Citizen.archived_at.is_(None)
                )
            ).scalar_one()
        )
    assert answer.total == expected


def test_ishsiz_count():
    answer = _answer("ishsizlar nechta?")
    assert answer.facets.employment == ["Ishsiz"]
    assert 0 < answer.total < 1279


# ---------------------------------------------------------------- agregat


def test_average_age():
    """«o'rtacha yosh nechchi?» — o'rtacha yosh hisoblanadi."""
    answer = _answer("o'rtacha yosh nechchi?")
    assert answer.facets.aggregate == "avg_age"
    # Javobda "yosh" so'zi va o'ndan katta raqam bo'lishi kerak.
    import re

    match = re.search(r"O'rtacha yosh: (\d+)", answer.text)
    assert match, answer.text
    value = int(match.group(1))
    assert 0 < value < 100


# ---------------------------------------------------------------- holat


def test_overdue_tasks():
    """«kechikkan vazifalar nechta?» — faqat muddati o'tganlar."""
    from app.core.time import today_local

    answer = _answer("kechikkan vazifalar nechta?")
    assert answer.facets.entity == "tasks"
    assert answer.facets.status == "overdue"
    with SessionLocal() as db:
        expected = int(
            db.execute(
                select(func.count()).select_from(Task).where(
                    Task.due_date < today_local(),
                    Task.status.notin_(["completed", "cancelled"]),
                )
            ).scalar_one()
        )
    assert answer.total == expected, (answer.total, expected)


def test_open_cases():
    """«ochiq murojaatlar nechta?» — yopilmaganlar."""
    answer = _answer("ochiq murojaatlar nechta?")
    assert answer.facets.entity == "cases"
    assert answer.facets.status == "open"
    with SessionLocal() as db:
        expected = int(
            db.execute(
                select(func.count()).select_from(Case).where(
                    Case.status.notin_(["closed", "cancelled"])
                )
            ).scalar_one()
        )
    assert answer.total == expected


# ---------------------------------------------------------------- taqsimot


def test_gender_breakdown():
    """«jins bo'yicha taqsimot» — Erkak/Ayol taqsimoti."""
    answer = _answer("jins bo'yicha taqsimot")
    assert answer.facets.breakdown_by == "gender"
    labels = {name for name, _value in answer.breakdown}
    assert "Erkak" in labels and "Ayol" in labels


def test_employment_breakdown():
    """«bandlik holati bo'yicha taqsimot»."""
    answer = _answer("bandlik holati bo'yicha taqsimot")
    assert answer.facets.breakdown_by == "employment"
    assert len(answer.breakdown) >= 2


def test_case_status_breakdown():
    """«murojaatlar holati bo'yicha taqsimot»."""
    answer = _answer("murojaatlar holati bo'yicha taqsimot")
    assert answer.facets.breakdown_by == "status"
    assert len(answer.breakdown) >= 1


# ---------------------------------------------------------------- reyting


def test_ranking_top_street():
    """«eng ko'p fuqaro qaysi ko'chada?» — top ko'cha va soni."""
    from app.services.agents import detect_intent

    intent, _intents = detect_intent("eng ko'p fuqaro qaysi ko'chada?")
    assert intent == "data_stats", intent

    answer = _answer("eng ko'p fuqaro qaysi ko'chada?")
    assert answer.facets.rank_top is True
    assert "Eng ko'p fuqaro" in answer.text
    assert len(answer.breakdown) >= 1
    # Top ko'cha ro'yxatda birinchi o'rinda.
    assert answer.breakdown[0][1] >= (answer.breakdown[1][1] if len(answer.breakdown) > 1 else 0)
