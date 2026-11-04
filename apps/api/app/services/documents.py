from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.audit import model_snapshot, write_audit
from app.core.config import settings
from app.core.errors import bad_request, not_found, validation_error
from app.core.pagination import PageMeta, paginate
from app.core.time import today_local
from app.models import (
    Case,
    Citizen,
    Document,
    DocumentBlob,
    Family,
    House,
    ImportBatch,
    ImportChange,
    ImportError,
    Mahalla,
    Report,
    Street,
    Task,
)
from app.services.serializers import citizen_out, document_out, family_out, task_out

ALLOWED_EXTENSIONS = {".xlsx", ".csv", ".docx", ".pdf"}
MODULE_ALIASES: dict[str, list[str]] = {
    "full_name": ["f.i.sh.", "fish", "f.i.sh", "full_name", "ism", "fuqaro", "fio"],
    "gender": ["jinsi", "gender", "jins"],
    "birth_date": ["tug'ilgan sana", "tugilgan sana", "birth_date", "tug'ilgan"],
    "phone": ["telefon", "phone", "telefon raqami", "tel"],
    "mahalla": ["mahalla", "mahalla nomi"],
    "street": ["ko'cha", "kocha", "street", "ko'cha nomi"],
    "house_number": ["uy raqami", "uy", "house", "house_number"],
    "family_external_id": ["oila id", "oila", "family_id", "family id"],
    "family_role": ["oiladagi o'rni", "oiladagi orni", "family_role", "o'rni"],
    "education": ["ma'lumoti", "malumoti", "education", "ta'lim"],
    "employment_status": ["bandligi", "employment", "employment_status"],
    "profession": ["kasbi", "profession", "kasb"],
    "social_status": ["ijtimoiy holati", "social_status", "ijtimoiy holat"],
    "needs": ["ehtiyoji", "needs", "ehtiyoj"],
    "notes": ["izoh", "notes", "comment"],
    "external_id": ["id", "citizen_id", "fuqaro id"],
    "family_type": ["oila turi", "family_type"],
}

REQUIRED_COLUMNS = ["full_name"]

UNKNOWN = {"", "yo'q", "yoq", "-", "—", "noma'lum"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower()).replace("ʻ", "'").replace("’", "'")


def detect_mapping(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    normalized = {header: normalize_header(header) for header in headers}
    for canonical, aliases in MODULE_ALIASES.items():
        for header, norm in normalized.items():
            if norm in aliases or any(norm == normalize_header(alias) for alias in aliases):
                mapping[canonical] = header
                break
    return mapping


def _detect_kind(name: str, data: bytes) -> str:
    """Formatni kengaytma emas, tarkib bo'yicha aniqlash (MD 9.1)."""
    if data[:4] == b"PK\x03\x04":
        return "xlsx"
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise validation_error(
            "Eski .xls (binary) format qo'llab-quvvatlanmaydi. Faylni Excel'da «.xlsx» sifatida saqlab yuklang."
        )
    sample = data[:4096].lstrip()
    if sample.startswith((b"{", b"[")):
        raise validation_error("JSON fayl qo'llab-quvvatlanmaydi. Ma'lumotni CSV/XLSX ko'rinishida yuklang.")
    try:
        text = data[:2048].decode("utf-8")
        if text.count("\n") >= 1 and ("," in text or ";" in text or "\t" in text):
            return "csv"
    except UnicodeDecodeError:
        pass
    suffix = Path(name).suffix.lower().lstrip(".")
    if suffix in {"xlsx", "csv", "docx", "pdf"}:
        return suffix
    raise validation_error("Fayl formatini aniqlab bo'lmadi. XLSX, CSV, DOCX yoki PDF yuklang.")


def _docx_records(data: bytes, warnings: list[str]) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    from docx import Document as DocxDocument

    doc = DocxDocument(io.BytesIO(data))
    best: tuple[list[str], list[dict[str, Any]]] | None = None
    for table in doc.tables:
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        rows = [row for row in rows if any(cell for cell in row)]
        if len(rows) < 2:
            continue
        if not best or len(rows) > len(best[1]) + 1:
            headers = [str(cell).strip() or f"ustun_{i+1}" for i, cell in enumerate(rows[0])]
            records = [
                {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
                for row in rows[1:]
            ]
            best = (headers, records)
    if best and best[1]:
        warnings.append("DOCX jadvali tahlil qilindi.")
        return best[0], best[1], warnings
    text = "\n".join(paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip())
    return ["matn"], [{"matn": text}], [*warnings, "DOCX faylda jadval topilmadi — matn sifatida saqlanadi."]


def _pdf_records(data: bytes, warnings: list[str]) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise validation_error("PDF fayldan matn ajratib bo'lmadi (skanerlangan rasm bo'lishi mumkin).")
    header_aliases = ("f.i.sh", "fish", "familiya", "ism", "tug'ilgan", "telefon", "jins", "manzil", "uy")
    header_index = -1
    for index, line in enumerate(lines[:30]):
        lowered = line.lower()
        if sum(alias in lowered for alias in header_aliases) >= 2:
            header_index = index
            break
    if header_index >= 0:
        def split_columns(line: str) -> list[str]:
            parts = re.split(r"\s{2,}|\t|\s*\|\s*", line.strip())
            return [part.strip() for part in parts if part.strip()]

        headers = split_columns(lines[header_index])
        records = []
        for line in lines[header_index + 1 :]:
            cells = split_columns(line)
            if not cells or len(cells) < len(headers) - 1:
                continue
            records.append(
                {headers[i]: (cells[i] if i < len(cells) else "") for i in range(len(headers))}
            )
        if records:
            warnings.append(
                f"PDF matnidan {len(records)} ta qator ajratildi. Ustunlar to'g'ri moslashganini tekshiring."
            )
            return headers, records, warnings
    return ["matn"], [{"matn": text}], [*warnings, "PDF faylda jadval strukturasi topilmadi — matn sifatida tahlil qilinadi."]


def _xlsx_sheet_rows(workbook, sheet_name: str) -> list[tuple]:
    target = workbook[sheet_name]
    return list(target.iter_rows(values_only=True))


def _score_sheet(rows: list[tuple]) -> int:
    """Varaq sarlavhalari fuqaro ustunlariga qanchalik mos kelishini baholash."""
    header_row_index = next(
        (index for index, row in enumerate(rows) if any(cell not in (None, "") for cell in row)),
        None,
    )
    if header_row_index is None:
        return -1
    headers = [
        normalize_header(cell) if cell not in (None, "") else ""
        for cell in rows[header_row_index]
    ]
    alias_pool = {alias for aliases in MODULE_ALIASES.values() for alias in aliases}
    alias_pool = {normalize_header(alias) for alias in alias_pool}
    score = 0
    for norm in headers:
        if not norm:
            continue
        if norm in alias_pool:
            score += 2
        elif any(norm in alias or alias in norm for alias in alias_pool):
            score += 1
    return score


def parse_table(
    document: Document, data: bytes, sheet: str | None = None
) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    kind = _detect_kind(document.original_name, data)
    warnings: list[str] = []
    if kind == "xlsx":
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        available = list(workbook.sheetnames)
        requested = sheet or document.meta.get("sheet")
        if requested and requested in available:
            chosen = requested
            warnings.append(f"Varaq tanlandi: «{chosen}»")
        elif len(available) > 1:
            scored = {name: _score_sheet(_xlsx_sheet_rows(workbook, name)) for name in available}
            chosen = max(scored, key=lambda name: scored[name])
            if scored[chosen] <= 0:
                chosen = workbook.sheetnames[0]
            warnings.append(
                f"Fayl {len(available)} varaqdan iborat — eng mosi tanlandi: «{chosen}» "
                f"(mavjud: {', '.join(available)}). Varaqni mapping bo'limidan o'zgartirish mumkin."
            )
        else:
            chosen = available[0]
        rows = _xlsx_sheet_rows(workbook, chosen)
        if not rows:
            raise validation_error("Fayl bo'sh.")
        header_row = next(
            (index for index, row in enumerate(rows) if any(cell not in (None, "") for cell in row)),
            0,
        )
        headers = [str(cell).strip() if cell is not None else f"ustun_{i+1}" for i, cell in enumerate(rows[header_row])]
        records = []
        for row in rows[header_row + 1 :]:
            if not any(cell not in (None, "") for cell in row):
                continue
            records.append(
                {headers[i]: row[i] if i < len(row) else None for i in range(len(headers))}
            )
        return headers, records, warnings
    if kind == "csv":
        for encoding in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise validation_error("CSV kodlashini aniqlab bo'lmadi. UTF-8 formatida yuklang.")
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        headers = [str(header).strip() for header in (reader.fieldnames or [])]
        records = [dict(row) for row in reader if any(v for v in row.values())]
        return headers, records, warnings
    if kind == "docx":
        return _docx_records(data, warnings)
    if kind == "pdf":
        return _pdf_records(data, warnings)
    raise validation_error("Faqat XLSX, CSV, DOCX va PDF fayllar qo'llab-quvvatlanadi.")


def _parse_birth(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and 1 < float(value) < 80000:
        from openpyxl.utils.datetime import from_excel

        try:
            parsed = from_excel(value)
            return parsed.date() if isinstance(parsed, datetime) else parsed
        except Exception:
            return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _clean(value: Any, default: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    return text if text not in UNKNOWN else default


def _normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    if len(digits) == 9:
        digits = "998" + digits
    elif len(digits) == 12 and digits.startswith("998"):
        pass
    elif len(digits) == 12:
        digits = "998" + digits[-9:]
    else:
        # 9 yoki 12 raqamli bo'lmagan har qanday qiymat noto'g'ri hisoblanadi.
        return ""
    return "+" + digits


def _gender(value: Any) -> str:
    text = _clean(value).lower()
    if text in {"ayol", "женщина", "female", "f"}:
        return "Ayol"
    return "Erkak"


def _split_needs(value: Any) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    return [item.strip() for item in re.split(r"[,;/]", text) if item.strip()]


def _family_type_for_role(role: str, family_type: str) -> str:
    if family_type:
        return family_type
    if role in {"Ona"}:
        return "To'liq bo'lmagan oila (ona)"
    if role in {"Ota"}:
        return "To'liq bo'lmagan oila (ota)"
    return "To'liq oila"


def _role(value: Any) -> str:
    text = _clean(value, "Farzand")
    allowed = {"Ota", "Ona", "Farzand", "Bobo", "Buvi", "Aka", "Uka", "Opa", "Singil", "Turmush o'rtoq"}
    return text if text in allowed else "Farzand"


def validate_records(
    db: Session, mapping: dict[str, str], records: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    parsed: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    for index, record in enumerate(records, start=1):
        get = lambda key: record.get(mapping.get(key, "")) if mapping.get(key) else None  # noqa: E731
        full_name = _clean(get("full_name"))
        if not full_name or len(full_name.split()) < 2:
            errors.append(
                {
                    "row_number": index,
                    "column": mapping.get("full_name"),
                    "code": "FULL_NAME_REQUIRED",
                    "message": "F.I.Sh. to'liq bo'lishi shart (kamida ism va familiya).",
                    "raw_value": str(get("full_name") or ""),
                    "severity": "error",
                }
            )
            continue
        raw_birth = get("birth_date")
        cleaned_birth = _clean(raw_birth)  # "—", "-", "yo'q" → ataylab bo'sh
        birth = _parse_birth(raw_birth)
        if cleaned_birth and birth is None:
            errors.append(
                {
                    "row_number": index,
                    "column": mapping.get("birth_date"),
                    "code": "INVALID_BIRTH_DATE",
                    "message": "Tug'ilgan sana noto'g'ri formatda.",
                    "raw_value": str(raw_birth),
                    "severity": "error",
                }
            )
        elif raw_birth not in (None, "") and birth is not None:
            # Noaniq format: 05/03/1990 ham kun/oy, ham oy/kun bo'lishi mumkin.
            text = str(raw_birth).strip() if isinstance(raw_birth, str) else ""
            parsed_variants = []
            for fmt in ("%d/%m/%Y", "%m/%d/%Y"):
                try:
                    parsed_variants.append(datetime.strptime(text, fmt).date())
                except ValueError:
                    continue
            if len(parsed_variants) == 2 and parsed_variants[0] != parsed_variants[1]:
                warnings.append(
                    {
                        "row_number": index,
                        "column": mapping.get("birth_date"),
                        "code": "AMBIGUOUS_DATE",
                        "message": (
                            "Sana noaniq formatda — kun/oy tartibi faraz qilindi: "
                            f"{birth.strftime('%d.%m.%Y')}. Faylda sanalarni DD.MM.YYYY shaklida yozish tavsiya etiladi."
                        ),
                        "raw_value": str(raw_birth),
                        "severity": "warning",
                    }
                )
        elif not cleaned_birth:
            pass  # "—" kabi placeholder — ataylab ko'rsatilmagan, ogohlantirish kerak emas
        if birth and birth > today_local():
            errors.append(
                {
                    "row_number": index,
                    "column": mapping.get("birth_date"),
                    "code": "FUTURE_BIRTH_DATE",
                    "message": "Tug'ilgan sana kelajakda bo'lishi mumkin emas.",
                    "raw_value": str(raw_birth),
                    "severity": "error",
                }
            )
        phone = _normalize_phone(get("phone"))
        raw_phone = _clean(get("phone"))
        if phone:
            pass  # normallashtirildi
        elif raw_phone and not phone:
            warnings.append(
                {
                    "row_number": index,
                    "column": mapping.get("phone"),
                    "code": "INVALID_PHONE",
                    "message": "Telefon raqami noto'g'ri (kamida 9 raqam bo'lishi kerak, masalan +998 90 123 45 67).",
                    "raw_value": raw_phone,
                    "severity": "warning",
                }
            )

        duplicate_key = (full_name, birth.isoformat() if birth else "")
        if duplicate_key in seen_keys:
            warnings.append(
                {
                    "row_number": index,
                    "column": mapping.get("full_name"),
                    "code": "DUPLICATE_IN_FILE",
                    "message": "Fayl ichida bir xil ism va tug'ilgan sana uchradi.",
                    "raw_value": full_name,
                    "severity": "warning",
                }
            )
        seen_keys.add(duplicate_key)
        existing = None
        if phone:
            existing = db.execute(
                select(Citizen).where(Citizen.phone == phone, Citizen.archived_at.is_(None))
            ).scalar_one_or_none()
        if existing is None and birth:
            existing = db.execute(
                select(Citizen).where(
                    Citizen.full_name == full_name,
                    Citizen.birth_date == birth,
                    Citizen.archived_at.is_(None),
                )
            ).scalar_one_or_none()
        if existing is not None:
            warnings.append(
                {
                    "row_number": index,
                    "column": mapping.get("full_name"),
                    "code": "EXISTING_CITIZEN",
                    "message": "Mos fuqaro bazada bor — mavjud yozuv yangilanadi.",
                    "raw_value": f"{existing.id}: {existing.full_name}",
                    "severity": "warning",
                }
            )
        needs = _split_needs(get("needs"))
        parsed.append(
            {
                "row_number": index,
                "existing_id": existing.id if existing else None,
                "external_id": _clean(get("external_id")),
                "full_name": full_name,
                "gender": _gender(get("gender")),
                "birth_date": birth,
                "phone": phone,
                "mahalla": _clean(get("mahalla"), "Mahalla"),
                "street": _clean(get("street"), "Ko'cha"),
                "house_number": _clean(get("house_number"), "1"),
                "family_external_id": _clean(get("family_external_id")),
                "family_role": _role(get("family_role")),
                "education": _clean(get("education"), "O'rta"),
                "employment_status": _clean(get("employment_status"), "Ishlamaydi"),
                "profession": _clean(get("profession"), "Yo'q"),
                "social_status": _clean(get("social_status"), "Yo'q"),
                "needs": needs,
                "notes": _clean(get("notes")),
                "family_type": _clean(get("family_type")),
            }
        )
    summary = {
        "total_rows": len(records),
        "valid_rows": len(parsed),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "will_create": len([row for row in parsed if not row["existing_id"]]),
        "will_update": len([row for row in parsed if row["existing_id"]]),
    }
    return parsed, errors, warnings, summary


def create_import_batch(
    db: Session,
    *,
    document: Document,
    mapping: dict[str, str] | None = None,
    actor: str,
) -> ImportBatch:
    existing = db.execute(
        select(ImportBatch).where(
            ImportBatch.document_id == document.id,
            ImportBatch.status.in_(["uploaded", "mapping", "validated"]),
        )
    ).scalar_one_or_none()
    batch = existing or ImportBatch(document_id=document.id, module="citizens", created_by=actor)
    if existing is None:
        db.add(batch)
    batch.status = "mapping"
    db.flush()
    return batch


def analyze_document(
    db: Session,
    document: Document,
    data: bytes,
    mapping: dict[str, str] | None,
    actor: str,
    sheet: str | None = None,
) -> dict:
    headers, records, parse_warnings = parse_table(document, data, sheet)
    detected = detect_mapping(headers)
    provided = {key: value for key, value in (mapping or {}).items() if value in headers}
    effective = {**detected, **provided}
    batch = create_import_batch(db, document=document, mapping=effective, actor=actor)
    batch.mapping = effective
    db.execute(
        ImportError.__table__.delete().where(ImportError.batch_id == batch.id)
    )
    missing = [col for col in REQUIRED_COLUMNS if col not in effective]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if missing:
        errors.append(
            {
                "row_number": 0,
                "column": None,
                "code": "MISSING_COLUMN",
                "message": "Majburiy ustun topilmadi: F.I.Sh.",
                "raw_value": ", ".join(missing),
                "severity": "error",
            }
        )
        summary = {
            "total_rows": len(records),
            "valid_rows": 0,
            "error_count": 1,
            "warning_count": 0,
        }
        parsed: list[dict] = []
    else:
        parsed, errors, warnings, summary = validate_records(db, effective, records)
    for item in parse_warnings:
        warnings.append(
            {
                "row_number": 0,
                "column": None,
                "code": "PARSE_NOTE",
                "message": item,
                "raw_value": None,
                "severity": "warning",
            }
        )
    for item in errors + warnings:
        db.add(
            ImportError(
                batch_id=batch.id,
                row_number=item["row_number"],
                column=item.get("column"),
                code=item["code"],
                message=item["message"],
                raw_value=item.get("raw_value"),
                severity=item["severity"],
            )
        )
    batch.status = "validated" if not errors else "failed"
    batch.error_count = len(errors)
    batch.warning_count = len(warnings)
    batch.summary = summary
    chosen_sheet = None
    available_sheets = None
    for warning in parse_warnings:
        if warning.startswith("Varaq tanlandi:") or "eng mosi tanlandi:" in warning:
            match = re.search(r"«(.+?)»", warning)
            if match:
                chosen_sheet = match.group(1)
        if "mavjud:" in warning:
            match_list = re.search(r"mavjud: (.+?)\)", warning)
            if match_list:
                available_sheets = [item.strip() for item in match_list.group(1).split(",")]
    if chosen_sheet is None:
        chosen_sheet = document.meta.get("sheet")
    if available_sheets is None:
        available_sheets = document.meta.get("available_sheets") or ([chosen_sheet] if chosen_sheet else None)
    document.status = "parsed"
    document.meta = {
        **(document.meta or {}),
        "headers": headers,
        "detected_module": "citizens",
        "preview": parsed[:5],
        "row_count": len(records),
        "sheet": chosen_sheet,
        "available_sheets": available_sheets,
    }
    db.flush()
    write_audit(
        db,
        action="document.analyzed",
        entity_type="document",
        entity_id=document.id,
        actor_id=actor,
        new_value={"batch_id": batch.id, "summary": summary},
    )
    db.commit()
    return build_preview(db, batch, headers, parsed, errors, warnings)


def build_preview(
    db: Session,
    batch: ImportBatch,
    headers: list[str],
    parsed: list[dict],
    errors: list[dict],
    warnings: list[dict],
) -> dict:
    meta = (batch.document.meta or {}) if batch.document else {}
    return {
        "batch": import_batch_out(db, batch),
        "headers": headers,
        "sheet": meta.get("sheet"),
        "available_sheets": meta.get("available_sheets") or ([meta.get("sheet")] if meta.get("sheet") else []),
        "mapping": batch.mapping,
        "detected_module": "citizens",
        "preview_rows": parsed[:20],
        "errors": [
            {
                "id": f"new-{index}",
                "row_number": item["row_number"],
                "column": item.get("column"),
                "code": item["code"],
                "message": item["message"],
                "raw_value": item.get("raw_value"),
                "severity": item["severity"],
            }
            for index, item in enumerate(errors)
        ],
        "warnings": [
            {
                "id": f"warn-{index}",
                "row_number": item["row_number"],
                "column": item.get("column"),
                "code": item["code"],
                "message": item["message"],
                "raw_value": item.get("raw_value"),
                "severity": item["severity"],
            }
            for index, item in enumerate(warnings)
        ],
        "summary": batch.summary,
        "can_commit": batch.status == "validated" and not errors,
    }


def import_batch_out(db: Session, batch: ImportBatch) -> dict:
    return {
        "id": batch.id,
        "document_id": batch.document_id,
        "module": batch.module,
        "status": batch.status,
        "mapping": batch.mapping or {},
        "summary": batch.summary or {},
        "error_count": batch.error_count,
        "warning_count": batch.warning_count,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
        "committed_at": batch.committed_at,
        "rolled_back_at": batch.rolled_back_at,
    }


def get_batch_preview(db: Session, batch_id: str) -> dict:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise not_found("Import batch topilmadi.")
    document = db.get(Document, batch.document_id)
    if document is None:
        raise not_found("Hujjat topilmadi.")
    blob = db.get(DocumentBlob, document.id)
    if blob is None:
        raise not_found("Fayl mazmuni topilmadi.")
    headers, records, parse_warnings = parse_table(document, blob.data, (document.meta or {}).get("sheet"))
    parsed, errors, warnings, summary = validate_records(db, batch.mapping or {}, records)
    for item in parse_warnings:
        warnings.append(
            {
                "row_number": 0,
                "column": None,
                "code": "PARSE_NOTE",
                "message": item,
                "raw_value": None,
                "severity": "warning",
            }
        )
    return build_preview(db, batch, headers, parsed, errors, warnings)


def _get_or_create(db: Session, model, filters: dict, defaults: dict, created: list[dict]):
    instance = db.execute(select(model).filter_by(**filters)).scalar_one_or_none()
    if instance is not None:
        return instance
    instance = model(**filters, **defaults)
    db.add(instance)
    db.flush()
    created.append(
        {"entity_type": model.__tablename__, "entity_id": instance.id, "action": "create"}
    )
    return instance


def commit_batch(
    db: Session,
    batch_id: str,
    *,
    actor: str,
    mapping: dict[str, str] | None = None,
    idempotency_key: str | None = None,
    request_id: str | None = None,
) -> dict:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise not_found("Import batch topilmadi.")
    if batch.status == "committed":
        return {"batch": import_batch_out(db, batch), "created": 0, "updated": 0, "skipped": 0}
    if batch.status not in {"validated", "mapping", "uploaded", "failed"}:
        raise bad_request("Bu importni yakunlash mumkin emas.")
    if idempotency_key:
        existing = db.execute(
            select(ImportBatch).where(ImportBatch.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing and existing.id != batch.id:
            raise bad_request("Bu idempotency kaliti allaqachon ishlatilgan.")
        batch.idempotency_key = idempotency_key
    if mapping:
        batch.mapping = {**batch.mapping, **mapping}
    document = db.get(Document, batch.document_id)
    blob = db.get(DocumentBlob, document.id) if document else None
    if document is None or blob is None:
        raise not_found("Import fayli topilmadi.")
    headers, records, _ = parse_table(document, blob.data, (document.meta or {}).get("sheet"))
    parsed, errors, warnings, summary = validate_records(db, batch.mapping or {}, records)
    if errors:
        batch.status = "failed"
        batch.summary = summary
        batch.error_count = len(errors)
        db.commit()
        raise validation_error(
            "Import oldidan xatolar mavjud. Xatolarni tuzating yoki validatsiyani qayta ishga tushiring.",
            [item["message"] for item in errors[:10]],
        )
    created: list[dict] = []
    changes = 0
    updates = 0
    mahalla_cache: dict[str, Mahalla] = {}
    street_cache: dict[tuple[str, str], Street] = {}
    house_cache: dict[tuple[str, str], House] = {}
    family_cache: dict[tuple[str, str], Family] = {}
    for row in parsed:
        mahalla = _get_or_create(
            db,
            Mahalla,
            {"name": row["mahalla"]},
            {"district": "Urganch shahri", "region": "Xorazm viloyati"},
            created,
        )
        street = _get_or_create(
            db,
            Street,
            {"mahalla_id": mahalla.id, "name": row["street"]},
            {},
            created,
        )
        house = _get_or_create(
            db,
            House,
            {"street_id": street.id, "house_number": row["house_number"]},
            {"address_label": f"{mahalla.name}, {street.name}, {row['house_number']}-uy"},
            created,
        )
        family_key = (house.id, row["family_external_id"] or f"{row['full_name']}|{row['house_number']}")
        if family_key not in family_cache:
            family = db.execute(
                select(Family).where(
                    Family.house_id == house.id,
                    (Family.id == row["family_external_id"])
                    if row["family_external_id"]
                    else Family.notes == f"import:{family_key[1]}",
                )
            ).scalar_one_or_none()
            if family is None:
                family = Family(
                    house_id=house.id,
                    family_type=_family_type_for_role(row["family_role"], row["family_type"]),
                    social_status=row["social_status"],
                    notes=f"import:{family_key[1]}",
                )
                db.add(family)
                db.flush()
                created.append(
                    {"entity_type": "families", "entity_id": family.id, "action": "create"}
                )
            family_cache[family_key] = family
        family = family_cache[family_key]
        existing = db.get(Citizen, row["existing_id"]) if row["existing_id"] else None
        if existing is None and row["phone"]:
            existing = db.execute(
                select(Citizen).where(Citizen.phone == row["phone"], Citizen.archived_at.is_(None))
            ).scalar_one_or_none()
        if existing is None:
            existing = db.execute(
                select(Citizen).where(
                    Citizen.full_name == row["full_name"],
                    Citizen.birth_date == row["birth_date"],
                    Citizen.archived_at.is_(None),
                )
            ).scalar_one_or_none()
        if existing is None:
            citizen = Citizen(
                full_name=row["full_name"],
                gender=row["gender"],
                birth_date=row["birth_date"],
                phone=row["phone"],
                family_id=family.id,
                family_role=row["family_role"],
                education=row["education"],
                employment_status=row["employment_status"],
                profession=row["profession"],
                social_status=row["social_status"],
                needs=row["needs"],
                needs_text=", ".join(row["needs"]),
                notes=row["notes"],
                data_source=document.original_name,
                last_verified_at=datetime.now(timezone.utc),
            )
            db.add(citizen)
            db.flush()
            row["_created_citizen"] = citizen
            created.append(
                {"entity_type": "citizens", "entity_id": citizen.id, "action": "create"}
            )
            changes += 1
        else:
            before = model_snapshot(existing)
            existing.full_name = row["full_name"]
            existing.gender = row["gender"]
            existing.birth_date = row["birth_date"]
            existing.phone = row["phone"] or existing.phone
            existing.family_id = family.id
            existing.family_role = row["family_role"]
            existing.education = row["education"]
            existing.employment_status = row["employment_status"]
            existing.profession = row["profession"]
            existing.social_status = row["social_status"]
            existing.needs = row["needs"]
            existing.needs_text = ", ".join(row["needs"])
            existing.notes = row["notes"]
            existing.data_source = document.original_name
            existing.last_verified_at = datetime.now(timezone.utc)
            existing.version += 1
            db.flush()
            db.add(
                ImportChange(
                    batch_id=batch.id,
                    entity_type="citizen",
                    entity_id=existing.id,
                    action="update",
                    before=before,
                    after=model_snapshot(existing),
                )
            )
            updates += 1
        if family.family_head_citizen_id is None and row["family_role"] in {"Ota", "Ona", "Bobo", "Buvi"}:
            head = existing if existing is not None else row.get("_created_citizen")
            if head is not None:
                family.family_head_citizen_id = head.id
    for item in created:
        db.add(
            ImportChange(
                batch_id=batch.id,
                entity_type=item["entity_type"],
                entity_id=item["entity_id"],
                action=item["action"],
                before=None,
                after=item,
            )
        )
    batch.status = "committed"
    batch.summary = {
        **summary,
        "created": changes,
        "updated": updates,
        "committed_at": datetime.now(timezone.utc).isoformat(),
    }
    batch.committed_at = datetime.now(timezone.utc)
    document.status = "committed"
    db.flush()
    write_audit(
        db,
        action="document.imported",
        entity_type="import_batch",
        entity_id=batch.id,
        actor_id=actor,
        new_value={"created": changes, "updated": updates, "batch": batch.id},
        request_id=request_id,
    )
    db.commit()
    return {
        "batch": import_batch_out(db, batch),
        "created": changes,
        "updated": updates,
        "skipped": 0,
    }


def rollback_batch(db: Session, batch_id: str, actor: str, request_id: str | None) -> dict:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise not_found("Import batch topilmadi.")
    if batch.status != "committed":
        raise bad_request("Faqat yakunlangan importni qaytarish mumkin.")
    changes = db.execute(
        select(ImportChange).where(ImportChange.batch_id == batch.id)
    ).scalars().all()
    deleted = 0
    restored = 0
    for change in reversed(changes):
        if change.entity_type == "citizen" and change.action == "update" and change.before:
            citizen = db.get(Citizen, change.entity_id)
            if citizen:
                for key, value in change.before.items():
                    if hasattr(citizen, key):
                        setattr(citizen, key, value)
                restored += 1
        elif change.action == "create":
            model_map = {
                "citizens": Citizen,
                "families": Family,
                "houses": House,
                "streets": Street,
                "mahallas": Mahalla,
            }
            model = model_map.get(change.entity_type)
            if model is not None:
                instance = db.get(model, change.entity_id)
                if instance is not None:
                    try:
                        db.delete(instance)
                        db.flush()
                        deleted += 1
                    except Exception:
                        db.rollback()
    batch.status = "rolled_back"
    batch.rolled_back_at = datetime.now(timezone.utc)
    document = db.get(Document, batch.document_id)
    if document:
        document.status = "validated"
    db.flush()
    write_audit(
        db,
        action="document.import_rolled_back",
        entity_type="import_batch",
        entity_id=batch.id,
        actor_id=actor,
        new_value={"deleted": deleted, "restored": restored},
        request_id=request_id,
    )
    db.commit()
    return {"batch": import_batch_out(db, batch), "deleted": deleted, "restored": restored}


def upload_document(
    db: Session,
    *,
    filename: str,
    data: bytes,
    content_type: str,
    actor: str,
    request_id: str | None,
) -> Document:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise validation_error("Faqat .xlsx, .csv, .docx va .pdf fayllar qabul qilinadi.")
    if len(data) > settings.max_upload_bytes:
        raise validation_error(f"Fayl hajmi {settings.max_upload_mb} MB dan oshmasligi kerak.")
    if not data:
        raise validation_error("Fayl bo'sh.")
    digest = sha256_bytes(data)
    existing = db.execute(
        select(Document).where(Document.content_hash == digest, Document.status != "archived")
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    document = Document(
        filename=f"{digest[:12]}{suffix}",
        original_name=filename,
        mime_type=content_type or "application/octet-stream",
        size=len(data),
        content_hash=digest,
        storage_backend="database",
        storage_key=None,
        kind=suffix.lstrip("."),
        status="uploaded",
        uploaded_by=actor,
        meta={},
    )
    db.add(document)
    db.flush()
    db.add(DocumentBlob(document_id=document.id, data=data))
    db.flush()
    write_audit(
        db,
        action="document.uploaded",
        entity_type="document",
        entity_id=document.id,
        actor_id=actor,
        new_value={"filename": filename, "size": len(data)},
        request_id=request_id,
    )
    db.commit()
    return document


def list_documents(
    db: Session, *, kind: str | None = None, q: str | None = None, page: int = 1, page_size: int = 20
) -> tuple[list[dict], PageMeta]:
    stmt = select(Document).where(Document.status != "archived").order_by(Document.created_at.desc())
    if kind:
        stmt = stmt.where(Document.kind == kind)
    if q:
        stmt = stmt.where(
            or_(Document.original_name.ilike(f"%{q}%"), Document.id.ilike(f"%{q}%"))
        )
    rows, meta = paginate(db, stmt, page, page_size)
    return [document_out(row) for row in rows], meta


def get_document(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise not_found("Hujjat topilmadi.")
    return document


def get_document_blob(db: Session, document_id: str) -> tuple[Document, bytes]:
    document = get_document(db, document_id)
    blob = db.get(DocumentBlob, document_id)
    if blob is None:
        raise not_found("Fayl mazmuni topilmadi.")
    return document, blob.data


def delete_document(db: Session, document_id: str, actor: str) -> Document:
    document = get_document(db, document_id)
    document.status = "archived"
    db.flush()
    write_audit(
        db,
        action="document.archived",
        entity_type="document",
        entity_id=document.id,
        actor_id=actor,
    )
    db.commit()
    return document


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _citizen_rows(db: Session, filters: dict[str, Any]) -> list[list[Any]]:
    stmt = select(Citizen).options(
        joinedload(Citizen.family).joinedload(Family.house).joinedload(House.street)
    ).where(Citizen.archived_at.is_(None))
    if filters.get("street_id"):
        stmt = stmt.where(Citizen.family.has(Family.house.has(House.street_id == filters["street_id"])))
    if filters.get("family_id"):
        stmt = stmt.where(Citizen.family_id == filters["family_id"])
    if filters.get("employment_status"):
        stmt = stmt.where(Citizen.employment_status == filters["employment_status"])
    if filters.get("social_status"):
        stmt = stmt.where(Citizen.social_status == filters["social_status"])
    rows = db.execute(stmt.order_by(Citizen.full_name)).scalars().all()
    output = []
    for row in rows:
        data = citizen_out(row)
        address = data.get("address") or {}
        output.append(
            [
                row.id,
                row.full_name,
                row.gender,
                row.birth_date.isoformat() if row.birth_date else "",
                row.phone,
                address.get("mahalla", ""),
                address.get("street", ""),
                address.get("house_number", ""),
                row.family_id or "",
                row.family_role,
                row.education,
                row.employment_status,
                row.profession,
                row.social_status,
                ", ".join(row.needs or []),
                row.notes,
            ]
        )
    return output


def _headers_for(module: str) -> list[str]:
    return {
        "citizens": [
            "ID", "F.I.Sh.", "Jinsi", "Tug'ilgan sana", "Telefon", "Mahalla",
            "Ko'cha", "Uy raqami", "Oila ID", "Oiladagi o'rni", "Ma'lumoti",
            "Bandligi", "Kasbi", "Ijtimoiy holati", "Ehtiyoji", "Izoh",
        ],
        "families": ["ID", "Uy", "Oila rahbari", "Oila turi", "Ijtimoiy holat", "A'zolar soni"],
        "houses": ["ID", "Ko'cha", "Uy raqami", "Manzil", "Oilalar"],
        "tasks": ["ID", "Sarlavha", "Fuqaro", "Kategoriya", "Ustuvorlik", "Holat", "Muddat", "Mas'ul"],
        "cases": ["ID", "Sarlavha", "Fuqaro", "Kategoriya", "Holat", "Ustuvorlik", "Ochilgan"],
    }.get(module, ["ID", "Nomi"])


def _module_rows(db: Session, module: str, filters: dict[str, Any]) -> list[list[Any]]:
    if module == "citizens":
        return _citizen_rows(db, filters)
    if module == "families":
        rows = db.execute(
            select(Family)
            .options(joinedload(Family.house).joinedload(House.street), joinedload(Family.head))
            .order_by(Family.id)
        ).scalars().all()
        return [
            [
                row.id,
                f"{row.house.street.name}, {row.house.house_number}-uy" if row.house else "",
                row.head.full_name if row.head else "",
                row.family_type,
                row.social_status,
                db.execute(select(func.count()).select_from(Citizen).where(Citizen.family_id == row.id)).scalar_one(),
            ]
            for row in rows
        ]
    if module == "houses":
        rows = db.execute(
            select(House).options(joinedload(House.street).joinedload(Street.mahalla)).order_by(House.id)
        ).scalars().all()
        return [
            [
                row.id,
                row.street.name,
                row.house_number,
                row.address_label,
                db.execute(select(func.count()).select_from(Family).where(Family.house_id == row.id)).scalar_one(),
            ]
            for row in rows
        ]
    if module == "tasks":
        rows = db.execute(select(Task).options(joinedload(Task.citizen)).order_by(Task.created_at.desc())).scalars().all()
        return [
            [
                row.id, row.title, row.citizen.full_name if row.citizen else "",
                row.category, row.priority, row.status,
                row.due_date.isoformat() if row.due_date else "", row.assignee or "",
            ]
            for row in rows
        ]
    if module == "cases":
        rows = db.execute(select(Case).options(joinedload(Case.citizen)).order_by(Case.opened_at.desc())).scalars().all()
        return [
            [
                row.id, row.title, row.citizen.full_name if row.citizen else "",
                row.category, row.status, row.priority, row.opened_at.date().isoformat(),
            ]
            for row in rows
        ]
    return []


def export_module(db: Session, module: str, fmt: str, filters: dict[str, Any]) -> tuple[bytes, str, str]:
    headers = _headers_for(module)
    rows = _module_rows(db, module, filters)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    safe = {"xlsx": "xlsx", "csv": "csv", "docx": "docx", "pdf": "pdf"}[fmt]
    name = f"{module}-{stamp}.{safe}"
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(rows)
        return buffer.getvalue().encode("utf-8-sig"), name, "text/csv"
    if fmt == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = {
            "citizens": "Fuqarolar",
            "families": "Oilalar",
            "houses": "Uylar",
            "tasks": "Vazifalar",
            "cases": "Case'lar",
        }.get(module, "Eksport")
        header_fill = PatternFill("solid", fgColor="1F3D2E")
        header_font = Font(color="F7F3E8", bold=True)
        thin = Side(style="thin", color="D8D2C2")
        for column_index, title in enumerate(headers, start=1):
            cell = sheet.cell(row=1, column=column_index, value=title)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(vertical="center")
        for row_index, row in enumerate(rows, start=2):
            for column_index, value in enumerate(row, start=1):
                cell = sheet.cell(row=row_index, column=column_index, value=value)
                cell.border = Border(bottom=thin)
                cell.alignment = Alignment(vertical="top", wrap_text=False)
        widths = [12, 30, 10, 14, 16, 22, 26, 12, 16, 20, 18, 16, 24, 22, 28, 30]
        for index in range(len(headers)):
            sheet.column_dimensions[get_column_letter(index + 1)].width = widths[index] if index < len(widths) else 18
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue(), name, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if fmt == "docx":
        from docx import Document as DocxDocument
        from docx.shared import Pt

        doc = DocxDocument()
        doc.add_heading("Mahalla Assistant — eksport", level=1)
        doc.add_paragraph(
            f"Yo'nalish: {module}. Yaratilgan: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} (UTC)."
        )
        table = doc.add_table(rows=1, cols=len(headers))
        table.style = "Light Grid Accent 1"
        for index, title in enumerate(headers):
            table.rows[0].cells[index].text = title
        for row in rows[:2000]:
            cells = table.add_row().cells
            for index, value in enumerate(row):
                cells[index].text = "" if value is None else str(value)
        doc.add_paragraph("")
        doc.add_paragraph("Ushbu hujjat Mahalla Assistant tizimi tomonidan avtomatik shakllantirildi.")
        buffer = io.BytesIO()
        doc.save(buffer)
        return buffer.getvalue(), name, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if fmt == "pdf":
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), title="Mahalla Assistant eksport")
        styles = getSampleStyleSheet()
        story = [
            Paragraph("Mahalla Assistant — eksport", styles["Title"]),
            Paragraph(
                f"Yo'nalish: {module} · {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC",
                styles["Normal"],
            ),
            Spacer(1, 12),
        ]
        cell_style = styles["BodyText"]
        cell_style.fontSize = 7
        cell_style.leading = 9
        data = [[Paragraph(str(title), cell_style) for title in headers]]
        for row in rows[:600]:
            data.append([Paragraph("" if value is None else str(value), cell_style) for value in row])
        table = Table(data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3D2E")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#F7F3E8")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D8D2C2")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F3E8")]),
                ]
            )
        )
        story.append(table)
        doc.build(story)
        return buffer.getvalue(), name, "application/pdf"
    raise validation_error("Format qo'llab-quvvatlanmaydi.")


def export_citizens_csv(db: Session) -> bytes:
    data, _, _ = export_module(db, "citizens", "csv", {})
    return data
