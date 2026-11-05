from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.audit import model_snapshot, write_audit
from app.core.constants import CASE_TRANSITIONS, TASK_TRANSITIONS
from app.core.errors import bad_request, conflict, not_found, validation_error
from app.core.pagination import PageMeta, paginate
from app.core.search import like_pattern
from app.core.time import today_local
from app.models import Case, Citizen, Family, Task, WorkLog
from app.schemas import (
    CaseCreate,
    CaseUpdate,
    TaskCompleteRequest,
    TaskCreate,
    TaskUpdate,
    WorkLogCreate,
)
from app.services.serializers import case_out, task_out, work_log_out


def _case_options():
    return joinedload(Case.citizen)


def _task_options():
    return joinedload(Task.citizen)


def list_cases(
    db: Session,
    *,
    q: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    citizen_id: str | None = None,
    family_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], PageMeta]:
    stmt = select(Case).options(_case_options()).order_by(Case.opened_at.desc())
    if status:
        stmt = stmt.where(Case.status == status)
    if priority:
        stmt = stmt.where(Case.priority == priority)
    if category:
        stmt = stmt.where(Case.category == category)
    if citizen_id:
        stmt = stmt.where(Case.citizen_id == citizen_id)
    if family_id:
        stmt = stmt.where(Case.family_id == family_id)
    if q:
        term = like_pattern(q.strip())
        stmt = stmt.where(
            or_(
                Case.title.ilike(term, escape="\\"),
                Case.description.ilike(term, escape="\\"),
                Case.id.ilike(term, escape="\\"),
            )
        )
    rows, meta = paginate(db, stmt, page, page_size)
    counts = _task_counts(db, [row.id for row in rows])
    return [case_out(row, counts.get(row.id, 0)) for row in rows], meta


def _task_counts(db: Session, case_ids: list[str]) -> dict[str, int]:
    if not case_ids:
        return {}
    rows = db.execute(
        select(Task.case_id, func.count())
        .where(Task.case_id.in_(case_ids))
        .group_by(Task.case_id)
    ).all()
    return {row[0]: int(row[1]) for row in rows}


def get_case(db: Session, case_id: str) -> dict:
    case = db.execute(
        select(Case).options(_case_options()).where(Case.id == case_id)
    ).scalar_one_or_none()
    if case is None:
        raise not_found("Case topilmadi.")
    tasks = db.execute(
        select(Task).options(_task_options()).where(Task.case_id == case_id)
    ).scalars().all()
    logs = db.execute(
        select(WorkLog).where(WorkLog.case_id == case_id).order_by(WorkLog.occurred_at.desc())
    ).scalars().all()
    data = case_out(case, len(tasks))
    data["tasks"] = [task_out(item) for item in tasks]
    data["work_logs"] = [work_log_out(item) for item in logs]
    return data


def create_case(
    db: Session,
    payload: CaseCreate,
    actor: str,
    request_id: str | None,
    *,
    commit: bool = True,
) -> Case:
    if payload.citizen_id and db.get(Citizen, payload.citizen_id) is None:
        raise validation_error("Fuqaro topilmadi.")
    if payload.family_id and db.get(Family, payload.family_id) is None:
        raise validation_error("Oila topilmadi.")
    case = Case(
        **payload.model_dump(),
        created_by=actor,
        opened_at=datetime.now(timezone.utc),
    )
    db.add(case)
    db.flush()
    write_audit(
        db,
        action="case.created",
        entity_type="case",
        entity_id=case.id,
        actor_id=actor,
        new_value=model_snapshot(case),
        request_id=request_id,
    )
    if commit:
        db.commit()
        db.refresh(case)
    return case


def update_case(
    db: Session, case_id: str, payload: CaseUpdate, actor: str, request_id: str | None
) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise not_found("Case topilmadi.")
    # D-1: versiya majburiy.
    if payload.version != case.version:
        raise conflict("Case ma'lumoti o'zgargan. Sahifani yangilang.")
    data = payload.model_dump(exclude_unset=True)
    data.pop("version", None)
    new_status = data.get("status")
    # O-5: `before` o'zgarishlardan **OLDIN** olinadi — aks holda audit yozuvida
    # "eski holat = yangi holat" ko'rinardi.
    before = model_snapshot(case)
    if new_status and new_status != case.status:
        if new_status not in CASE_TRANSITIONS.get(case.status, set()):
            raise bad_request(
                f"Case holatini '{case.status}' dan '{new_status}' ga o'zgartirish mumkin emas."
            )
        case.status = new_status
        # N-9: `resolved` — hal qilingan, lekin **yopilmagan** case. Yopish
        # sanasi faqat `closed`/`cancelled` holatlarida belgilanadi; aks
        # holda hisobotlarda "yopilgan" deb hisoblanib ketardi.
        case.closed_at = (
            datetime.now(timezone.utc) if new_status in {"closed", "cancelled"} else None
        )
        data.pop("status")
    for key, value in data.items():
        setattr(case, key, value)
    case.version += 1
    db.flush()
    write_audit(
        db,
        action="case.updated",
        entity_type="case",
        entity_id=case.id,
        actor_id=actor,
        old_value=before,
        new_value=model_snapshot(case),
        request_id=request_id,
    )
    db.commit()
    db.refresh(case)
    return case


def list_tasks(
    db: Session,
    *,
    q: str | None = None,
    status: str | None = None,
    statuses: list[str] | None = None,
    priority: str | None = None,
    category: str | None = None,
    citizen_id: str | None = None,
    family_id: str | None = None,
    case_id: str | None = None,
    assignee: str | None = None,
    timeframe: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], PageMeta]:
    stmt = select(Task).options(_task_options()).order_by(
        Task.due_date.asc().nullslast(), Task.created_at.desc()
    )
    today = today_local()
    if status:
        stmt = stmt.where(Task.status == status)
    if statuses:
        stmt = stmt.where(Task.status.in_(statuses))
    if priority:
        stmt = stmt.where(Task.priority == priority)
    if category:
        stmt = stmt.where(Task.category == category)
    if citizen_id:
        stmt = stmt.where(Task.citizen_id == citizen_id)
    if family_id:
        stmt = stmt.where(Task.family_id == family_id)
    if case_id:
        stmt = stmt.where(Task.case_id == case_id)
    if assignee:
        stmt = stmt.where(Task.assignee == assignee)
    if timeframe == "today":
        stmt = stmt.where(Task.due_date == today, Task.status.notin_(["completed", "cancelled"]))
    elif timeframe == "tomorrow":
        stmt = stmt.where(
            Task.due_date == today + timedelta(days=1),
            Task.status.notin_(["completed", "cancelled"]),
        )
    elif timeframe == "week":
        stmt = stmt.where(
            Task.due_date >= today,
            Task.due_date <= today + timedelta(days=7),
            Task.status.notin_(["completed", "cancelled"]),
        )
    elif timeframe == "overdue":
        stmt = stmt.where(
            Task.due_date < today, Task.status.notin_(["completed", "cancelled"])
        )
    elif timeframe == "completed":
        stmt = stmt.where(Task.status == "completed")
    if q:
        term = like_pattern(q.strip())
        stmt = stmt.where(
            or_(
                Task.title.ilike(term, escape="\\"),
                Task.description.ilike(term, escape="\\"),
                Task.id.ilike(term, escape="\\"),
            )
        )
    rows, meta = paginate(db, stmt, page, page_size)
    return [task_out(row) for row in rows], meta


def get_task(db: Session, task_id: str) -> dict:
    task = db.execute(
        select(Task).options(_task_options()).where(Task.id == task_id)
    ).scalar_one_or_none()
    if task is None:
        raise not_found("Vazifa topilmadi.")
    logs = db.execute(
        select(WorkLog).where(WorkLog.task_id == task_id).order_by(WorkLog.occurred_at.desc())
    ).scalars().all()
    data = task_out(task)
    data["work_logs"] = [work_log_out(item) for item in logs]
    return data


def create_task(
    db: Session,
    payload: TaskCreate,
    actor: str,
    request_id: str | None,
    *,
    commit: bool = True,
) -> Task:
    citizen = None
    if payload.citizen_id:
        citizen = db.get(Citizen, payload.citizen_id)
        if citizen is None:
            raise validation_error("Fuqaro topilmadi.")
    family = None
    if payload.family_id:
        family = db.get(Family, payload.family_id)
        if family is None:
            raise validation_error("Oila topilmadi.")
    case = None
    if payload.case_id:
        case = db.get(Case, payload.case_id)
        if case is None:
            raise validation_error("Case topilmadi.")
    # O-6: vazifa, case va fuqaro bir-biriga tegishli bo'lishi kerak —
    # aks holda case X fuqarosi va task Y fuqarosi bo'lib qolardi.
    if case is not None:
        if (
            payload.citizen_id
            and case.citizen_id
            and payload.citizen_id != case.citizen_id
        ):
            raise validation_error(
                "Vazifa fuqarosi case'ga biriktirilgan fuqaro bilan mos kelishi kerak."
            )
        if payload.family_id and case.family_id and payload.family_id != case.family_id:
            raise validation_error(
                "Vazifa oilasi case'ga biriktirilgan oila bilan mos kelishi kerak."
            )
        if not payload.citizen_id and case.citizen_id:
            payload.citizen_id = case.citizen_id
        if not payload.family_id and case.family_id:
            payload.family_id = case.family_id
    if citizen is not None and family is not None and citizen.family_id:
        if citizen.family_id != family.id:
            raise validation_error(
                "Fuqaro tanlangan oilaga tegishli emas."
            )
    task = Task(**payload.model_dump(), created_by=actor)
    db.add(task)
    db.flush()
    write_audit(
        db,
        action="task.created",
        entity_type="task",
        entity_id=task.id,
        actor_id=actor,
        new_value=model_snapshot(task),
        request_id=request_id,
    )
    if commit:
        db.commit()
        db.refresh(task)
    return task


def _apply_status(db: Session, task: Task, new_status: str) -> None:
    allowed = TASK_TRANSITIONS.get(task.status, set())
    if new_status not in allowed:
        raise bad_request(
            f"Vazifa holatini '{task.status}' dan '{new_status}' ga o'zgartirish mumkin emas."
        )
    task.status = new_status
    # E-1: `elif new_status != "completed"` — oldingi `if` ning aniq inkori.
    if new_status == "completed":
        task.completed_at = datetime.now(timezone.utc)
    else:
        task.completed_at = None


def update_task(
    db: Session, task_id: str, payload: TaskUpdate, actor: str, request_id: str | None
) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise not_found("Vazifa topilmadi.")
    # D-1: versiya majburiy.
    if payload.version != task.version:
        raise conflict("Vazifa ma'lumoti o'zgargan. Sahifani yangilang.")
    data = payload.model_dump(exclude_unset=True)
    data.pop("version", None)
    new_status = data.pop("status", None)
    # O-5: `before` o'zgarishlardan **OLDIN** olinadi.
    before = model_snapshot(task)
    if new_status and new_status != task.status:
        _apply_status(db, task, new_status)
    for key, value in data.items():
        setattr(task, key, value)
    task.version += 1
    db.flush()
    write_audit(
        db,
        action="task.updated",
        entity_type="task",
        entity_id=task.id,
        actor_id=actor,
        old_value=before,
        new_value=model_snapshot(task),
        request_id=request_id,
    )
    db.commit()
    db.refresh(task)
    return task


def complete_task(
    db: Session,
    task_id: str,
    payload: TaskCompleteRequest,
    actor: str,
    request_id: str | None,
) -> Task:
    """Vazifani bajarilgan deb belgilaydi.

    O-6: holatlar mashinasi (`TASK_TRANSITIONS`) va versiya tekshiruvi
    qo'llanadi, qator `with_for_update()` bilan bloklanadi — qo'sh bosishda
    ikki marta ish logi yozilmaydi.
    """
    task = db.execute(
        select(Task).where(Task.id == task_id).with_for_update()
    ).scalar_one_or_none()
    if task is None:
        raise not_found("Vazifa topilmadi.")
    if payload.version is not None and payload.version != task.version:
        raise conflict("Vazifa ma'lumoti o'zgargan. Sahifani yangilang.")
    # O-5: `before` o'zgarishlardan OLDIN olinadi.
    before = model_snapshot(task)
    _apply_status(db, task, "completed")
    task.evidence_note = payload.evidence_note
    task.evidence_document_id = payload.evidence_document_id
    task.version += 1
    db.add(
        WorkLog(
            citizen_id=task.citizen_id,
            family_id=task.family_id,
            case_id=task.case_id,
            task_id=task.id,
            type="bajarilgan ish",
            title=f"Vazifa bajarildi: {task.title}",
            description=payload.evidence_note,
            occurred_at=datetime.now(timezone.utc),
            author_id=actor,
            source="manual",
            approval_status="confirmed",
        )
    )
    db.flush()
    write_audit(
        db,
        action="task.completed",
        entity_type="task",
        entity_id=task.id,
        actor_id=actor,
        old_value=before,
        new_value=model_snapshot(task),
        request_id=request_id,
    )
    db.commit()
    db.refresh(task)
    return task


def cancel_task(
    db: Session,
    task_id: str,
    reason: str,
    actor: str,
    request_id: str | None,
    version: int | None = None,
) -> Task:
    """Vazifani bekor qilingan deb belgilaydi (O-6: holatlar mashinasi)."""
    task = db.execute(
        select(Task).where(Task.id == task_id).with_for_update()
    ).scalar_one_or_none()
    if task is None:
        raise not_found("Vazifa topilmadi.")
    if version is not None and version != task.version:
        raise conflict("Vazifa ma'lumoti o'zgargan. Sahifani yangilang.")
    # O-5: `before` o'zgarishlardan OLDIN olinadi.
    before = model_snapshot(task)
    _apply_status(db, task, "cancelled")
    task.evidence_note = reason
    task.version += 1
    db.flush()
    write_audit(
        db,
        action="task.cancelled",
        entity_type="task",
        entity_id=task.id,
        actor_id=actor,
        old_value=before,
        new_value=model_snapshot(task),
        request_id=request_id,
    )
    db.commit()
    db.refresh(task)
    return task
def list_work_logs(
    db: Session,
    *,
    citizen_id: str | None = None,
    family_id: str | None = None,
    case_id: str | None = None,
    task_id: str | None = None,
    type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], PageMeta]:
    stmt = select(WorkLog).order_by(WorkLog.occurred_at.desc())
    if citizen_id:
        stmt = stmt.where(WorkLog.citizen_id == citizen_id)
    if family_id:
        stmt = stmt.where(WorkLog.family_id == family_id)
    if case_id:
        stmt = stmt.where(WorkLog.case_id == case_id)
    if task_id:
        stmt = stmt.where(WorkLog.task_id == task_id)
    if type:
        stmt = stmt.where(WorkLog.type == type)
    rows, meta = paginate(db, stmt, page, page_size)
    return [work_log_out(row) for row in rows], meta


def create_work_log(
    db: Session,
    payload: WorkLogCreate,
    actor: str,
    request_id: str | None,
    *,
    commit: bool = True,
) -> WorkLog:
    log = WorkLog(
        **payload.model_dump(exclude={"occurred_at"}),
        occurred_at=payload.occurred_at or datetime.now(timezone.utc),
        author_id=actor,
        source="manual",
        approval_status="confirmed",
    )
    db.add(log)
    db.flush()
    write_audit(
        db,
        action="work_log.created",
        entity_type="work_log",
        entity_id=log.id,
        actor_id=actor,
        new_value=model_snapshot(log),
        request_id=request_id,
    )
    if commit:
        db.commit()
        db.refresh(log)
    return log
