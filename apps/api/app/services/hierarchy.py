from __future__ import annotations


from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.audit import model_snapshot, write_audit
from app.core.errors import conflict, not_found, validation_error
from app.core.pagination import PageMeta, paginate
from app.models import Case, Citizen, Family, House, Mahalla, Street, Task, WorkLog
from app.schemas import FamilyCreate, FamilyUpdate
from app.services.serializers import (
    case_out,
    citizen_out,
    family_out,
    task_out,
    work_log_out,
)


def _family_eager():
    return (
        joinedload(Family.house)
        .joinedload(House.street)
        .joinedload(Street.mahalla)
    )


def list_mahallas(db: Session) -> list[dict]:
    mahallas = db.execute(select(Mahalla).order_by(Mahalla.name)).scalars().all()
    result = []
    for mahalla in mahallas:
        street_ids = db.execute(
            select(Street.id).where(Street.mahalla_id == mahalla.id)
        ).scalars().all()
        house_ids = (
            db.execute(select(House.id).where(House.street_id.in_(street_ids))).scalars().all()
            if street_ids
            else []
        )
        family_ids = (
            db.execute(select(Family.id).where(Family.house_id.in_(house_ids))).scalars().all()
            if house_ids
            else []
        )
        citizen_count = (
            db.execute(
                select(func.count()).select_from(Citizen).where(
                    Citizen.family_id.in_(family_ids), Citizen.archived_at.is_(None)
                )
            ).scalar_one()
            if family_ids
            else 0
        )
        result.append(
            {
                "id": mahalla.id,
                "name": mahalla.name,
                "district": mahalla.district,
                "region": mahalla.region,
                "street_count": len(street_ids),
                "house_count": len(house_ids),
                "family_count": len(family_ids),
                "citizen_count": int(citizen_count),
            }
        )
    return result


def list_streets(db: Session, mahalla_id: str | None = None) -> list[dict]:
    stmt = select(Street).options(joinedload(Street.mahalla)).order_by(Street.name)
    if mahalla_id:
        stmt = stmt.where(Street.mahalla_id == mahalla_id)
    streets = db.execute(stmt).scalars().all()
    result = []
    for street in streets:
        house_ids = db.execute(
            select(House.id).where(House.street_id == street.id)
        ).scalars().all()
        family_ids = (
            db.execute(select(Family.id).where(Family.house_id.in_(house_ids))).scalars().all()
            if house_ids
            else []
        )
        citizen_count = (
            db.execute(
                select(func.count()).select_from(Citizen).where(
                    Citizen.family_id.in_(family_ids), Citizen.archived_at.is_(None)
                )
            ).scalar_one()
            if family_ids
            else 0
        )
        result.append(
            {
                "id": street.id,
                "mahalla_id": street.mahalla_id,
                "name": street.name,
                "house_count": len(house_ids),
                "family_count": len(family_ids),
                "citizen_count": int(citizen_count),
            }
        )
    return result


def get_street(db: Session, street_id: str) -> dict:
    street = db.execute(
        select(Street).options(joinedload(Street.mahalla)).where(Street.id == street_id)
    ).scalar_one_or_none()
    if street is None:
        raise not_found("Ko'cha topilmadi.")
    houses = db.execute(
        select(House).where(House.street_id == street_id).order_by(House.house_number)
    ).scalars().all()
    return {
        "id": street.id,
        "mahalla_id": street.mahalla_id,
        "name": street.name,
        "mahalla": {"id": street.mahalla.id, "name": street.mahalla.name},
        "houses": [house_out(db, house) for house in houses],
    }


def house_out(db: Session, house: House) -> dict:
    family_ids = db.execute(
        select(Family.id).where(Family.house_id == house.id)
    ).scalars().all()
    citizen_count = (
        db.execute(
            select(func.count()).select_from(Citizen).where(
                Citizen.family_id.in_(family_ids), Citizen.archived_at.is_(None)
            )
        ).scalar_one()
        if family_ids
        else 0
    )
    return {
        "id": house.id,
        "street_id": house.street_id,
        "house_number": house.house_number,
        "address_label": house.address_label,
        "family_count": len(family_ids),
        "citizen_count": int(citizen_count),
    }


def list_houses(
    db: Session,
    *,
    street_id: str | None = None,
    mahalla_id: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], PageMeta]:
    stmt = (
        select(House)
        .options(joinedload(House.street).joinedload(Street.mahalla))
        .order_by(House.street_id, House.house_number)
    )
    if street_id:
        stmt = stmt.where(House.street_id == street_id)
    if mahalla_id:
        stmt = stmt.where(House.street.has(Street.mahalla_id == mahalla_id))
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                House.house_number.ilike(term),
                House.address_label.ilike(term),
                House.street.has(Street.name.ilike(term)),
            )
        )
    rows, meta = paginate(db, stmt, page, page_size)
    return [house_out(db, row) for row in rows], meta


def get_house(db: Session, house_id: str) -> dict:
    house = db.execute(
        select(House)
        .options(joinedload(House.street).joinedload(Street.mahalla))
        .where(House.id == house_id)
    ).scalar_one_or_none()
    if house is None:
        raise not_found("Uy topilmadi.")
    families = db.execute(
        select(Family).options(_family_eager()).where(Family.house_id == house_id)
    ).scalars().all()
    return {
        **house_out(db, house),
        "street": {"id": house.street.id, "name": house.street.name},
        "mahalla": {"id": house.street.mahalla.id, "name": house.street.mahalla.name},
        "families": [family_out(item, member_count=_member_count(db, item.id)) for item in families],
    }


def _member_count(db: Session, family_id: str) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(Citizen)
            .where(Citizen.family_id == family_id, Citizen.archived_at.is_(None))
        ).scalar_one()
    )


def list_families(
    db: Session,
    *,
    q: str | None = None,
    house_id: str | None = None,
    street_id: str | None = None,
    mahalla_id: str | None = None,
    family_type: str | None = None,
    social_status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], PageMeta]:
    stmt = (
        select(Family)
        .options(_family_eager(), joinedload(Family.head))
        .order_by(Family.created_at.asc())
    )
    if house_id:
        stmt = stmt.where(Family.house_id == house_id)
    if street_id:
        stmt = stmt.where(Family.house.has(House.street_id == street_id))
    if mahalla_id:
        stmt = stmt.where(Family.house.has(House.street.has(Street.mahalla_id == mahalla_id)))
    if family_type:
        stmt = stmt.where(Family.family_type == family_type)
    if social_status:
        stmt = stmt.where(Family.social_status == social_status)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Family.id.ilike(term),
                Family.notes.ilike(term),
                Family.head.has(Citizen.full_name.ilike(term)),
                Family.house.has(House.address_label.ilike(term)),
            )
        )
    rows, meta = paginate(db, stmt, page, page_size)
    items = [family_out(row, member_count=_member_count(db, row.id)) for row in rows]
    return items, meta


def get_family(db: Session, family_id: str) -> dict:
    family = db.execute(
        select(Family)
        .options(_family_eager(), joinedload(Family.head), selectinload(Family.members))
        .where(Family.id == family_id)
    ).scalar_one_or_none()
    if family is None:
        raise not_found("Oila topilmadi.")
    members = [c for c in family.members if c.archived_at is None]
    member_ids = [m.id for m in members]
    cases = (
        db.execute(
            select(Case)
            .options(joinedload(Case.citizen))
            .where(Case.family_id == family_id)
            .order_by(Case.opened_at.desc())
        ).scalars().all()
        if True
        else []
    )
    tasks = db.execute(
        select(Task).options(joinedload(Task.citizen)).where(Task.family_id == family_id)
    ).scalars().all()
    logs = db.execute(
        select(WorkLog).where(WorkLog.family_id == family_id)
    ).scalars().all()
    data = family_out(family, member_count=len(members))
    data.update(
        {
            "members": [
                citizen_out(member, include_family=False) for member in members
            ],
            "cases": [case_out(item) for item in cases],
            "tasks": [task_out(item) for item in tasks],
            "work_logs": [work_log_out(item) for item in logs],
            "member_ids": member_ids,
        }
    )
    return data


def create_family(db: Session, payload: FamilyCreate, actor: str, request_id: str | None) -> Family:
    house = db.get(House, payload.house_id)
    if house is None:
        raise validation_error("Uy topilmadi.")
    family = Family(
        house_id=payload.house_id,
        family_head_citizen_id=payload.family_head_citizen_id,
        family_type=payload.family_type,
        social_status=payload.social_status,
        notes=payload.notes,
    )
    db.add(family)
    db.flush()
    write_audit(
        db,
        action="family.created",
        entity_type="family",
        entity_id=family.id,
        actor_id=actor,
        new_value=model_snapshot(family),
        request_id=request_id,
    )
    db.commit()
    db.refresh(family)
    return family


def update_family(
    db: Session, family_id: str, payload: FamilyUpdate, actor: str, request_id: str | None
) -> Family:
    family = db.get(Family, family_id)
    if family is None:
        raise not_found("Oila topilmadi.")
    if payload.version is not None and payload.version != family.version:
        raise conflict("Oila ma'lumoti o'zgargan. Sahifani yangilang.")
    before = model_snapshot(family)
    data = payload.model_dump(exclude_unset=True)
    data.pop("version", None)
    for key, value in data.items():
        setattr(family, key, value)
    family.version += 1
    db.flush()
    write_audit(
        db,
        action="family.updated",
        entity_type="family",
        entity_id=family.id,
        actor_id=actor,
        old_value=before,
        new_value=model_snapshot(family),
        request_id=request_id,
    )
    db.commit()
    db.refresh(family)
    return family
