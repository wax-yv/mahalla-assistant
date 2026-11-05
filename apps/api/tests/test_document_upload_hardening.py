from __future__ import annotations

import io
import zipfile

import pytest
from app.core.db import SessionLocal
from app.core.errors import APIError
from app.models import Document
from app.services import documents as service

CSV_DATA = (
    "Ism,Familiya,Jins,Tug'ilgan sana,Telefon\n"
    "Testovsinov,Testism,Erkak,1990-05-15,+998900000010\n"
)
PDF_DATA = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"

@pytest.fixture()
def clean_documents():
    def _cleanup():
        with SessionLocal() as db:
            rows = db.execute(
                Document.__table__.select().where(
                    Document.original_name.like("O10 sinov%")
                )
            ).fetchall()
            for row in rows:
                db.execute(
                    Document.__table__.delete().where(Document.id == row.id)
                )
            db.commit()

    _cleanup()
    yield
    _cleanup()

def _upload(filename: str, data: bytes, content_type: str = "application/octet-stream"):
    with SessionLocal() as db:
        return service.upload_document(
            db,
            filename=filename,
            data=data,
            content_type=content_type,
            actor="tester",
            request_id=None,
        )

def test_upload_rejects_oversized_file_with_413(clean_documents):
    from app.core.config import settings

    data = b"a" * (settings.max_upload_bytes + 1)
    with pytest.raises(APIError) as exc:
        _upload("O10 sinov katta.csv", data)
    assert exc.value.status_code == 413, (
        f"kutilgan 413, kelgan {exc.value.status_code}"
    )

def test_upload_rejects_extension_content_mismatch(clean_documents):
    with pytest.raises(APIError) as exc:
        _upload("O10 sinov nomartosh.xlsx", CSV_DATA.encode("utf-8"))
    assert exc.value.status_code == 422, (
        f"kutilgan 422, kelgan {exc.value.status_code}"
    )

def test_upload_rejects_pdf_named_as_csv(clean_documents):
    with pytest.raises(APIError) as exc:
        _upload("O10 sinov pdf.csv", PDF_DATA)
    assert exc.value.status_code == 422

def test_upload_accepts_matching_csv(clean_documents):
    document = _upload("O10 sinov ro'yxat.csv", CSV_DATA.encode("utf-8"))
    assert document.kind == "csv"

def test_upload_accepts_matching_pdf(clean_documents):
    document = _upload("O10 sinov hujjat.pdf", PDF_DATA)
    assert document.kind == "pdf"

def test_upload_mime_comes_from_allowlist(clean_documents):
    document = _upload(
        "O10 sinov mime.csv",
        CSV_DATA.encode("utf-8"),
        content_type="application/x-msdownload; name=virus.exe",
    )
    assert document.mime_type == "text/csv", (
        f"mime noto'g'ri: {document.mime_type}"
    )

def test_allowed_mime_types_are_fixed():
    assert service.MIME_BY_KIND["csv"] == "text/csv"
    assert service.MIME_BY_KIND["pdf"] == "application/pdf"
    assert service.MIME_BY_KIND["xlsx"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert service.MIME_BY_KIND["docx"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

def test_upload_rejects_zip_bomb(clean_documents):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/large.bin", b"\0" * (service.MAX_ZIP_UNCOMPRESSED_BYTES + 1024))
    with pytest.raises(APIError) as exc:
        _upload("O10 sinov bomba.xlsx", buffer.getvalue())
    assert exc.value.status_code == 422, (
        f"kutilgan 422, kelgan {exc.value.status_code}"
    )

def test_zip_limit_is_50_mb():
    assert service.MAX_ZIP_UNCOMPRESSED_BYTES == 50 * 1024 * 1024

def test_router_rejects_invalid_mapping_json(auth, clean_documents):
    client, token = auth
    response = client.post(
        "/api/v1/documents",
        files={"file": ("O10 sinov map.csv", CSV_DATA.encode("utf-8"), "text/csv")},
        data={"mapping": "{bu yaroq json"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 422, (
        f"kutilgan 422, kelgan {response.status_code}: {response.text[:200]}"
    )

def test_router_rejects_oversized_content_length(auth, clean_documents):
    import asyncio

    from app.routers import documents as documents_router

    class _FakeRequest:
        headers = {"content-length": str(999 * 1024 * 1024)}

    class _FakeFile:
        async def read(self, size: int = -1):
            return b""

    with pytest.raises(APIError) as exc:
        asyncio.run(documents_router._read_upload(_FakeRequest(), _FakeFile()))
    assert exc.value.status_code == 413, (
        f"kutilgan 413, kelgan {exc.value.status_code}"
    )

def test_router_stops_stream_above_limit(auth, clean_documents):
    import asyncio

    from app.core.config import settings
    from app.routers import documents as documents_router

    chunk = b"a" * (1024 * 1024)

    class _FakeRequest:
        headers = {}

    class _FakeFile:
        def __init__(self):
            self.count = 0

        async def read(self, size: int = -1):
            self.count += 1
            return chunk

    fake = _FakeFile()
    with pytest.raises(APIError) as exc:
        asyncio.run(documents_router._read_upload(_FakeRequest(), fake))
    assert exc.value.status_code == 413
    assert fake.count <= settings.max_upload_mb + 2, (
        f"oqim to'xtatilmadi: {fake.count} ta blok"
    )

def test_router_accepts_valid_csv(auth, clean_documents):
    client, token = auth
    response = client.post(
        "/api/v1/documents",
        files={"file": ("O10 sinov router.csv", CSV_DATA.encode("utf-8"), "text/csv")},
        data={"analyze": "false", "mapping": "{}"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 201, (
        f"kutilgan 201, kelgan {response.status_code}: {response.text[:200]}"
    )
