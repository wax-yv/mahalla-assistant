from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_csrf_and_permission, require_permission
from app.models import User
from app.schemas import ChatRequest
from app.services import agents as service

router = APIRouter(prefix="/agents", tags=["agents"])


class ConversationCreate(BaseModel):
    title: str = Field(default="Yangi suhbat", max_length=200)


class DraftDecision(BaseModel):
    note: str = ""


@router.post("/chat")
def chat(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("agents.use")),
):
    result = service.chat(
        db,
        message=payload.message,
        conversation_id=payload.conversation_id,
        actor=user.id,
        request_id=getattr(request.state, "request_id", None),
        preferred_provider=payload.provider,
        preferred_model=payload.model,
    )
    draft_rows = result.pop("draft_actions", [])
    result["draft_actions"] = [service._draft_out(row) for row in draft_rows]
    result["message"] = {
        "id": result["message"].id,
        "conversation_id": result["message"].conversation_id,
        "role": result["message"].role,
        "content": result["message"].content,
        "agent": result["message"].agent,
        "workflow_id": result["message"].workflow_id,
        "sources": result["message"].sources or [],
        "draft_actions": [
            service._draft_out(row) for row in draft_rows
        ],
        "created_at": result["message"].created_at,
    }
    return result


@router.get("/conversations")
def conversations(
    limit: int = Query(40, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_permission("agents.use")),
):
    return {"items": service.list_conversations(db, limit=limit)}


@router.post("/conversations", status_code=201)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    _=Depends(require_csrf_and_permission("agents.use")),
):
    row = service.create_conversation(db, payload.title)
    return {
        "id": row.id,
        "title": row.title,
        "archived_at": row.archived_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "message_count": 0,
        "last_message": None,
    }


@router.get("/conversations/{conversation_id}")
def conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_permission("agents.use")),
):
    return service.get_conversation(db, conversation_id)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    purge: bool = False,
    db: Session = Depends(get_db),
    _=Depends(require_csrf_and_permission("agents.use")),
):
    if purge:
        return service.delete_conversation(db, conversation_id)
    row = service.archive_conversation(db, conversation_id)
    return {"ok": True, "id": row.id}


@router.get("/drafts")
def drafts(
    status: str | None = "pending",
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_permission("agents.use")),
):
    return {"items": service.list_drafts(db, status=status, limit=limit)}


@router.post("/drafts/{draft_id}/approve")
def approve_draft(
    draft_id: str,
    payload: DraftDecision,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("agents.use")),
):
    return service.decide_draft(
        db,
        draft_id,
        approve=True,
        actor=user.id,
        request_id=getattr(request.state, "request_id", None),
        note=payload.note,
    )


@router.post("/drafts/{draft_id}/reject")
def reject_draft(
    draft_id: str,
    payload: DraftDecision,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("agents.use")),
):
    return service.decide_draft(
        db,
        draft_id,
        approve=False,
        actor=user.id,
        request_id=getattr(request.state, "request_id", None),
        note=payload.note,
    )


@router.get("/workflows")
def workflows(
    limit: int = Query(50, ge=1, le=100),
    status: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_permission("agents.use")),
):
    return {"items": service.list_workflows(db, limit=limit, status_filter=status)}


@router.get("/workflows/{workflow_id}")
def workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_permission("agents.use")),
):
    return service.get_workflow(db, workflow_id)


@router.get("/status")
def status(db: Session = Depends(get_db), _=Depends(require_permission("agents.use"))):
    return service.agent_status(db)
