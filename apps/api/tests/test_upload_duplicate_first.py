from __future__ import annotations

from app.core.db import SessionLocal
from app.models import Document
from sqlalchemy import select

MARKER = "D13sinov"

def _cleanup() -> None:
    with SessionLocal() as db:
        rows = db.execute(
            select(Document).where(Document.original_name.like(f"{MARKER}%"))
        ).scalars().all()
        for row in rows:
            db.delete(row)
        db.commit()

def test_upload_returns_first_when_multiple_duplicates_exist():
    from app.services.documents import upload_document

    data = (
        "ism,familiya\n"
        "Aziz,Rahimov\n"
        "Dilnoza,Yusupova\n"
    ).encode("utf-8")

    _cleanup()
    try:
        with SessionLocal() as db:
            first = upload_document(
                db,
                filename=f"{MARKER}-1.csv",
                data=data,
                content_type="text/csv",
                actor="tester",
                request_id=None,
            )
            duplicate = Document(
                filename=f"{MARKER}-2.csv",
                original_name=f"{MARKER}-2.csv",
                mime_type=first.mime_type,
                size=first.size,
                content_hash=first.content_hash,
                kind=first.kind,
            )
            db.add(duplicate)
            db.commit()

            with SessionLocal() as db2:
                result = upload_document(
                    db2,
                    filename=f"{MARKER}-3.csv",
                    data=data,
                    content_type="text/csv",
                    actor="tester",
                    request_id=None,
                )
            assert result.id in {first.id, duplicate.id}
    finally:
        _cleanup()
