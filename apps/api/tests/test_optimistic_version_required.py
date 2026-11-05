"""D-1: PATCH so'rovlarida `version` majburiy.

Muammo (audit D-1): `payload.version is None` bo'lsa qulf tekshiruvi
o'tkazib yuborilardi — ikki kishi bir vaqtda tahrirlasa birinchining
o'zgarishi yo'qolardi ("lost update").

To'g'rilash: `CitizenUpdate`, `FamilyUpdate`, `CaseUpdate`, `TaskUpdate`
sxemalarida `version` majburiy maydon; xizmat darajasida mos qiymat
bo'lmasa `conflict` (409) chiqadi.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete, select
from pydantic import ValidationError

from app.core.db import SessionLocal
from app.models import Case, Citizen, Family, House, Mahalla, Street, Task, WorkLog

MARKER = "D1sinov"


@pytest.fixture()
def clean():
    def _cleanup():
        with SessionLocal() as db:
            task_ids = db.execute(select(Task.id).where(Task.title.like(f"{MARKER}%"))).scalars().all()
            case_ids = db.execute(select(Case.id).where(Case.title.like(f"{MARKER}%"))).scalars().all()
            citizen_ids = db.execute(
                select(Citizen.id).where(Citizen.full_name.like(f"{MARKER}%"))
            ).scalars().all()
            street_ids = db.execute(
                select(Street.id).where(Street.name.like(f"{MARKER}%"))
            ).scalars().all()
            mahalla_ids = db.execute(
                select(Mahalla.id).where(Mahalla.name.like(f"{MARKER}%"))
            ).scalars().all()
            db.execute(delete(WorkLog).where(WorkLog.task_id.in_(task_ids)))
            db.execute(delete(Task).where(Task.id.in_(task_ids)))
            db.execute(delete(Case).where(Case.id.in_(case_ids)))
            db.execute(delete(Citizen).where(Citizen.id.in_(citizen_ids)))
            db.execute(
                delete(Family).where(
                    Family.house_id.in_(select(House.id).where(House.street_id.in_(street_ids)))
                )
            )
            db.execute(delete(House).where(House.street_id.in_(street_ids)))
            db.execute(delete(Street).where(Street.id.in_(street_ids)))
            db.execute(delete(Mahalla).where(Mahalla.id.in_(mahalla_ids)))
            db.commit()

    _cleanup()
    yield
    _cleanup()


def _make_citizen() -> str:
    with SessionLocal() as db:
        citizen = Citizen(
            full_name=f"{MARKER} fuqaro",
            gender="Erkak",
            birth_date=date(1990, 1, 1),
            phone="+998900000101",
        )
        db.add(citizen)
        db.commit()
        return citizen.id


def _make_family() -> str:
    with SessionLocal() as db:
        mahalla = Mahalla(name=f"{MARKER} mahalla", district="Test")
        db.add(mahalla)
        db.flush()
        street = Street(mahalla_id=mahalla.id, name=f"{MARKER} ko'cha")
        db.add(street)
        db.flush()
        house = House(street_id=street.id, house_number=f"{MARKER}-1")
        db.add(house)
        db.flush()
        family = Family(house_id=house.id, notes=f"{MARKER} oila")
        db.add(family)
        db.commit()
        return family.id


def _make_case() -> str:
    with SessionLocal() as db:
        case = Case(title=f"{MARKER} case", category="umumiy", status="open", priority="normal")
        db.add(case)
        db.commit()
        return case.id


def _make_task() -> str:
    with SessionLocal() as db:
        task = Task(title=f"{MARKER} vazifa", category="umumiy", status="new", priority="normal")
        db.add(task)
        db.commit()
        return task.id


# ---------------------------------------------------------------- sxema


@pytest.mark.parametrize(
    "schema_name",
    ["CitizenUpdate", "FamilyUpdate", "CaseUpdate", "TaskUpdate"],
)
def test_version_is_required_in_update_schemas(schema_name):
    """`version` berilmasa sxema darajasida 422 (validatsiya xatosi)."""
    from app import schemas

    schema = getattr(schemas, schema_name)
    with pytest.raises(ValidationError):
        schema(notes="x" if schema_name != "TaskUpdate" else "x")
    assert schema(version=1).version == 1


# ---------------------------------------------------------------- fuqaro


def test_update_citizen_requires_current_version(clean):
    """Eski versiya bilan yozish rad etiladi (409)."""
    from app.core.errors import APIError
    from app.schemas import CitizenUpdate
    from app.services import citizens as service

    citizen_id = _make_citizen()
    with SessionLocal() as db:
        citizen = db.get(Citizen, citizen_id)
        stale = citizen.version

    with SessionLocal() as db:
        citizen = db.get(Citizen, citizen_id)
        service.update_citizen(
            db, citizen_id, CitizenUpdate(notes="birinchi", version=stale), "tester", None
        )

    with SessionLocal() as db:
        citizen = db.get(Citizen, citizen_id)
        assert citizen.version == stale + 1
        assert citizen.notes == "birinchi"

        with pytest.raises(APIError) as exc:
            service.update_citizen(
                db, citizen_id, CitizenUpdate(notes="ikkinchi", version=stale), "tester", None
            )
        assert exc.value.status_code == 409


def test_update_citizen_accepts_fresh_version(clean):
    """To'g'ri versiya bilan yozish ishlaydi."""
    from app.schemas import CitizenUpdate
    from app.services import citizens as service

    citizen_id = _make_citizen()
    with SessionLocal() as db:
        citizen = db.get(Citizen, citizen_id)
        version = citizen.version
        service.update_citizen(
            db, citizen_id, CitizenUpdate(notes="yangilandi", version=version), "tester", None
        )
        citizen = db.get(Citizen, citizen_id)
        assert citizen.version == version + 1
        assert citizen.notes == "yangilandi"


# ---------------------------------------------------------------- oila


def test_update_family_requires_current_version(clean):
    """Oila uchun ham versiya majburiy."""
    from app.core.errors import APIError
    from app.schemas import FamilyUpdate
    from app.services import hierarchy as service

    family_id = _make_family()
    with SessionLocal() as db:
        family = db.get(Family, family_id)
        stale = family.version

    with SessionLocal() as db:
        family = db.get(Family, family_id)
        service.update_family(
            db, family_id, FamilyUpdate(notes="birinchi", version=family.version), "tester", None
        )

    with SessionLocal() as db:
        with pytest.raises(APIError) as exc:
            service.update_family(
                db, family_id, FamilyUpdate(notes="ikkinchi", version=stale), "tester", None
            )
        assert exc.value.status_code == 409


# ---------------------------------------------------------------- case


def test_update_case_requires_current_version(clean):
    """Case uchun ham versiya majburiy."""
    from app.core.errors import APIError
    from app.schemas import CaseUpdate
    from app.services import cases as service

    case_id = _make_case()
    with SessionLocal() as db:
        case = db.get(Case, case_id)
        stale = case.version

    with SessionLocal() as db:
        case = db.get(Case, case_id)
        service.update_case(
            db, case_id, CaseUpdate(description="birinchi", version=case.version), "tester", None
        )

    with SessionLocal() as db:
        with pytest.raises(APIError) as exc:
            service.update_case(
                db, case_id, CaseUpdate(description="ikkinchi", version=stale), "tester", None
            )
        assert exc.value.status_code == 409


# ---------------------------------------------------------------- vazifa


def test_update_task_requires_current_version(clean):
    """Vazifa uchun ham versiya majburiy."""
    from app.core.errors import APIError
    from app.schemas import TaskUpdate
    from app.services import cases as service

    task_id = _make_task()
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        stale = task.version

    with SessionLocal() as db:
        task = db.get(Task, task_id)
        service.update_task(
            db, task_id, TaskUpdate(description="birinchi", version=task.version), "tester", None
        )

    with SessionLocal() as db:
        with pytest.raises(APIError) as exc:
            service.update_task(
                db, task_id, TaskUpdate(description="ikkinchi", version=stale), "tester", None
            )
        assert exc.value.status_code == 409
