from __future__ import annotations

import pytest
from app.core.db import SessionLocal
from app.core.downloads import content_disposition
from app.models import Document, DocumentBlob
from sqlalchemy import delete


def test_unicode_filename_is_encoded():
    header = content_disposition("Oʻzbekiston_ro‘yxat.csv")
    assert "filename*=UTF-8''" in header
    assert 'filename="' in header
    header.encode("latin-1")

def test_quote_and_crlf_are_removed():
    header = content_disposition('bad"name\r\nX-Injected: 1.csv')
    assert "\r" not in header
    assert "\n" not in header
    assert 'filename="bad' in header

def test_empty_filename_gets_fallback():
    header = content_disposition("")
    assert 'filename="file"' in header

def test_cyrillic_filename_is_encoded():
    header = content_disposition("Отчёт.docx")
    header.encode("latin-1")
    assert "filename*=UTF-8''" in header

def test_documents_download_with_unicode_name(auth):
    client, token = auth
    headers = {"X-CSRF-Token": token}

    data = "F.I.Sh.,Jinsi\nTestSinov Ota,Erkak\n".encode("utf-8")
    upload = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("Oʻzbekiston_ro‘yxat.csv", data, "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["document"]["id"]

    try:
        download = client.get(f"/api/v1/documents/{document_id}/download")
        assert download.status_code == 200, download.text
        disposition = download.headers.get("content-disposition", "")
        assert "filename*=UTF-8''" in disposition
        disposition.encode("latin-1")
    finally:
        with SessionLocal() as db:
            db.execute(delete(DocumentBlob).where(DocumentBlob.document_id == document_id))
            db.execute(delete(Document).where(Document.id == document_id))
            db.commit()

@pytest.mark.parametrize(
    "filename",
    ["hisobot-oy-20260101.xlsx", "Oʻzbekiston hisoboti.docx", "отчёт.pdf"],
)
def test_helper_never_raises(filename: str):
    header = content_disposition(filename)
    header.encode("latin-1")
    assert header.startswith("attachment;")
