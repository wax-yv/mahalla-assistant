"""J-6: `citizens.data_source` uzunligi — fayl nomi 255 belgidan uzun bo'lishi mumkin.

Muqova: Postgres'da `String(64)` ustunga 64+ belgili fayl nomi bilan commit
"value too long for type character varying(64)" -> 500, import batch "failed"
holatda qoladi. SQLite uzunlikni tekshirmaydi — lokal sinov ko'rmaydi.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import Citizen, Document, DocumentBlob, Family, House, ImportBatch, Street


@pytest.fixture()
def clean_db():
    """Test yozuvlarini tozalaydi (boshqa testlarga tegilmaydi)."""
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
            select(Document).where(Document.original_name.like("Oʻzbekiston_respublikasi%"))
        ).scalars().all()
        for document in documents:
            db.execute(delete(ImportBatch).where(ImportBatch.document_id == document.id))
            db.execute(delete(DocumentBlob).where(DocumentBlob.document_id == document.id))
            db.execute(delete(Document).where(Document.id == document.id))
        db.commit()
    yield
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
            select(Document).where(Document.original_name.like("Oʻzbekiston_respublikasi%"))
        ).scalars().all()
        for document in documents:
            db.execute(delete(ImportBatch).where(ImportBatch.document_id == document.id))
            db.execute(delete(DocumentBlob).where(DocumentBlob.document_id == document.id))
            db.execute(delete(Document).where(Document.id == document.id))
        db.commit()


def test_data_source_column_is_255_in_model():
    from app.models import Citizen as CitizenModel

    column = CitizenModel.__table__.columns["data_source"]
    assert column.type.length == 255


def test_long_file_name_does_not_break_import(clean_db, auth):
    """64 belgidan uzun fayl nomi bilan import 500 bermasligi kerak."""
    client, token = auth
    headers = {"X-CSRF-Token": token}

    long_name = "Oʻzbekiston_respublikasi_aholi_roʻyxati_mahalla_Navbahor_" + "x" * 60 + ".csv"
    assert len(long_name) > 64

    data = "F.I.Sh.,Jinsi\nTestSinov Uzun O'g'li,Erkak\n".encode("utf-8")
    upload = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (long_name, data, "text/csv")},
        data={"analyze": "true"},
    )
    assert upload.status_code == 201, upload.text
    batch = upload.json()["analysis"]["batch"]
    assert batch["error_count"] == 0

    commit = client.post(
        f"/api/v1/documents/imports/{batch['id']}/commit",
        headers=headers,
        json={},
    )
    assert commit.status_code == 200, commit.text

    with SessionLocal() as db:
        citizen = db.execute(
            select(Citizen).where(Citizen.full_name == "TestSinov Uzun O'g'li")
        ).scalars().first()
    assert citizen is not None
    assert citizen.data_source
    assert len(citizen.data_source) <= 255


def test_migration_script_widens_data_source():
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "scripts" / "migrate.sql"
    text = path.read_text(encoding="utf-8")
    assert "data_source" in text
    assert "VARCHAR(255)" in text
