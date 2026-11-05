from __future__ import annotations

from datetime import date

import pytest
from app.core.db import SessionLocal
from app.models import AuditLog, Citizen, MemoryItem, Program
from sqlalchemy import delete, select

MARKER = "N10sinov"

def _cleanup() -> None:
    with SessionLocal() as db:
        citizens = db.execute(
            select(Citizen.id).where(Citizen.full_name.like(f"{MARKER}%"))
        ).scalars().all()
        programs = db.execute(
            select(Program.id).where(Program.name.like(f"{MARKER}%"))
        ).scalars().all()
        memories = db.execute(
            select(MemoryItem.id).where(MemoryItem.key.like(f"{MARKER}%"))
        ).scalars().all()
        db.execute(delete(MemoryItem).where(MemoryItem.id.in_(memories)))
        db.execute(delete(AuditLog).where(AuditLog.entity_id.in_(programs)))
        db.execute(delete(Program).where(Program.id.in_(programs)))
        db.execute(delete(Citizen).where(Citizen.id.in_(citizens)))
        db.commit()

@pytest.fixture()
def clean():
    _cleanup()
    yield
    _cleanup()

def _make_program(name: str, organization: str, eligibility: dict | None = None) -> str:
    with SessionLocal() as db:
        program = Program(
            name=name,
            organization=organization,
            type="credit",
            status="verified",
            eligibility=eligibility or {},
        )
        db.add(program)
        db.commit()
        return program.id

def _make_citizen(**kwargs) -> str:
    values = {
        "full_name": f"{MARKER} fuqaro",
        "gender": "Erkak",
        "birth_date": date(1990, 1, 1),
        "phone": "+998900000951",
        "employment_status": "Ishlaydi",
    }
    values.update(kwargs)
    with SessionLocal() as db:
        citizen = Citizen(**values)
        db.add(citizen)
        db.commit()
        return citizen.id

def test_detect_organization_uses_word_boundary(clean):
    from app.services import programs as service

    _make_program(f"{MARKER} ipoteka", "Biznesni rivojlantirish banki")
    with SessionLocal() as db:
        assert service.detect_organization(db, "brb uchun kredit") is not None
        assert service.detect_organization(db, "brab so'zi boshqa narsa") is None

def test_detect_organization_full_name(clean):
    from app.services import programs as service

    _make_program(f"{MARKER} dastur", "Agrobank")
    with SessionLocal() as db:
        result = service.detect_organization(db, "agrobank krediti kerak")
    assert result is not None
    assert result["organization"] == "Agrobank"

def test_requires_business_failure_is_not_matchable(clean):
    from app.services import programs as service

    program_id = _make_program(
        f"{MARKER} tadbirkor krediti",
        f"{MARKER} bank",
        eligibility={"requires_business": True},
    )
    citizen_id = _make_citizen(employment_status="Ishlaydi")
    with SessionLocal() as db:
        result = service.match_citizen(db, citizen_id, program_id)[0]
    assert result["result"] == "mos kelmaydi"
    assert "tadbirkorlik ro'yxatdan o'tkazilganligi" not in result["missing_fields"]

def test_missing_fields_not_added_when_not_required(clean):
    from app.services import programs as service

    program_id = _make_program(f"{MARKER} oddiy", f"{MARKER} bank", eligibility={})
    citizen_id = _make_citizen(birth_date=None, phone=None)
    with SessionLocal() as db:
        result = service.match_citizen(db, citizen_id, program_id)[0]
    assert result["result"] == "mos kelishi mumkin"
    assert result["missing_fields"] == []

def test_missing_birth_date_only_when_age_required(clean):
    from app.services import programs as service

    program_id = _make_program(
        f"{MARKER} yoshlar",
        f"{MARKER} bank",
        eligibility={"min_age": 18, "max_age": 30},
    )
    citizen_id = _make_citizen(birth_date=None)
    with SessionLocal() as db:
        result = service.match_citizen(db, citizen_id, program_id)[0]
    assert result["result"] == "ma'lumot yetarli emas"
    assert "tug'ilgan sana" in result["missing_fields"]

def test_save_preference_upsert(clean):
    from app.services import programs as service

    with SessionLocal() as db:
        service.save_preference(
            db,
            conversation_id=None,
            organization="Agrobank",
            program_id=None,
            program_name=f"{MARKER} dastur",
        )
        service.save_preference(
            db,
            conversation_id=None,
            organization="Kapitalbank",
            program_id=None,
            program_name=f"{MARKER} dastur 2",
        )
        rows = db.execute(
            select(MemoryItem).where(MemoryItem.key == "credit.bank_preference")
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].value["organization"] == "Kapitalbank"

def test_compare_rejects_unknown_ids(clean):
    from app.core.errors import APIError
    from app.services import programs as service

    with SessionLocal() as db:
        with pytest.raises(APIError) as exc:
            service.compare(db, ["YOQ-ID-1"])
    assert exc.value.status_code == 422
