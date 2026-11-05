from __future__ import annotations

from datetime import date, datetime, timezone

from app.core.time import age_from_birth, today_local
from app.models import (
    Case,
    Citizen,
    Document,
    Family,
    LegislationDocument,
    Program,
    Task,
    WorkLog,
)


def address_for_citizen(citizen: Citizen) -> dict | None:
    family = citizen.family
    if not family or not family.house:
        return None
    house = family.house
    street = house.street
    mahalla = street.mahalla if street else None
    return {
        "mahalla_id": mahalla.id if mahalla else None,
        "mahalla": mahalla.name if mahalla else None,
        "street_id": street.id if street else None,
        "street": street.name if street else None,
        "house_id": house.id,
        "house_number": house.house_number,
        "address_label": house.address_label
        or f"{mahalla.name if mahalla else ''}, {street.name if street else ''}, {house.house_number}-uy".strip(", "),
    }


def address_for_family(family: Family) -> dict | None:
    house = family.house
    if not house:
        return None
    street = house.street
    mahalla = street.mahalla if street else None
    return {
        "mahalla_id": mahalla.id if mahalla else None,
        "mahalla": mahalla.name if mahalla else None,
        "street_id": street.id if street else None,
        "street": street.name if street else None,
        "house_id": house.id,
        "house_number": house.house_number,
        "address_label": house.address_label
        or f"{mahalla.name if mahalla else ''}, {street.name if street else ''}, {house.house_number}-uy".strip(", "),
    }


def family_out(
    family: Family,
    *,
    member_count: int | None = None,
    head_name: str | None = None,
) -> dict:
    head = family.head if getattr(family, "head", None) is not None else None
    return {
        "id": family.id,
        "house_id": family.house_id,
        "family_head_citizen_id": family.family_head_citizen_id,
        "family_head_name": head_name or (head.full_name if head else None),
        "family_type": family.family_type,
        "social_status": family.social_status,
        "member_count": member_count if member_count is not None else len(family.members or []),
        "notes": family.notes,
        "address": address_for_family(family),
        "version": family.version,
    }


def citizen_out(
    citizen: Citizen,
    *,
    quality: dict | None = None,
    include_family: bool = True,
    family_member_count: int | None = None,
) -> dict:
    family = citizen.family
    data = {
        "id": citizen.id,
        "family_id": citizen.family_id,
        "full_name": citizen.full_name,
        "gender": citizen.gender,
        "birth_date": citizen.birth_date,
        "age": age_from_birth(citizen.birth_date),
        "phone": citizen.phone,
        "family_role": citizen.family_role,
        "education": citizen.education,
        "employment_status": citizen.employment_status,
        "profession": citizen.profession,
        "social_status": citizen.social_status,
        "needs": citizen.needs or [],
        "notes": citizen.notes,
        "data_source": citizen.data_source,
        "last_verified_at": citizen.last_verified_at,
        "archived_at": citizen.archived_at,
        "version": citizen.version,
        "created_at": citizen.created_at,
        "updated_at": citizen.updated_at,
        "address": address_for_citizen(citizen),
        "family": None,
        "data_quality": quality,
    }
    if include_family and family is not None:
        data["family"] = family_out(family, member_count=family_member_count)
    return data


def case_out(case: Case, task_count: int = 0) -> dict:
    citizen_name = None
    if getattr(case, "citizen", None) is not None:
        citizen_name = case.citizen.full_name
    return {
        "id": case.id,
        "citizen_id": case.citizen_id,
        "family_id": case.family_id,
        "citizen_name": citizen_name,
        "category": case.category,
        "title": case.title,
        "description": case.description,
        "opened_at": case.opened_at,
        "status": case.status,
        "priority": case.priority,
        "responsible_user": case.responsible_user,
        "target_date": case.target_date,
        "outcome": case.outcome,
        "closed_at": case.closed_at,
        "evidence_refs": case.evidence_refs or [],
        "version": case.version,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "task_count": task_count,
    }


def task_out(task: Task, *, today: date | None = None) -> dict:
    today = today or today_local()
    citizen_name = None
    if getattr(task, "citizen", None) is not None:
        citizen_name = task.citizen.full_name
    is_overdue = bool(
        task.status not in {"completed", "cancelled"}
        and task.due_date is not None
        and task.due_date < today
    )
    days_until_due = (task.due_date - today).days if task.due_date else None
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "citizen_id": task.citizen_id,
        "citizen_name": citizen_name,
        "family_id": task.family_id,
        "case_id": task.case_id,
        "category": task.category,
        "priority": task.priority,
        "status": task.status,
        "due_date": task.due_date,
        "assignee": task.assignee,
        "completed_at": task.completed_at,
        "evidence_note": task.evidence_note,
        "evidence_document_id": task.evidence_document_id,
        "is_overdue": is_overdue,
        "days_until_due": days_until_due,
        "version": task.version,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def work_log_out(log: WorkLog) -> dict:
    return {
        "id": log.id,
        "citizen_id": log.citizen_id,
        "family_id": log.family_id,
        "case_id": log.case_id,
        "task_id": log.task_id,
        "type": log.type,
        "title": log.title,
        "description": log.description,
        "occurred_at": log.occurred_at,
        "author_id": log.author_id,
        "source": log.source,
        "approval_status": log.approval_status,
        "created_at": log.created_at,
    }


def document_out(document: Document) -> dict:
    return {
        "id": document.id,
        "filename": document.filename,
        "original_name": document.original_name,
        "mime_type": document.mime_type,
        "size": document.size,
        "content_hash": document.content_hash,
        "storage_backend": document.storage_backend,
        "kind": document.kind,
        "status": document.status,
        "meta": document.meta or {},
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def program_out(program: Program, *, now: datetime | None = None) -> dict:
    # N-4: `now` bir marta beriladi — ro'yxat ichida "stale" chegarasi har
    # qatorga boshqacha hisoblanib qolmasdi.
    now = now or datetime.now(timezone.utc)
    verified = program.last_verified_at
    stale = program.status == "stale"
    if verified is not None:
        if verified.tzinfo is None:
            verified = verified.replace(tzinfo=timezone.utc)
        stale = stale or (now - verified).days > 90
    return {
        "id": program.id,
        "name": program.name,
        "type": program.type,
        "organization": program.organization,
        "target_group": program.target_group,
        "region": program.region,
        "eligibility": program.eligibility or {},
        "amount": program.amount,
        "interest_rate": program.interest_rate,
        "term_months": program.term_months,
        "grace_period": program.grace_period,
        "required_documents": program.required_documents or [],
        "application_channel": program.application_channel,
        "official_url": program.official_url,
        "valid_from": program.valid_from,
        "valid_to": program.valid_to,
        "last_verified_at": program.last_verified_at,
        "status": program.status,
        "notes": program.notes,
        "stale": stale,
    }


def legislation_document_out(document: LegislationDocument) -> dict:
    return {
        "id": document.id,
        "source_url": document.source_url,
        "title": document.title,
        "number": document.number,
        "doc_type": document.doc_type,
        "adoption_date": document.adoption_date,
        "effective_date": document.effective_date,
        "last_revision_date": document.last_revision_date,
        "legal_status": document.legal_status,
        "retrieved_at": document.retrieved_at,
        "content_hash": document.content_hash,
        "version_identifier": document.version_identifier,
    }
