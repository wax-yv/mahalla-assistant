from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import require_csrf_and_permission, require_permission
from app.core.downloads import content_disposition
from app.core.errors import not_found, payload_too_large, validation_error
from app.models import ImportBatch, User
from app.schemas import ExportRequest, ImportCommitRequest, MessageResponse
from app.services import documents as service

router = APIRouter(tags=["documents"])


def _attachment(data: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.get("/documents")
def list_documents(
    kind: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_permission("documents.read")),
):
    rows, meta = service.list_documents(db, kind=kind, q=q, page=page, page_size=page_size)
    return {"items": rows, "meta": meta.model_dump()}


async def _read_upload(request: Request, file: UploadFile) -> bytes:
    """Faylni oqimli o'qib, hajm chegarasini qo'llaydi (O-10).

    Katta fayl butunligi bilan RAM'ga yuklanmasligi kerak — `Content-Length`
    oldindan tekshiriladi, oqim esa chegarani buzsa to'xtatiladi (413).
    """
    limit = settings.max_upload_bytes
    # Multipart body'siz da chegaradan biroz kattaroq bo'ladi — kichik
    # zaxira (64 KB) multipart sarlavhalari uchun.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + 64 * 1024:
        raise payload_too_large(
            f"Fayl hajmi {settings.max_upload_mb} MB dan oshmasligi kerak."
        )
    buffer = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise payload_too_large(
                f"Fayl hajmi {settings.max_upload_mb} MB dan oshmasligi kerak."
            )
    return bytes(buffer)


def _parse_mapping(mapping: str | None) -> dict | None:
    """`mapping` JSON'ini tekshiradi (O-10: noto'g'ri JSON -> 422, 500 emas)."""
    if not mapping:
        return None
    try:
        parsed = json.loads(mapping)
    except json.JSONDecodeError:
        raise validation_error(
            "«mapping» maydoni yaroq JSON emas. JSON formatida yuboring."
        )
    if not isinstance(parsed, dict):
        raise validation_error("«mapping» JSON obyekti bo'lishi kerak.")
    return parsed


@router.post("/documents", status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    analyze: bool = Form(True),
    mapping: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("documents.import")),
):
    data = await _read_upload(request, file)
    parsed_mapping = _parse_mapping(mapping)
    document = service.upload_document(
        db,
        filename=file.filename or "upload.bin",
        data=data,
        content_type=file.content_type or "application/octet-stream",
        actor=user.id,
        request_id=getattr(request.state, "request_id", None),
    )
    payload = {"document": service.document_out(document)}
    if analyze and document.kind in {"xlsx", "csv", "docx"}:
        payload["analysis"] = service.analyze_document(db, document, data, parsed_mapping, user.id)
    return payload


@router.get("/documents/imports")
def list_imports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_permission("documents.read")),
):
    from app.core.pagination import paginate

    rows, meta = paginate(
        db, select(ImportBatch).order_by(ImportBatch.created_at.desc()), page, page_size
    )
    return {
        "items": [service.import_batch_out(db, row) for row in rows],
        "meta": meta.model_dump(),
    }


@router.get("/documents/imports/{batch_id}")
def get_import(
    batch_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_permission("documents.read")),
):
    return service.get_batch_preview(db, batch_id)


@router.post("/documents/imports/{batch_id}/analyze")
def reanalyze_import(
    batch_id: str,
    payload: ImportCommitRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("documents.import")),
):
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise not_found("Import batch topilmadi.")
    document, data = service.get_document_blob(db, batch.document_id)
    mapping = payload.mapping or batch.mapping
    return service.analyze_document(db, document, data, mapping, user.id, sheet=payload.sheet)


@router.post("/documents/imports/{batch_id}/commit")
def commit_import(
    batch_id: str,
    payload: ImportCommitRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("documents.import")),
):
    return service.commit_batch(
        db,
        batch_id,
        actor=user.id,
        mapping=payload.mapping,
        idempotency_key=payload.idempotency_key,
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/documents/imports/{batch_id}/rollback")
def rollback_import(
    batch_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("documents.import")),
):
    return service.rollback_batch(
        db, batch_id, user.id, getattr(request.state, "request_id", None)
    )


@router.get("/exports/{module}")
def export_module_get(
    module: str,
    format: str = Query("xlsx"),
    filters: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_permission("documents.export")),
):
    parsed = json.loads(filters) if filters else {}
    data, filename, media_type = service.export_module(db, module, format, parsed)
    return _attachment(data, filename, media_type)


@router.post("/exports")
def export_module_post(
    payload: ExportRequest,
    db: Session = Depends(get_db),
    _=Depends(require_csrf_and_permission("documents.export")),
):
    data, filename, media_type = service.export_module(
        db, payload.module, payload.format, payload.filters
    )
    return _attachment(data, filename, media_type)


@router.get("/documents/{document_id}")
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_permission("documents.read")),
):
    document = service.get_document(db, document_id)
    return {
        **service.document_out(document),
        "batch": (
            service.import_batch_out(db, document_batch)
            if (document_batch := db.execute(
                select(ImportBatch).where(ImportBatch.document_id == document.id).order_by(ImportBatch.created_at.desc()).limit(1)
            ).scalar_one_or_none())
            else None
        ),
    }


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_permission("documents.read")),
):
    document, data = service.get_document_blob(db, document_id)
    return _attachment(data, document.original_name, document.mime_type)


@router.delete("/documents/{document_id}", response_model=MessageResponse)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("documents.import")),
):
    service.delete_document(db, document_id, user.id)
    return MessageResponse(message="Hujjat arxivlandi.")
