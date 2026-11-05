from __future__ import annotations

import csv
import io
from datetime import date

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import Citizen, Report

MALICIOUS_NAME = "=cmd|' /C calc'!A0 O15sinov"
MALICIOUS_NOTE = "@SUM(1+1)*cmd|' /C calc'!A0"
TEST_MARKER = "O15sinov"

@pytest.fixture()
def clean_rows():
    def _cleanup():
        with SessionLocal() as db:
            ids = db.execute(
                select(Citizen.id).where(Citizen.full_name.like(f"%{TEST_MARKER}%"))
            ).scalars().all()
            if ids:
                db.execute(delete(Citizen).where(Citizen.id.in_(ids)))
            db.execute(delete(Report).where(Report.title.like(f"%{TEST_MARKER}%")))
            db.commit()

    _cleanup()
    yield
    _cleanup()

def _make_citizen() -> str:
    with SessionLocal() as db:
        citizen = Citizen(
            full_name=MALICIOUS_NAME,
            gender="Erkak",
            birth_date=date(1990, 1, 1),
            phone="+998901234567",
            notes=MALICIOUS_NOTE,
        )
        db.add(citizen)
        db.flush()
        citizen_id = citizen.id
        db.commit()
        return citizen_id

def _make_report(narrative: str) -> str:
    with SessionLocal() as db:
        report = Report(
            type="daily",
            period_start=date(2024, 5, 1),
            period_end=date(2024, 5, 31),
            filters={},
            status="draft",
            title=f"{TEST_MARKER} hisobot",
            summary="",
            metrics={},
            narrative=narrative,
            sources=[],
            created_by="tester",
        )
        db.add(report)
        db.flush()
        report_id = report.id
        db.commit()
        return report_id

def test_safe_cell_escapes_every_formula_prefix():
    from app.core.downloads import safe_cell

    for prefix in ("=", "+", "-", "@", "\t", "\r"):
        value = f"{prefix}cmd|' /C calc'!A0"
        result = safe_cell(value)
        assert isinstance(result, str), type(result)
        assert result.startswith("'"), f"niqolanmadi: {prefix!r} -> {result!r}"
        assert result[1:] == value, f"qiymat o'zgarib ketdi: {result!r}"

def test_safe_cell_keeps_inner_formula_char():
    from app.core.downloads import safe_cell

    assert safe_cell("O15 sinov =1+1") == "O15 sinov =1+1"
    assert safe_cell("Alisher Karimov") == "Alisher Karimov"
    assert safe_cell("Telefon: +998 90 123 45 67") == "Telefon: +998 90 123 45 67"

def test_safe_cell_keeps_numbers_numeric():
    from app.core.downloads import safe_cell

    assert safe_cell(5) == 5
    assert isinstance(safe_cell(5), int)
    assert safe_cell(12.5) == 12.5
    assert safe_cell(None) == ""

def test_safe_cell_keeps_dates_as_dates():
    from app.core.downloads import safe_cell

    value = date(1990, 5, 15)
    assert safe_cell(value) == value

def test_csv_export_escapes_formula_in_name(clean_rows):
    from app.services import documents as service

    citizen_id = _make_citizen()
    with SessionLocal() as db:
        data, _name, _mime = service.export_module(db, "citizens", "csv", {})

    text = data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    header = rows[0]
    name_index = header.index("F.I.Sh.")
    note_index = header.index("Izoh")

    matched = [row for row in rows[1:] if row[0] == citizen_id]
    assert matched, "test fuqaro eksportda topilmadi"
    row = matched[0]
    assert row[name_index].startswith("'"), f"F.I.Sh. niqolanmadi: {row[name_index]!r}"
    assert row[name_index][1:] == MALICIOUS_NAME
    assert row[note_index].startswith("'"), f"Izoh niqolanmadi: {row[note_index]!r}"

def test_csv_export_keeps_plain_names_intact(clean_rows):
    from app.services import documents as service

    with SessionLocal() as db:
        citizen = Citizen(
            full_name="O15sinov Alisher Karimov",
            gender="Erkak",
            phone="+998901234567",
        )
        db.add(citizen)
        db.flush()
        citizen_id = citizen.id
        db.commit()

    with SessionLocal() as db:
        data, _name, _mime = service.export_module(db, "citizens", "csv", {})
    text = data.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    name_index = rows[0].index("F.I.Sh.")
    matched = [row for row in rows[1:] if row[0] == citizen_id]
    assert matched
    assert matched[0][name_index] == "O15sinov Alisher Karimov"

def test_export_citizens_csv_helper_is_safe(clean_rows):
    from app.services import documents as service

    citizen_id = _make_citizen()
    with SessionLocal() as db:
        data = service.export_citizens_csv(db)
    text = data.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    name_index = rows[0].index("F.I.Sh.")
    matched = [row for row in rows[1:] if row[0] == citizen_id]
    assert matched
    assert matched[0][name_index].startswith("'")

def test_xlsx_export_does_not_write_formula(clean_rows):
    from openpyxl import load_workbook

    from app.services import documents as service

    citizen_id = _make_citizen()
    with SessionLocal() as db:
        data, _name, _mime = service.export_module(db, "citizens", "xlsx", {})

    workbook = load_workbook(io.BytesIO(data))
    sheet = workbook.active
    header = [cell.value for cell in sheet[1]]
    name_index = header.index("F.I.Sh.")
    note_index = header.index("Izoh")

    target = None
    for row in sheet.iter_rows(min_row=2):
        if row[0].value == citizen_id:
            target = row
            break
    assert target is not None, "test fuqaro eksportda topilmadi"

    for index in (name_index, note_index):
        cell = target[index]
        assert cell.data_type != "f", f"formula yozildi: {cell.value!r}"
        assert not str(cell.value).startswith("="), f"formula boshlandi: {cell.value!r}"
        assert str(cell.value).startswith("'"), f"niqolanmadi: {cell.value!r}"

def test_xlsx_export_keeps_numeric_cells_numeric(clean_rows):
    from openpyxl import load_workbook

    from app.services import documents as service

    with SessionLocal() as db:
        data, _name, _mime = service.export_module(db, "families", "xlsx", {})

    workbook = load_workbook(io.BytesIO(data))
    sheet = workbook.active
    header = [cell.value for cell in sheet[1]]
    count_index = header.index("A'zolar soni")
    numeric = [
        row[count_index]
        for row in sheet.iter_rows(min_row=2)
        if isinstance(row[count_index].value, int)
    ]
    assert numeric, "sonlar ustuni raqam sifatida saqlanmadi"

def test_report_export_does_not_write_formula(clean_rows):
    from openpyxl import load_workbook

    from app.services import reports as report_service

    report_id = _make_report(f"{MALICIOUS_NAME}\n\nIkkinchi paragraf.")
    with SessionLocal() as db:
        data, _name, _mime = report_service.export_report(db, report_id, "xlsx")

    workbook = load_workbook(io.BytesIO(data))
    sheet = workbook.active
    formulas = [
        cell.value
        for row in sheet.iter_rows()
        for cell in row
        if cell.data_type == "f"
    ]
    assert not formulas, f"formulalar yozildi: {formulas}"

def test_report_export_keeps_plain_narrative(clean_rows):
    from openpyxl import load_workbook

    from app.services import reports as report_service

    report_id = _make_report("Oddiy xulosa matni.")
    with SessionLocal() as db:
        data, _name, _mime = report_service.export_report(db, report_id, "xlsx")

    workbook = load_workbook(io.BytesIO(data))
    sheet = workbook.active
    values = [cell.value for row in sheet.iter_rows() for cell in row]
    assert "Oddiy xulosa matni." in values, values
