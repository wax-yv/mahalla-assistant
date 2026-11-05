from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import Citizen, Document, DocumentBlob, Family, House, ImportBatch, Street

HEADER = "F.I.Sh.,Jinsi,Tug'ilgan sana,Telefon,Mahalla,Ko'cha,Uy raqami,Oila ID,Oiladagi o'rni"

CSV_DATA = (
    HEADER + "\n"
    "TestSinov Ota O'g'li,Erkak,01.01.1980,+998901234567,Test mahallasi,Test ko'chasi,1,TEST-1,Ota\n"
    "TestSinova Ona Qizi,Ayol,02.02.1982,+998901234567,Test mahallasi,Test ko'chasi,1,TEST-1,Ona\n"
).encode("utf-8")

MAPPING = {
    "full_name": "F.I.Sh.",
    "gender": "Jinsi",
    "birth_date": "Tug'ilgan sana",
    "phone": "Telefon",
    "mahalla": "Mahalla",
    "street": "Ko'cha",
    "house_number": "Uy raqami",
    "family_external_id": "Oila ID",
    "family_role": "Oiladagi o'rni",
}

def _row(name: str, gender: str, birth: str, phone: str, role: str, family: str) -> dict:
    return {
        "F.I.Sh.": name,
        "Jinsi": gender,
        "Tug'ilgan sana": birth,
        "Telefon": phone,
        "Mahalla": "Test mahallasi",
        "Ko'cha": "Test ko'chasi",
        "Uy raqami": "1",
        "Oila ID": family,
        "Oiladagi o'rni": role,
    }

def _cleanup() -> None:
    with SessionLocal() as db:
        citizens = db.execute(
            select(Citizen).where(Citizen.full_name.like("TestSinov%"))
        ).scalars().all()
        for citizen in citizens:
            db.delete(citizen)
        db.execute(delete(Family).where(Family.notes.like("import:TEST-%")))
        db.execute(delete(House).where(House.address_label.like("%Test ko'chasi%")))
        db.execute(delete(Street).where(Street.name == "Test ko'chasi"))
        documents = db.execute(
            select(Document).where(Document.original_name == "k1-test.csv")
        ).scalars().all()
        for document in documents:
            db.execute(delete(ImportBatch).where(ImportBatch.document_id == document.id))
            db.execute(delete(DocumentBlob).where(DocumentBlob.document_id == document.id))
            db.execute(delete(Document).where(Document.id == document.id))
        db.commit()

@pytest.fixture()
def clean_db():
    _cleanup()
    yield
    _cleanup()

def test_shared_phone_creates_two_citizens(clean_db, auth):
    client, token = auth
    headers = {"X-CSRF-Token": token}

    upload = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("k1-test.csv", CSV_DATA, "text/csv")},
        data={"analyze": "true"},
    )
    assert upload.status_code == 201, upload.text
    analysis = upload.json()["analysis"]
    batch = analysis["batch"]
    assert batch["error_count"] == 0, analysis

    commit = client.post(
        f"/api/v1/documents/imports/{batch['id']}/commit",
        headers=headers,
        json={},
    )
    assert commit.status_code == 200, commit.text

    with SessionLocal() as db:
        citizens = db.execute(
            select(Citizen).where(Citizen.full_name.like("TestSinov%"))
        ).scalars().all()
        names = sorted(c.full_name for c in citizens)
        phones = sorted(c.phone for c in citizens)
    assert names == ["TestSinov Ota O'g'li", "TestSinova Ona Qizi"]
    assert phones == ["+998901234567", "+998901234567"]
    assert len(citizens) == 2

def test_validate_does_not_match_by_phone_only(clean_db):
    from app.services import documents as service

    with SessionLocal() as db:
        db.add(
            Citizen(
                full_name="TestSinov Mavjud Ota O'g'li",
                gender="Erkak",
                birth_date="1970-01-01",
                phone="+998905555555",
                family_id=None,
            )
        )
        db.flush()
        db.commit()

    with SessionLocal() as db:
        parsed, errors, _warnings, summary = service.validate_records(
            db,
            MAPPING,
            [_row("TestSinov Boshqa Ona Qizi", "Ayol", "02.02.1982", "+998905555555", "Ona", "TEST-2")],
        )
    assert not [e for e in errors if e["code"] == "AMBIGUOUS_CITIZEN"]
    assert parsed[0]["existing_id"] is None
    assert parsed[0]["match_method"] == "new"
    assert summary["will_create"] == 1
    assert summary["will_update"] == 0

def test_name_and_birth_matches(clean_db):
    from app.services import documents as service

    with SessionLocal() as db:
        citizen = Citizen(
            full_name="TestSinov Kalit O'g'li",
            gender="Erkak",
            birth_date="1975-05-05",
            phone="+998907777777",
            family_id=None,
        )
        db.add(citizen)
        db.flush()
        db.commit()
        citizen_id = citizen.id

    with SessionLocal() as db:
        parsed, _errors, _warnings, summary = service.validate_records(
            db,
            MAPPING,
            [_row("TestSinov Kalit O'g'li", "Erkak", "05.05.1975", "+998907777777", "Ota", "TEST-3")],
        )
    assert parsed[0]["existing_id"] == citizen_id
    assert parsed[0]["match_method"] == "name_birth"
    assert summary["will_update"] == 1

def test_phone_name_match_updates_same_person(clean_db):
    from app.services import documents as service

    with SessionLocal() as db:
        citizen = Citizen(
            full_name="TestSinov Telefon O'g'li",
            gender="Erkak",
            birth_date="1980-08-08",
            phone="+998908888888",
            family_id=None,
        )
        db.add(citizen)
        db.flush()
        db.commit()
        citizen_id = citizen.id

    with SessionLocal() as db:
        parsed, _errors, _warnings, _summary = service.validate_records(
            db,
            MAPPING,
            [_row("TestSinov Telefon O'g'li", "Erkak", "08.08.1980", "+998908888888", "Ota", "TEST-4")],
        )
    assert parsed[0]["existing_id"] == citizen_id
    assert parsed[0]["match_method"] in {"phone_name", "name_birth"}

def test_find_existing_citizen_does_not_raise_multiple_results(clean_db):
    from app.services import documents as service

    with SessionLocal() as db:
        for _ in range(2):
            db.add(
                Citizen(
                    full_name="TestSinov Dublikat O'g'li",
                    gender="Erkak",
                    birth_date="1990-01-01",
                    phone="+998909999999",
                    family_id=None,
                )
            )
        db.flush()
        db.commit()

    with SessionLocal() as db:
        matched, method = service.find_existing_citizen(
            db,
            {
                "full_name": "TestSinov Dublikat O'g'li",
                "birth_date": "1990-01-01",
                "phone": "+998909999999",
            },
        )
    assert matched is None
    assert method == "ambiguous"
