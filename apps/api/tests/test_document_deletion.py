"""O-11: «o'chirilgan» hujjat aslida to'liq o'chishi kerak.

Muqova:
- `delete_document` faqat `status="archived"` qilardi — `DocumentBlob`
  (fuqarolar ro'yxati Excel'i) bazada to'liq qolardi.
- Arxivlangan hujjat ID bo'yicha hamon `GET /documents/{id}` va
  `/download` orqali ochilardi — ya'ni «o'chirish» hech narsani yo'qotmasdi.

To'g'rilash: o'chirishda blob ham o'chiriladi; arxivlangan hujjat
`GET`/`download` orqali 404 beradi.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.core.errors import APIError
from app.models import Document, DocumentBlob
from app.services import documents as service

CSV_DATA = "Ism,Familiya,Jins\nTestovsinov,Testism,Erkak\n".encode("utf-8")


@pytest.fixture()
def clean_documents():
    def _cleanup():
        with SessionLocal() as db:
            ids = db.execute(
                select(Document.id).where(Document.original_name.like("O11 sinov%"))
            ).scalars().all()
            if ids:
                db.execute(delete(DocumentBlob).where(DocumentBlob.document_id.in_(ids)))
                db.execute(delete(Document).where(Document.id.in_(ids)))
            db.commit()

    _cleanup()
    yield
    _cleanup()


def _make_document() -> str:
    with SessionLocal() as db:
        document = service.upload_document(
            db,
            filename="O11 sinov ro'yxat.csv",
            data=CSV_DATA,
            content_type="text/csv",
            actor="tester",
            request_id=None,
        )
        return document.id


def test_delete_removes_blob(clean_documents):
    """O'chirilganda fayl mazmuni (blob) ham bazadan o'chadi."""
    document_id = _make_document()

    with SessionLocal() as db:
        service.delete_document(db, document_id, "tester")

    with SessionLocal() as db:
        blob = db.get(DocumentBlob, document_id)
        assert blob is None, "blob bazada qoldi"


def test_delete_keeps_metadata_for_audit(clean_documents):
    """Hujjat yozuvi (audit izi) saqlanib qoladi, holati `archived`."""
    document_id = _make_document()

    with SessionLocal() as db:
        document = service.delete_document(db, document_id, "tester")
        assert document.status == "archived"

    with SessionLocal() as db:
        document = db.get(Document, document_id)
        assert document is not None
        assert document.status == "archived"


def test_archived_document_is_not_found(clean_documents):
    """Arxivlangan hujjat `get_document` orqali topilmaydi."""
    document_id = _make_document()
    with SessionLocal() as db:
        service.delete_document(db, document_id, "tester")

    with SessionLocal() as db:
        with pytest.raises(APIError) as exc:
            service.get_document(db, document_id)
        assert exc.value.status_code == 404


def test_archived_blob_is_not_downloadable(clean_documents):
    """Arxivlangan hujjat fayli yuklab olib bo'lmaydi."""
    document_id = _make_document()
    with SessionLocal() as db:
        service.delete_document(db, document_id, "tester")

    with SessionLocal() as db:
        with pytest.raises(APIError) as exc:
            service.get_document_blob(db, document_id)
        assert exc.value.status_code == 404


def test_router_returns_404_for_archived_document(auth, clean_documents):
    """Router orqali arxivlangan hujjat 404 beradi."""
    client, token = auth
    document_id = _make_document()

    with SessionLocal() as db:
        service.delete_document(db, document_id, "tester")

    response = client.get(f"/api/v1/documents/{document_id}")
    assert response.status_code == 404, (
        f"kutilgan 404, kelgan {response.status_code}: {response.text[:200]}"
    )

    download = client.get(f"/api/v1/documents/{document_id}/download")
    assert download.status_code == 404, (
        f"kutilgan 404, kelgan {download.status_code}: {download.text[:200]}"
    )
