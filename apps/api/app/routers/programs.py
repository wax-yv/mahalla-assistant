from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_permission
from app.schemas import ProgramCompareRequest, ProgramMatchRequest
from app.services import programs as service

router = APIRouter(prefix="/programs", tags=["programs"])


@router.get("")
def list_programs(
    q: str | None = None,
    type: str | None = None,
    organization: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_permission("reports.read")),
):
    return {"items": service.list_programs(db, q=q, type=type, organization=organization)}


@router.get("/organizations")
def organizations(db: Session = Depends(get_db), _=Depends(require_permission("reports.read"))):
    return {"items": service.organizations(db)}


@router.get("/preference/{conversation_id}")
def preference(
    conversation_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_permission("agents.use")),
):
    return {"preference": service.get_preference(db, conversation_id)}


@router.post("/match")
def match(
    payload: ProgramMatchRequest,
    db: Session = Depends(get_db),
    _=Depends(require_permission("reports.read")),
):
    return {"items": service.match_citizen(db, payload.citizen_id, payload.program_id)}


@router.post("/compare")
def compare(
    payload: ProgramCompareRequest,
    db: Session = Depends(get_db),
    _=Depends(require_permission("reports.read")),
):
    return {"items": service.compare(db, payload.program_ids)}


@router.get("/{program_id}")
def get_program(
    program_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_permission("reports.read")),
):
    return service.get_program(db, program_id)
