from __future__ import annotations

import io

import pytest

from app.core.errors import APIError
from app.services.documents import _detect_kind

def _make_docx() -> bytes:
    from docx import Document

    document = Document()
    table = document.add_table(rows=2, cols=3)
    table.rows[0].cells[0].text = "F.I.Sh."
    table.rows[0].cells[1].text = "Jinsi"
    table.rows[0].cells[2].text = "Telefon"
    table.rows[1].cells[0].text = "Testov Ota"
    table.rows[1].cells[1].text = "Erkak"
    table.rows[1].cells[2].text = "+998901234567"
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()

def _make_xlsx() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["F.I.Sh.", "Jinsi", "Telefon"])
    sheet.append(["Testov Ota", "Erkak", "+998901234567"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()

def test_docx_is_detected_as_docx():
    data = _make_docx()
    assert data[:4] == b"PK\x03\x04"
    assert _detect_kind("hujjat.docx", data) == "docx"

def test_xlsx_is_detected_as_xlsx():
    data = _make_xlsx()
    assert data[:4] == b"PK\x03\x04"
    assert _detect_kind("ro'yxat.xlsx", data) == "xlsx"

def test_docx_with_wrong_extension_still_detected():
    data = _make_docx()
    assert _detect_kind("nomi.xlsx", data) == "docx"

def test_pdf_is_detected():
    assert _detect_kind("hujjat.pdf", b"%PDF-1.7\n...") == "pdf"

def test_csv_is_detected():
    data = "F.I.Sh.,Jinsi\nTestov Ota,Erkak\n".encode("utf-8")
    assert _detect_kind("ro'yxat.csv", data) == "csv"

def test_old_xls_is_rejected():
    with pytest.raises(APIError):
        _detect_kind("eski.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 16)

def test_broken_zip_is_rejected():
    with pytest.raises(APIError):
        _detect_kind("buzilgan.xlsx", b"PK\x03\x04" + b"\x00" * 32)

def test_docx_upload_does_not_crash(auth):
    from sqlalchemy import delete, select

    from app.core.db import SessionLocal
    from app.models import Document, DocumentBlob, ImportBatch

    client, token = auth
    response = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": token},
        files={"file": ("hujjat.docx", _make_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"analyze": "true"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document"]["kind"] == "docx"

    with SessionLocal() as db:
        documents = db.execute(
            select(Document).where(Document.original_name == "hujjat.docx")
        ).scalars().all()
        for document in documents:
            db.execute(delete(ImportBatch).where(ImportBatch.document_id == document.id))
            db.execute(delete(DocumentBlob).where(DocumentBlob.document_id == document.id))
            db.execute(delete(Document).where(Document.id == document.id))
        db.commit()
