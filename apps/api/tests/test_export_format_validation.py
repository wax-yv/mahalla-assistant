"""O-17: eksport format validatsiyasi va fayl nomi xavfsizligi.

Muammo:
- `format` query validatsiya qilinmagan (`format: str = Query(...)`) — noma'lum
  formatda xato 500 (server xatosi) bo'lishi mumkin edi. `export_module` da
  lug'at `KeyError` bilan uzilardi.
- Eksport fayl nomi `report.type` / `module` dan yig'ilardi — maxsus belgilar
  (`"`, `/`, `..`) `Content-Disposition` ichiga kirib, sarlavha inyeksiyasi yoki
  yo'l elementlariga olib kelishi mumkin edi.

To'g'rilash:
- router'da `Literal[...]` — FastAPI avtomatik 422 beradi;
- service'da format oldindan tekshiriladi (422, 500 emas);
- fayl nomi komponenti `safe_filename_part()` bilan tozalanadi (yo'l
  elementlari va maxsus belgilar olib tashlanadi).
"""

from __future__ import annotations

from datetime import date
from urllib.parse import unquote

import pytest
from sqlalchemy import delete

from app.core.db import SessionLocal
from app.core.errors import APIError
from app.models import Report

REPORT_MARKER = "O17 sinov hisobili"


@pytest.fixture()
def clean_reports():
    def _cleanup():
        with SessionLocal() as db:
            db.execute(delete(Report).where(Report.title.like(f"{REPORT_MARKER}%")))
            db.commit()

    _cleanup()
    yield
    _cleanup()


def _make_report(report_type: str) -> str:
    with SessionLocal() as db:
        report = Report(
            type=report_type,
            period_start=date(2024, 5, 1),
            period_end=date(2024, 5, 31),
            filters={},
            status="draft",
            title=f"{REPORT_MARKER} {report_type}",
            summary="",
            metrics={},
            narrative="",
            sources=[],
            created_by="tester",
        )
        db.add(report)
        db.flush()
        report_id = report.id
        db.commit()
        return report_id


# ---------------------------------------------------------- format validatsiyasi


def test_report_export_rejects_unknown_format(auth, clean_reports):
    """Noma'lum format — 422 (500 emas)."""
    client, _token = auth
    report_id = _make_report("daily")
    response = client.get(f"/api/v1/reports/{report_id}/export?format=bogus")
    assert response.status_code == 422, (
        f"kutilgan 422, kelgan {response.status_code}: {response.text[:200]}"
    )


def test_report_export_accepts_valid_formats(auth, clean_reports):
    """Ruxsat etilgan formatlar ishlashi kerak."""
    client, _token = auth
    report_id = _make_report("daily")
    for fmt in ("xlsx", "docx", "pdf"):
        response = client.get(f"/api/v1/reports/{report_id}/export?format={fmt}")
        assert response.status_code == 200, f"{fmt}: {response.text[:200]}"
        assert response.content, f"{fmt}: fayl bo'sh"


def test_module_export_rejects_unknown_format(auth):
    """Noma'lum format — 422 (500 emas)."""
    client, _token = auth
    response = client.get("/api/v1/exports/citizens?format=bogus")
    assert response.status_code == 422, (
        f"kutilgan 422, kelgan {response.status_code}: {response.text[:200]}"
    )


def test_module_export_accepts_valid_formats(auth):
    """Ruxsat etilgan formatlar ishlashi kerak."""
    client, _token = auth
    for fmt in ("xlsx", "csv", "docx", "pdf"):
        response = client.get(f"/api/v1/exports/citizens?format={fmt}")
        assert response.status_code == 200, f"{fmt}: {response.text[:200]}"
        assert response.content, f"{fmt}: fayl bo'sh"


def test_module_export_post_rejects_unknown_format(auth):
    """POST eksportda ham noma'lum format — 422."""
    client, token = auth
    response = client.post(
        "/api/v1/exports",
        headers={"X-CSRF-Token": token},
        json={"module": "citizens", "format": "bogus"},
    )
    assert response.status_code == 422, (
        f"kutilgan 422, kelgan {response.status_code}: {response.text[:200]}"
    )


def test_service_export_module_rejects_unknown_format():
    """Service darajasida ham 422 (KeyError/500 emas)."""
    from app.services import documents as service

    with SessionLocal() as db:
        with pytest.raises(APIError) as exc:
            service.export_module(db, "citizens", "bogus", {})
    assert exc.value.status_code == 422, exc.value.status_code


def test_service_export_report_rejects_unknown_format(clean_reports):
    """Service darajasida ham 422."""
    from app.services import reports as report_service

    report_id = _make_report("daily")
    with SessionLocal() as db:
        with pytest.raises(APIError) as exc:
            report_service.export_report(db, report_id, "bogus")
    assert exc.value.status_code == 422, exc.value.status_code


# ------------------------------------------------------------ fayl nomi xavfsizligi


def _disposition_filenames(header: str) -> list[str]:
    names: list[str] = []
    for part in header.split(";"):
        part = part.strip()
        if part.startswith("filename="):
            names.append(part[len("filename=") :].strip('"'))
        elif part.startswith("filename*=UTF-8''"):
            names.append(unquote(part[len("filename*=UTF-8''") :]))
    return names


def test_report_export_filename_has_no_path_separators(auth, clean_reports):
    """Fayl nomida yo'l elementlari bo'lmasligi kerak."""
    client, _token = auth
    report_id = _make_report("../../etc/passwd")
    response = client.get(f"/api/v1/reports/{report_id}/export?format=docx")
    assert response.status_code == 200, response.text[:200]

    header = response.headers.get("content-disposition", "")
    for name in _disposition_filenames(header):
        assert "/" not in name, f"yo'ldan belgi qoldi: {name!r}"
        assert "\\" not in name, f"yo'ldan belgi qoldi: {name!r}"
        assert ".." not in name, f"yo'l elementi qoldi: {name!r}"


def test_report_export_filename_cannot_break_header(auth, clean_reports):
    """Fayl nomi sarlavhani buzmasligi kerak."""
    client, _token = auth
    report_id = _make_report('daily"; filename="butilajak.zip')
    response = client.get(f"/api/v1/reports/{report_id}/export?format=docx")
    assert response.status_code == 200, response.text[:200]

    header = response.headers.get("content-disposition", "")
    assert "\r" not in header and "\n" not in header, "sarlavha buzildi"
    names = _disposition_filenames(header)
    assert names, "fayl nomi topilmadi"
    assert not any(name == "butilajak.zip" for name in names), (
        f"sarlavha inyeksiyasi: {names}"
    )


def test_module_export_filename_has_no_path_separators(auth):
    """Modul nomi fayl nomiga xavfsiz tarzda o'tishi kerak."""
    client, _token = auth
    response = client.get("/api/v1/exports/citizens?format=csv")
    assert response.status_code == 200, response.text[:200]

    header = response.headers.get("content-disposition", "")
    for name in _disposition_filenames(header):
        assert "/" not in name, f"yo'ldan belgi qoldi: {name!r}"
        assert ".." not in name, f"yo'l elementi qoldi: {name!r}"


def test_safe_filename_part_removes_traversal():
    """`safe_filename_part` yo'l elementlarini olib tashlaydi."""
    from app.core.downloads import safe_filename_part

    assert "/" not in safe_filename_part("../../etc/passwd")
    assert ".." not in safe_filename_part("../../etc/passwd")
    assert safe_filename_part("daily") == "daily"
    assert safe_filename_part("") != ""
    assert safe_filename_part("") == "eksport"
