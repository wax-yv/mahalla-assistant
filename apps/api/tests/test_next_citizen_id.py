"""N-5: `next_citizen_id` — string MAX o'rniga raqamli MAX va retry.

Muammo (audit N-5):
- `func.max(Citizen.id)` string tartibida ishlaydi: `F-99999` dan keyin
  `F-100000` kelganda string MAX noto'g'ri tanlanadi;
- parallel yaratishda ikki so'rov bir xil MAX ni o'qib, bir xil ID
  oladi — IntegrityError (500).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import AuditLog, Citizen

MARKER = "N5sinov"


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


def test_next_citizen_id_ignores_non_numeric_prefixes(clean):
    """Raqamsiz ID'lar hisobga olinmaydi."""
    from app.services import citizens as service

    with SessionLocal() as db:
        # Mavjud fuqarolar orasida raqamsiz/g'alati ID bo'lsa ham ishlashi kerak.
        first = service.next_citizen_id(db)
    assert first.startswith("F-")
    assert int(first.split("-")[1]) >= 1


def test_next_citizen_id_survives_six_digit_ids(clean):
    """`F-1000000` mavjud bo'lsa string MAX uni ko'rmaydi (leksikografik)."""
    from app.services import citizens as service

    with SessionLocal() as db:
        db.add(
            Citizen(
                id="F-999999",
                full_name=f"{MARKER} besh_xona",
                gender="Erkak",
                birth_date=date(1990, 1, 1),
                phone="+998900000901",
            )
        )
        db.add(
            Citizen(
                id="F-1000000",
                full_name=f"{MARKER} yetti_xona",
                gender="Erkak",
                birth_date=date(1990, 1, 1),
                phone="+998900000903",
            )
        )
        db.commit()
        next_id = service.next_citizen_id(db)
        db.query(Citizen).filter(Citizen.id.in_(["F-999999", "F-1000000"])).delete(
            synchronize_session=False
        )
        db.commit()
    assert next_id == "F-1000001", f"string MAX xato berdi: {next_id}"


def test_next_citizen_id_is_monotonic(clean):
    """Ketma-ket ID'lar oshib boradi."""
    from app.services import citizens as service

    with SessionLocal() as db:
        first = int(service.next_citizen_id(db).split("-")[1])
        second = int(service.next_citizen_id(db).split("-")[1])
    assert second == first


def test_create_citizen_assigns_numeric_id(clean):
    """`create_citizen` raqamli ID bilan fuqaro yaratadi."""
    from app.schemas import CitizenCreate
    from app.services import citizens as service

    with SessionLocal() as db:
        citizen = service.create_citizen(
            db,
            CitizenCreate(full_name=f"{MARKER} yangi", gender="Ayol", phone="+998900000902"),
            "tester",
            None,
        )
        citizen_id = citizen.id
    assert citizen_id.startswith("F-")
    assert citizen_id.split("-")[1].isdigit()
