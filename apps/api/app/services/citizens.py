from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.audit import model_snapshot, write_audit
from app.core.errors import bad_request, conflict, not_found, validation_error
from app.core.pagination import PageMeta, paginate
from app.core.time import age_from_birth, today_local
from app.models import AuditLog, Case, Citizen, Document, Family, House, Street, Task, WorkLog
from app.schemas import CitizenCreate, CitizenUpdate
from app.services.serializers import (
    address_for_citizen,
    case_out,
    citizen_out,
    document_out,
    task_out,
    work_log_out,
)

REQUIRED_FIELDS: dict[str, str] = {
    "full_name": "F.I.Sh.",
    "birth_date": "Tug'ilgan sana",
    "phone": "Telefon",
    "family_id": "Oila",
    "education": "Ma'lumoti",
    "employment_status": "Bandligi",
}


def years_ago(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def citizen_quality(citizen: Citizen, duplicate_risk: str = "low") -> dict:
    missing = []
    filled = 0
    for field, label in REQUIRED_FIELDS.items():
        value = getattr(citizen, field, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(label)
        else:
            filled += 1
    score = round(filled / len(REQUIRED_FIELDS) * 100)
    if score == 100:
        note = "Ma'lumotlar to'liq."
    elif score >= 67:
        note = "Ba'zi maydonlar yetishmaydi."
    else:
        note = "Ma'lumotlar sezilarli darajada to'liq emas."
    return {
        "score": score,
        "missing_fields": missing,
        "duplicate_risk": duplicate_risk,
        "notes": note,
    }


def duplicate_risk_for(db: Session, citizen: Citizen) -> str:
    conditions = []
    if citizen.phone:
        conditions.append(Citizen.phone == citizen.phone)
    if citizen.full_name and citizen.birth_date:
        conditions.append(
            and_(Citizen.full_name == citizen.full_name, Citizen.birth_date == citizen.birth_date)
        )
    if not conditions:
        return "low"
    count = int(
        db.execute(
            select(func.count())
            .select_from(Citizen)
            .where(Citizen.id != citizen.id, or_(*conditions))
        ).scalar_one()
    )
    if count >= 2:
        return "high"
    if count == 1:
        return "medium"
    return "low"


def _eager_options():
    return (
        selectinload(Citizen.family)
        .selectinload(Family.house)
        .selectinload(House.street)
        .selectinload(Street.mahalla)
    )


def _detail_options():
    return (
        joinedload(Citizen.family)
        .joinedload(Family.house)
        .joinedload(House.street)
        .joinedload(Street.mahalla)
    )


def list_citizens(
    db: Session,
    *,
    q: str | None = None,
    mahalla_id: str | None = None,
    street_id: str | None = None,
    house_id: str | None = None,
    family_id: str | None = None,
    gender: str | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
    employment_status: str | None = None,
    education: str | None = None,
    profession: str | None = None,
    social_status: str | None = None,
    needs: str | None = None,
    data_quality: str | None = None,
    updated_since: date | None = None,
    include_archived: bool = False,
    sort: str = "full_name",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], PageMeta]:
    stmt = select(Citizen).options(_eager_options())
    conditions = []

    if not include_archived:
        conditions.append(Citizen.archived_at.is_(None))
    if q:
        term = f"%{q.strip()}%"
        conditions.append(
            or_(
                Citizen.full_name.ilike(term),
                Citizen.id.ilike(term),
                Citizen.phone.ilike(term),
                Citizen.profession.ilike(term),
            )
        )
    if family_id:
        conditions.append(Citizen.family_id == family_id)
    if house_id:
        conditions.append(Citizen.family.has(Family.house_id == house_id))
    if street_id:
        conditions.append(Citizen.family.has(Family.house.has(House.street_id == street_id)))
    if mahalla_id:
        conditions.append(
            Citizen.family.has(Family.house.has(House.street.has(Street.mahalla_id == mahalla_id)))
        )
    if gender:
        conditions.append(Citizen.gender == gender)
    today = today_local()
    if age_min is not None:
        conditions.append(Citizen.birth_date.is_not(None))
        conditions.append(Citizen.birth_date <= years_ago(today, age_min))
    if age_max is not None:
        conditions.append(Citizen.birth_date.is_not(None))
        conditions.append(Citizen.birth_date >= years_ago(today, age_max + 1) + timedelta(days=1))
    if employment_status:
        conditions.append(Citizen.employment_status == employment_status)
    if education:
        conditions.append(Citizen.education == education)
    if profession:
        conditions.append(Citizen.profession.ilike(f"%{profession}%"))
    if social_status:
        conditions.append(Citizen.social_status == social_status)
    if needs:
        conditions.append(Citizen.needs_text.ilike(f"%{needs}%"))
    if data_quality == "complete":
        conditions.extend(
            [
                Citizen.full_name != "",
                Citizen.birth_date.is_not(None),
                Citizen.phone != "",
                Citizen.family_id.is_not(None),
                Citizen.education != "",
                Citizen.employment_status != "",
            ]
        )
    elif data_quality == "incomplete":
        conditions.append(
            or_(
                Citizen.full_name == "",
                Citizen.birth_date.is_(None),
                Citizen.phone == "",
                Citizen.family_id.is_(None),
                Citizen.education == "",
                Citizen.employment_status == "",
            )
        )
    if updated_since:
        conditions.append(Citizen.updated_at >= datetime.combine(updated_since, datetime.min.time(), tzinfo=timezone.utc))

    if conditions:
        stmt = stmt.where(*conditions)

    sort_map = {
        "full_name": Citizen.full_name,
        "birth_date": Citizen.birth_date,
        "updated_at": Citizen.updated_at,
        "created_at": Citizen.created_at,
        "id": Citizen.id,
        "employment_status": Citizen.employment_status,
        "social_status": Citizen.social_status,
    }
    descending = sort.startswith("-")
    column = sort_map.get(sort.lstrip("-"), Citizen.full_name)
    stmt = stmt.order_by(column.desc() if descending else column.asc(), Citizen.id.asc())

    rows, meta = paginate(db, stmt, page, page_size)
    items = [
        citizen_out(
            row,
            quality=citizen_quality(row),
            duplicate_risk="low",
            include_family=False,
        )
        for row in rows
    ]
    return items, meta


def get_citizen(db: Session, citizen_id: str) -> Citizen:
    citizen = db.execute(
        select(Citizen).options(_detail_options()).where(Citizen.id == citizen_id)
    ).scalar_one_or_none()
    if citizen is None:
        raise not_found("Fuqaro topilmadi.")
    return citizen


def family_member_count(db: Session, family_id: str | None) -> int:
    if not family_id:
        return 0
    return int(
        db.execute(
            select(func.count())
            .select_from(Citizen)
            .where(Citizen.family_id == family_id, Citizen.archived_at.is_(None))
        ).scalar_one()
    )


def get_citizen_detail(db: Session, citizen_id: str) -> dict:
    citizen = get_citizen(db, citizen_id)
    quality = citizen_quality(citizen, duplicate_risk_for(db, citizen))
    member_count = family_member_count(db, citizen.family_id)

    cases = db.execute(
        select(Case)
        .options(joinedload(Case.citizen))
        .where(Case.citizen_id == citizen_id)
        .order_by(Case.opened_at.desc())
    ).scalars().all()
    tasks = db.execute(
        select(Task)
        .options(joinedload(Task.citizen))
        .where(Task.citizen_id == citizen_id)
        .order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())
    ).scalars().all()
    logs = db.execute(
        select(WorkLog)
        .where(WorkLog.citizen_id == citizen_id)
        .order_by(WorkLog.occurred_at.desc())
    ).scalars().all()
    documents = db.execute(
        select(Document)
        .where(Document.meta.op("->>")("citizen_id") == citizen_id)
        .order_by(Document.created_at.desc())
    ).scalars().all()
    audit_rows = db.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == "citizen", AuditLog.entity_id == citizen_id)
        .order_by(AuditLog.created_at.desc())
        .limit(50)
    ).scalars().all()

    timeline: list[dict] = []
    for case in cases:
        timeline.append(
            {
                "id": f"case-open-{case.id}",
                "kind": "case",
                "title": case.title,
                "description": case.description,
                "occurred_at": case.opened_at,
                "status": case.status,
                "entity_type": "case",
                "entity_id": case.id,
                "source": "database",
            }
        )
        if case.closed_at:
            timeline.append(
                {
                    "id": f"case-close-{case.id}",
                    "kind": "natija",
                    "title": f"Case yopildi: {case.title}",
                    "description": case.outcome,
                    "occurred_at": case.closed_at,
                    "status": case.status,
                    "entity_type": "case",
                    "entity_id": case.id,
                    "source": "database",
                }
            )
    for task in tasks:
        timeline.append(
            {
                "id": f"task-{task.id}",
                "kind": "vazifa",
                "title": task.title,
                "description": task.description,
                "occurred_at": task.created_at,
                "status": task.status,
                "entity_type": "task",
                "entity_id": task.id,
                "source": "database",
            }
        )
        if task.completed_at:
            timeline.append(
                {
                    "id": f"task-done-{task.id}",
                    "kind": "bajarilgan ish",
                    "title": f"Vazifa bajarildi: {task.title}",
                    "description": task.evidence_note,
                    "occurred_at": task.completed_at,
                    "status": "completed",
                    "entity_type": "task",
                    "entity_id": task.id,
                    "source": "database",
                }
            )
    for log in logs:
        timeline.append(
            {
                "id": f"log-{log.id}",
                "kind": log.type,
                "title": log.title,
                "description": log.description,
                "occurred_at": log.occurred_at,
                "status": log.approval_status,
                "entity_type": "work_log",
                "entity_id": log.id,
                "source": log.source,
            }
        )
    for audit in audit_rows:
        timeline.append(
            {
                "id": f"audit-{audit.id}",
                "kind": "o'zgarish",
                "title": audit.action,
                "description": "",
                "occurred_at": audit.created_at,
                "status": audit.result,
                "entity_type": "audit",
                "entity_id": audit.id,
                "source": "audit",
            }
        )
    timeline.sort(key=lambda item: item["occurred_at"], reverse=True)

    data = citizen_out(
        citizen,
        quality=quality,
        duplicate_risk=quality["duplicate_risk"],
        include_family=True,
        family_member_count=member_count,
    )
    data.update(
        {
            "cases": [case_out(item, task_count=0) for item in cases],
            "tasks": [task_out(item) for item in tasks],
            "work_logs": [work_log_out(item) for item in logs],
            "documents": [document_out(item) for item in documents],
            "timeline": timeline,
            "audit_history": [
                {
                    "id": row.id,
                    "actor_type": row.actor_type,
                    "actor_id": row.actor_id,
                    "action": row.action,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "old_value": row.old_value,
                    "new_value": row.new_value,
                    "request_id": row.request_id,
                    "workflow_id": row.workflow_id,
                    "source": row.source,
                    "ip": row.ip,
                    "result": row.result,
                    "created_at": row.created_at,
                }
                for row in audit_rows
            ],
        }
    )
    return data


def next_citizen_id(db: Session) -> str:
    max_id = db.execute(select(func.max(Citizen.id))).scalar_one()
    if not max_id:
        return "F-00001"
    try:
        number = int(str(max_id).split("-")[1]) + 1
    except (IndexError, ValueError):
        number = 1
    return f"F-{number:05d}"


def _validate_citizen_payload(db: Session, data: dict) -> None:
    birth_date = data.get("birth_date")
    if birth_date:
        if birth_date > today_local():
            raise validation_error("Tug'ilgan sana kelajakda bo'lishi mumkin emas.")
        if age_from_birth(birth_date) and age_from_birth(birth_date) > 120:
            raise validation_error("Tug'ilgan sana yosh chegarasidan tashqarida.")
    family_id = data.get("family_id")
    if family_id:
        family = db.get(Family, family_id)
        if family is None:
            raise validation_error("Ko'rsatilgan oila mavjud emas.")


def create_citizen(db: Session, payload: CitizenCreate, actor: str, request_id: str | None = None) -> Citizen:
    data = payload.model_dump()
    _validate_citizen_payload(db, data)
    citizen = Citizen(
        id=next_citizen_id(db),
        **{k: v for k, v in data.items() if k != "needs"},
        needs=list(payload.needs or []),
        needs_text=", ".join(payload.needs or []),
        data_source="manual",
        last_verified_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(citizen)
    db.flush()

    if citizen.family_id and citizen.family_role in {"Ota", "Ona", "Bobo", "Buvi"}:
        family = db.get(Family, citizen.family_id)
        if family and not family.family_head_citizen_id:
            family.family_head_citizen_id = citizen.id
            db.flush()

    write_audit(
        db,
        action="citizen.created",
        entity_type="citizen",
        entity_id=citizen.id,
        actor_id=actor,
        new_value=model_snapshot(citizen),
        request_id=request_id,
    )
    db.commit()
    db.refresh(citizen)
    return citizen


def update_citizen(
    db: Session,
    citizen_id: str,
    payload: CitizenUpdate,
    actor: str,
    request_id: str | None = None,
) -> Citizen:
    citizen = get_citizen(db, citizen_id)
    # D-1: versiya majburiy — eskirgan yozuv ustidan yozish rad etiladi.
    if payload.version != citizen.version:
        raise conflict(
            "Ma'lumot siz ko'rganingizdan keyin o'zgargan. Sahifani yangilab qayta urinib ko'ring."
        )
    data = payload.model_dump(exclude_unset=True)
    data.pop("version", None)
    _validate_citizen_payload(db, data)
    before = model_snapshot(citizen)

    old_family_id = citizen.family_id
    for key, value in data.items():
        if key == "needs":
            citizen.needs = list(value or [])
            citizen.needs_text = ", ".join(value or [])
        else:
            setattr(citizen, key, value)
    if "needs" not in data:
        citizen.needs_text = ", ".join(citizen.needs or [])
    citizen.version += 1
    citizen.last_verified_at = datetime.now(timezone.utc)
    citizen.updated_at = datetime.now(timezone.utc)

    if old_family_id and old_family_id != citizen.family_id:
        old_family = db.get(Family, old_family_id)
        if old_family and old_family.family_head_citizen_id == citizen.id:
            old_family.family_head_citizen_id = None
    if citizen.family_id and citizen.family_role in {"Ota", "Ona", "Bobo", "Buvi"}:
        family = db.get(Family, citizen.family_id)
        if family and not family.family_head_citizen_id:
            family.family_head_citizen_id = citizen.id

    db.flush()
    write_audit(
        db,
        action="citizen.updated",
        entity_type="citizen",
        entity_id=citizen.id,
        actor_id=actor,
        old_value=before,
        new_value=model_snapshot(citizen),
        request_id=request_id,
    )
    db.commit()
    db.refresh(citizen)
    return citizen


def archive_citizen(db: Session, citizen_id: str, actor: str, request_id: str | None = None) -> Citizen:
    citizen = get_citizen(db, citizen_id)
    if citizen.archived_at is not None:
        raise bad_request("Fuqaro allaqachon arxivlangan.")
    before = model_snapshot(citizen)
    citizen.archived_at = datetime.now(timezone.utc)
    citizen.version += 1
    if citizen.family_id:
        family = db.get(Family, citizen.family_id)
        if family and family.family_head_citizen_id == citizen.id:
            family.family_head_citizen_id = None
    db.flush()
    write_audit(
        db,
        action="citizen.archived",
        entity_type="citizen",
        entity_id=citizen.id,
        actor_id=actor,
        old_value=before,
        new_value=model_snapshot(citizen),
        request_id=request_id,
    )
    db.commit()
    return citizen


def citizen_address(db: Session, citizen: Citizen) -> dict | None:
    return address_for_citizen(citizen)
