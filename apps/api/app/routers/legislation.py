from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_csrf_and_permission, require_permission
from app.models import User
from app.schemas import LegislationSyncRequest
from app.services import legislation as service

router = APIRouter(prefix="/legislation", tags=["legislation"])


class LegislationQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    use_ai: bool = True
    # J-13: so'rov yo'lida avtomatik sinxron o'chirilgan. Sinxron faqat
    # foydalanuvchi aniq so'raganda (`/legislation/sync`) bajariladi.
    sync_if_empty: bool = False


@router.get("/documents")
def list_documents(
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _=Depends(require_permission("reports.read")),
):
    return {"items": service.list_documents(db, q=q, limit=limit)}


@router.get("/status")
def status(db: Session = Depends(get_db), _=Depends(require_permission("reports.read"))):
    return service.status(db)


@router.get("/documents/{document_id}")
def document(
    document_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_permission("reports.read")),
):
    return service.document_detail(db, document_id)


@router.get("/search")
def search(
    q: str = Query(min_length=2, max_length=300),
    limit: int = Query(8, ge=1, le=30),
    db: Session = Depends(get_db),
    _=Depends(require_permission("reports.read")),
):
    return {"items": service.search_chunks(db, q, limit=limit)}


@router.post("/ask")
def ask(
    payload: LegislationQuestion,
    db: Session = Depends(get_db),
    _=Depends(require_csrf_and_permission("agents.use")),
):
    return service.ask(
        db,
        payload.question,
        use_ai=payload.use_ai,
        sync_if_empty=payload.sync_if_empty,
    )


@router.post("/sync")
def sync(
    payload: LegislationSyncRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("agents.use")),
):
    if payload.url:
        document = service.ingest_document(db, payload.url, actor=user.id)
        return {"documents": [service.document_detail(db, document.id)["document"]], "live": True}
    if not payload.query:
        from app.core.errors import validation_error

        raise validation_error("Qidiruv so'zi yoki hujjat URL manzilini kiriting.")
    documents = service.sync_query(
        db,
        payload.query,
        limit=max(1, min(10, payload.limit)),
        actor=user.id,
    )
    return {
        "documents": [
            service.document_detail(db, document.id)["document"] for document in documents
        ],
        "live": True,
    }


@router.post("/search-live")
def search_live(
    payload: LegislationQuestion,
    db: Session = Depends(get_db),
    _=Depends(require_csrf_and_permission("agents.use")),
):
    return {"items": service.search_lex(payload.question, limit=10)}
