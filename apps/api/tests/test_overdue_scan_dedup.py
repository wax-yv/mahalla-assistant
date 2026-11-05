from __future__ import annotations

from datetime import timedelta

import pytest
from app.core.db import SessionLocal
from app.core.time import today_local
from app.models import Notification, ScheduledJob, Task
from sqlalchemy import delete, select

MARKER = "D14sinov"
NOTIFY_TITLE = "Muddatidan oshgan vazifalar"

def _cleanup() -> None:
    with SessionLocal() as db:
        task_ids = db.execute(select(Task.id).where(Task.title.like(f"{MARKER}%"))).scalars().all()
        db.execute(delete(Notification).where(Notification.title == NOTIFY_TITLE))
        db.execute(delete(Task).where(Task.id.in_(task_ids)))
        db.execute(delete(ScheduledJob).where(ScheduledJob.name.like(f"{MARKER}%")))
        db.commit()

@pytest.fixture()
def job():
    _cleanup()
    with SessionLocal() as db:
        job = ScheduledJob(
            name=f"{MARKER} job",
            job_type="overdue_scan",
            schedule="daily",
            payload={},
            status="active",
        )
        db.add(job)
        db.commit()
        job_id = job.id
    yield job_id
    _cleanup()

def _make_overdue_task(title_suffix: str, priority: str = "normal") -> str:
    with SessionLocal() as db:
        task = Task(
            title=f"{MARKER} {title_suffix}",
            category="umumiy",
            status="new",
            priority=priority,
            due_date=today_local() - timedelta(days=3),
        )
        db.add(task)
        db.commit()
        return task.id

def _notifications() -> list[Notification]:
    with SessionLocal() as db:
        return db.execute(
            select(Notification).where(Notification.title == NOTIFY_TITLE)
        ).scalars().all()

def _prefill(job_id: str) -> None:
    with SessionLocal() as db:
        overdue_ids = db.execute(
            select(Task.id).where(
                Task.due_date < today_local(), Task.status.notin_(["completed", "cancelled"])
            )
        ).scalars().all()
        job = db.get(ScheduledJob, job_id)
        job.payload = {"overdue_notified_ids": list(overdue_ids)}
        db.commit()

def test_scan_notifies_once_per_task(job):
    from app.services import scheduler

    _prefill(job)
    _make_overdue_task("vazifa-1")
    with SessionLocal() as db:
        job_row = db.get(ScheduledJob, job)
        result = scheduler._overdue_scan(db, job_row, "tester")
        db.commit()
    assert result["newly"] == 1
    assert len(_notifications()) == 1

    with SessionLocal() as db:
        job_row = db.get(ScheduledJob, job)
        result = scheduler._overdue_scan(db, job_row, "tester")
        db.commit()
    assert result["newly"] == 0
    assert len(_notifications()) == 1

def test_scan_escalates_only_new_tasks(job):
    from app.services import scheduler

    _prefill(job)
    first_id = _make_overdue_task("vazifa-1")
    with SessionLocal() as db:
        job_row = db.get(ScheduledJob, job)
        scheduler._overdue_scan(db, job_row, "tester")
        db.commit()

    second_id = _make_overdue_task("vazifa-2")
    with SessionLocal() as db:
        job_row = db.get(ScheduledJob, job)
        result = scheduler._overdue_scan(db, job_row, "tester")
        db.commit()
    assert result["newly"] == 1

    with SessionLocal() as db:
        first = db.get(Task, first_id)
        second = db.get(Task, second_id)
        assert first.priority == "high"
        assert second.priority == "high"

def test_manual_lowering_is_not_overridden(job):
    from app.services import scheduler

    _prefill(job)
    task_id = _make_overdue_task("vazifa-1")
    with SessionLocal() as db:
        job_row = db.get(ScheduledJob, job)
        scheduler._overdue_scan(db, job_row, "tester")
        db.commit()

    with SessionLocal() as db:
        task = db.get(Task, task_id)
        task.priority = "normal"
        db.commit()

    with SessionLocal() as db:
        job_row = db.get(ScheduledJob, job)
        result = scheduler._overdue_scan(db, job_row, "tester")
        db.commit()
    assert result["newly"] == 0

    with SessionLocal() as db:
        task = db.get(Task, task_id)
        assert task.priority == "normal", "doimiy 'high' qayta o'rnatildi"

def test_new_task_triggers_new_notification(job):
    from app.services import scheduler

    _prefill(job)
    _make_overdue_task("vazifa-1")
    with SessionLocal() as db:
        job_row = db.get(ScheduledJob, job)
        scheduler._overdue_scan(db, job_row, "tester")
        db.commit()
    assert len(_notifications()) == 1

    _make_overdue_task("vazifa-2")
    with SessionLocal() as db:
        job_row = db.get(ScheduledJob, job)
        scheduler._overdue_scan(db, job_row, "tester")
        db.commit()
    assert len(_notifications()) == 2
