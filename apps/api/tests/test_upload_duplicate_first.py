"""D-13: hujjat yuklashdagi dublikat tekshiruvi bir nechta qatorda buzolmasdi.

Muammo (audit D-13): `scalar_one_or_none()` — bir xil `content_hash` li
ikki faol hujjat bo'lsa `MultipleResultsFound` bilan 500 qaytarardi.
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Document

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
    """Ikki xuddi shu xeshli faol hujjat bo'lsa — xato emas, eng so'nggisi."""
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
            # Test maqsadida ikkinchi "faol" nusxa qo'lda yaratiladi —
            # bir xil xesh, boshqa yozuv.
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
