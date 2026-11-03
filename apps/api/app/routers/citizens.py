from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_csrf_and_permission, require_permission
from app.models import User
from app.schemas import CitizenCreate, CitizenUpdate, MessageResponse
from app.services import citizens as service

router = APIRouter(prefix="/citizens", tags=["citizens"])


@router.get("")
def list_citizens(
    q: str | None = None,
    mahalla_id: str | None = None,
    street_id: str | None = None,
    house_id: str | None = None,
    family_id: str | None = None,
    gender: str | None = None,
    age_min: int | None = Query(None, ge=0, le=120),
    age_max: int | None = Query(None, ge=0, le=120),
    employment_status: str | None = None,
    education: str | None = None,
    profession: str | None = None,
    social_status: str | None = None,
    needs: str | None = None,
    data_quality: str | None = None,
    updated_since: date | None = None,
    include_archived: bool = False,
    sort: str = "full_name",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_permission("citizens.read")),
):
    rows, meta = service.list_citizens(
        db,
        q=q,
        mahalla_id=mahalla_id,
        street_id=street_id,
        house_id=house_id,
        family_id=family_id,
        gender=gender,
        age_min=age_min,
        age_max=age_max,
        employment_status=employment_status,
        education=education,
        profession=profession,
        social_status=social_status,
        needs=needs,
        data_quality=data_quality,
        updated_since=updated_since,
        include_archived=include_archived,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return {"items": rows, "meta": meta.model_dump()}


@router.get("/options")
def citizen_options(db: Session = Depends(get_db), _=Depends(require_permission("citizens.read"))):
    rows = service.list_citizens(db, page=1, page_size=100)
    return {
        "items": [
            {
                "id": item["id"],
                "full_name": item["full_name"],
                "phone": item.get("phone"),
                "address": item.get("address"),
            }
            for item in rows[0]
        ]
    }


@router.get("/{citizen_id}")
def get_citizen(
    citizen_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_permission("citizens.read")),
):
    return service.get_citizen_detail(db, citizen_id)


@router.post("", status_code=201)
def create_citizen(
    payload: CitizenCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("citizens.create")),
):
    citizen = service.create_citizen(db, payload, user.id, getattr(request.state, "request_id", None))
    return service.get_citizen_detail(db, citizen.id)


@router.patch("/{citizen_id}")
def update_citizen(
    citizen_id: str,
    payload: CitizenUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("citizens.update")),
):
    service.update_citizen(
        db, citizen_id, payload, user.id, getattr(request.state, "request_id", None)
    )
    return service.get_citizen_detail(db, citizen_id)


@router.delete("/{citizen_id}", response_model=MessageResponse)
def archive_citizen(
    citizen_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("citizens.archive")),
):
    service.archive_citizen(db, citizen_id, user.id, getattr(request.state, "request_id", None))
    return MessageResponse(message="Fuqaro arxivlandi.")
