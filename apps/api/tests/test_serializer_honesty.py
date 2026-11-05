"""N-4: serializatsiya — halol qiymatlar va yagona vaqt.

Muammo (audit N-4):
- ro'yxatda `duplicate_risk="low"` hardcoded — real xavf faqat detailda
  hisoblanadi (yolg'on xavfsizlik hissi);
- `program_out` har qator uchun alohida `datetime.now()` — ro'yxat ichida
  "stale" chegarasi boshqacha bo'lishi mumkin edi;
- `_iso()` o'lik funksiya;
- `compare()` topilmagan ID'larni jimgina o'tkazib yuborardi.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import Citizen, Program

MARKER = "N4sinov"


def _cleanup() -> None:
    with SessionLocal() as db:
        citizens = db.execute(
            select(Citizen.id).where(Citizen.full_name.like(f"{MARKER}%"))
        ).scalars().all()
        db.execute(delete(Citizen).where(Citizen.id.in_(citizens)))
        programs = db.execute(
            select(Program.id).where(Program.name.like(f"{MARKER}%"))
        ).scalars().all()
        db.execute(delete(Program).where(Program.id.in_(programs)))
        db.commit()


@pytest.fixture()
def clean():
    _cleanup()
    yield
    _cleanup()


def _make_citizen() -> str:
    with SessionLocal() as db:
        citizen = Citizen(
            full_name=f"{MARKER} fuqaro",
            gender="Erkak",
            birth_date=date(1990, 1, 1),
            phone="+998900000801",
        )
        db.add(citizen)
        db.commit()
        return citizen.id


def test_citizen_list_does_not_claim_low_risk(clean):
    """Ro'yxatda `duplicate_risk` hisoblanmaganini halol ko'rsatadi."""
    from app.services import citizens as service

    _make_citizen()
    with SessionLocal() as db:
        rows, _meta = service.list_citizens(db, q=MARKER, page_size=20)
    assert rows, "fuqaro topilmadi"
    assert all(row["data_quality"]["duplicate_risk"] == "unknown" for row in rows)


def test_citizen_detail_computes_real_risk(clean):
    """Detailda real xavf hisoblanadi."""
    from app.services import citizens as service

    citizen_id = _make_citizen()
    with SessionLocal() as db:
        quality = service.citizen_quality(db.get(Citizen, citizen_id), "medium")
        assert quality["duplicate_risk"] == "medium"


def test_program_out_uses_given_now(clean):
    """`program_out` berilgan `now` bilan bir xil stale holat qaytaradi."""
    from datetime import datetime, timedelta, timezone

    from app.services.serializers import program_out

    with SessionLocal() as db:
        program = Program(
            name=f"{MARKER} dastur",
            organization=f"{MARKER} org",
            type="credit",
            status="verified",
            last_verified_at=datetime(2025, 9, 1, tzinfo=timezone.utc) - timedelta(days=10),
        )
        db.add(program)
        db.commit()
        program_id = program.id

    try:
        with SessionLocal() as db:
            program = db.get(Program, program_id)
            first = program_out(program, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
            second = program_out(program, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert first["stale"] is True
        assert second["stale"] is True
    finally:
        with SessionLocal() as db:
            db.execute(delete(Program).where(Program.id == program_id))
            db.commit()


def test_compare_rejects_unknown_program_ids(clean):
    """`compare()` topilmagan ID uchun aniq xato beradi (jim skip yo'q)."""
    from app.core.errors import APIError
    from app.services import programs as service

    with SessionLocal() as db:
        with pytest.raises(APIError) as exc:
            service.compare(db, program_ids=["YOQ-DASTUR-1"])
    assert exc.value.status_code == 422
    assert "YOQ-DASTUR-1" in exc.value.message
