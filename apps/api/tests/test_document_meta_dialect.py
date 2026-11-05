from __future__ import annotations

from sqlalchemy import select

from app.core.db import SessionLocal
from app.services import citizens as service

def test_filter_uses_jsonb_on_postgresql():
    with SessionLocal() as db:
        dialect = db.get_bind().dialect.name
        condition = service._document_citizen_filter(db, "X")
        if dialect == "postgresql":
            compiled = str(
                select(1).where(condition).compile(compile_kwargs={"literal_binds": True})
            )
            assert "->>" in compiled
        else:
            compiled = str(
                select(1).where(condition).compile(compile_kwargs={"literal_binds": True})
            )
            assert "LIKE" in compiled.upper()

def test_citizen_detail_returns_documents():
    from datetime import date

    from app.models import Citizen, Document

    with SessionLocal() as db:
        citizen = Citizen(
            full_name="N6sinov fuqaro",
            gender="Erkak",
            birth_date=date(1990, 1, 1),
            phone="+998900000701",
        )
        db.add(citizen)
        db.flush()
        document = Document(
            filename="n6sinov.csv",
            original_name="n6sinov.csv",
            content_hash="hash-n6sinov",
            kind="csv",
            status="ready",
            meta={"citizen_id": citizen.id},
        )
        db.add(document)
        db.commit()
        citizen_id = citizen.id
        document_id = document.id

    try:
        with SessionLocal() as db:
            detail = service.get_citizen_detail(db, citizen_id)
        assert any(item["id"] == document_id for item in detail["documents"])
    finally:
        with SessionLocal() as db:
            citizen = db.get(Citizen, citizen_id)
            document = db.get(Document, document_id)
            if document is not None:
                db.delete(document)
            if citizen is not None:
                db.delete(citizen)
            db.commit()
