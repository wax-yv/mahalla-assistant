from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_csrf_and_permission, require_permission
from app.models import User
from app.schemas import FamilyCreate, FamilyUpdate
from app.services import hierarchy as service

router = APIRouter(tags=["hierarchy"])

@router.get("/mahallas")
def mahallas(db: Session = Depends(get_db), _=Depends(require_permission("families.read"))):
    return {"items": service.list_mahallas(db)}

@router.get("/streets")
def streets(
    mahalla_id: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_permission("families.read")),
):
    return {"items": service.list_streets(db, mahalla_id)}

@router.get("/streets/{street_id}")
def street(
    street_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_permission("families.read")),
):
    return service.get_street(db, street_id)

@router.get("/houses")
def houses(
    street_id: str | None = None,
    mahalla_id: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_permission("families.read")),
):
    rows, meta = service.list_houses(
        db, street_id=street_id, mahalla_id=mahalla_id, q=q, page=page, page_size=page_size
    )
    return {"items": rows, "meta": meta.model_dump()}

@router.get("/houses/{house_id}")
def house(
    house_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_permission("families.read")),
):
    return service.get_house(db, house_id)

@router.get("/families")
def families(
    q: str | None = None,
    house_id: str | None = None,
    street_id: str | None = None,
    mahalla_id: str | None = None,
    family_type: str | None = None,
    social_status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_permission("families.read")),
):
    rows, meta = service.list_families(
        db,
        q=q,
        house_id=house_id,
        street_id=street_id,
        mahalla_id=mahalla_id,
        family_type=family_type,
        social_status=social_status,
        page=page,
        page_size=page_size,
    )
    return {"items": rows, "meta": meta.model_dump()}

@router.get("/families/{family_id}")
def family(
    family_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_permission("families.read")),
):
    return service.get_family(db, family_id)

@router.post("/families", status_code=201)
def create_family(
    payload: FamilyCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("families.update")),
):
    row = service.create_family(db, payload, user.id, getattr(request.state, "request_id", None))
    return service.get_family(db, row.id)

@router.patch("/families/{family_id}")
def update_family(
    family_id: str,
    payload: FamilyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_and_permission("families.update")),
):
    service.update_family(
        db, family_id, payload, user.id, getattr(request.state, "request_id", None)
    )
    return service.get_family(db, family_id)
