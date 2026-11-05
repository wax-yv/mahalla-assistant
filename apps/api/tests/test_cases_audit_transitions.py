"""O-5/O-6: audit `old_value` va vazifa holatlari mashinasi.

Muqova:
- O-5: `update_task`/`update_case` da `before = model_snapshot(...)`
  **o'zgarishdan keyin** olinardi — audit yozuvida "eski holat = yangi
  holat" ko'rinardi.
- O-6: `complete_task`/`cancel_task` holatlar mashinasini (`TASK_TRANSITIONS`)
  va versiyani chetlab o'tardi; `create_task` esa `citizen_id`/`family_id`/
  `case_id` bir-biriga tegishliligini tekshirtirmasdi.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import AuditLog, Citizen, Case, Task, WorkLog


@pytest.fixture()
def clean_tasks():
    def _cleanup():
        with SessionLocal() as db:
            ids = db.execute(
                select(Task.id).where(Task.title.like("O56 sinov vazifasi%"))
            ).scalars().all()
            if ids:
                db.execute(delete(WorkLog).where(WorkLog.task_id.in_(ids)))
                db.execute(delete(Task).where(Task.id.in_(ids)))
            db.commit()

    _cleanup()
    yield
    _cleanup()


def _make_task(status: str = "new") -> str:
    with SessionLocal() as db:
        task = Task(
            title="O56 sinov vazifasi",
            description="sinov",
            status=status,
            priority="normal",
            category="umumiy",
        )
        db.add(task)
        db.commit()
        return task.id


def _make_case(status: str = "open") -> str:
    with SessionLocal() as db:
        case = Case(
            title="O56 sinov case",
            category="umumiy",
            status=status,
            priority="normal",
        )
        db.add(case)
        db.commit()
        return case.id


def _audit_for(entity_type: str, entity_id: str, action: str):
    with SessionLocal() as db:
        return db.execute(
            select(AuditLog).where(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
                AuditLog.action == action,
            )
        ).scalars().first()


# ---------------------------------------------------------------- O-5


def test_update_task_audit_old_status_is_previous(clean_tasks):
    """O-5: audit `old_value` da ESKI holat ko'rinishi kerak."""
    from app.schemas import TaskUpdate
    from app.services import cases as service

    task_id = _make_task("new")
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        service.update_task(
            db,
            task_id,
            TaskUpdate(status="in_progress", priority="high", version=task.version),
            "tester",
            None,
        )

    audit = _audit_for("task", task_id, "task.updated")
    assert audit is not None
    assert audit.old_value["status"] == "new", (
        f"audit eski holat noto'g'ri: {audit.old_value.get('status')}"
    )
    assert audit.new_value["status"] == "in_progress"


def test_update_case_audit_old_status_is_previous():
    """O-5: case uchun ham `old_value` eski holatni ko'rsatishi kerak."""
    from app.schemas import CaseUpdate
    from app.services import cases as service

    case_id = _make_case("open")
    with SessionLocal() as db:
        case = db.get(Case, case_id)
        service.update_case(
            db, case_id, CaseUpdate(status="in_progress", version=case.version), "tester", None
        )

    audit = _audit_for("case", case_id, "case.updated")
    assert audit is not None
    assert audit.old_value["status"] == "open", (
        f"audit eski holat noto'g'ri: {audit.old_value.get('status')}"
    )
    assert audit.new_value["status"] == "in_progress"


# ---------------------------------------------------------------- O-6


def test_complete_task_uses_state_machine(clean_tasks):
    """O-6: `completed` ga o'tish `TASK_TRANSITIONS` bilan tekshiriladi."""
    from app.schemas import TaskCompleteRequest
    from app.services import cases as service

    task_id = _make_task("waiting")
    with SessionLocal() as db:
        service.complete_task(
            db, task_id, TaskCompleteRequest(evidence_note=" bajarildi"), "tester", None
        )

    with SessionLocal() as db:
        task = db.get(Task, task_id)
        assert task is not None
        assert task.status == "completed"


def test_complete_task_rejects_invalid_transition(clean_tasks):
    """O-6: `cancelled` dan `completed` ga o'tish taqiqlanadi."""
    from app.core.errors import APIError
    from app.schemas import TaskCompleteRequest
    from app.services import cases as service

    task_id = _make_task("cancelled")
    with SessionLocal() as db:
        with pytest.raises(APIError):
            service.complete_task(
                db,
                task_id,
                TaskCompleteRequest(evidence_note=" bajarildi"),
                "tester",
                None,
            )


def test_cancel_task_rejects_invalid_transition(clean_tasks):
    """O-6: `cancel_task` ham holatlar mashinasini tekshirishi kerak."""
    from app.core.errors import APIError
    from app.services import cases as service

    task_id = _make_task("completed")
    with SessionLocal() as db:
        with pytest.raises(APIError):
            service.cancel_task(db, task_id, "bekor qilindi", "tester", None)


def test_complete_task_rejects_stale_version(clean_tasks):
    """O-6: eskirgan `version` bilan bajarish rad etiladi."""
    from app.core.errors import APIError
    from app.schemas import TaskCompleteRequest
    from app.services import cases as service

    task_id = _make_task("new")
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        assert task is not None
        stale_version = task.version

    payload = TaskCompleteRequest(evidence_note=" bajarildi", version=stale_version + 99)
    with SessionLocal() as db:
        with pytest.raises(APIError):
            service.complete_task(db, task_id, payload, "tester", None)


def test_complete_task_creates_single_worklog(clean_tasks):
    """O-6: qo'sh bosishda ikkita `WorkLog` yaratilmasligi kerak."""
    from app.schemas import TaskCompleteRequest
    from app.services import cases as service

    task_id = _make_task("new")
    with SessionLocal() as db:
        service.complete_task(
            db, task_id, TaskCompleteRequest(evidence_note=" bajarildi"), "tester", None
        )

    with SessionLocal() as db:
        logs = db.execute(
            select(WorkLog).where(WorkLog.task_id == task_id)
        ).scalars().all()
    assert len(logs) == 1, f"kutilgan 1 ish logi, topildi: {len(logs)}"


def test_create_task_rejects_mismatched_case_and_citizen():
    """O-6: task'ning case'i va fuqarosi bir-biriga tegishli bo'lishi kerak."""
    from app.core.errors import APIError
    from app.schemas import TaskCreate
    from app.services import cases as service

    with SessionLocal() as db:
        citizen = Citizen(full_name="O56 sinov fuqarosi", gender="Erkak")
        db.add(citizen)
        db.flush()
        other = Citizen(full_name="O56 boshqa fuqaro", gender="Ayol")
        db.add(other)
        db.flush()
        case = Case(
            title="O56 sinov case",
            category="umumiy",
            status="new",
            priority="normal",
            citizen_id=citizen.id,
        )
        db.add(case)
        db.commit()
        case_id = case.id
        citizen_id = citizen.id
        other_id = other.id

    try:
        with SessionLocal() as db:
            with pytest.raises(APIError):
                service.create_task(
                    db,
                    TaskCreate(
                        title="O56 sinov vazifasi",
                        citizen_id=other_id,
                        case_id=case_id,
                    ),
                    "tester",
                    None,
                )
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.title.like("O56 sinov vazifasi%")))
            db.execute(delete(Case).where(Case.id == case_id))
            db.execute(delete(Citizen).where(Citizen.id.in_([citizen_id, other_id])))
            db.commit()
