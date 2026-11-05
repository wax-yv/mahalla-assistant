from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.errors import not_found
from app.core.time import today_local
from app.models import JobRun, Notification, Program, ProgramSource, ScheduledJob, Task, User
from app.services import legislation, reports


def next_run_at(schedule: str, from_time: datetime | None = None) -> datetime:
    base = from_time or datetime.now(timezone.utc)
    schedule = (schedule or "daily").lower()
    if schedule.startswith("weekly"):
        return base + timedelta(days=7)
    if schedule.startswith("monthly"):
        return base + timedelta(days=30)
    if schedule.startswith("hourly"):
        return base + timedelta(hours=1)
    return base + timedelta(days=1)


def _notify(db: Session, title: str, body: str, kind: str = "info") -> None:
    user = db.execute(select(User).where(User.role == "admin").limit(1)).scalar_one_or_none()
    db.add(Notification(user_id=user.id if user else None, title=title, body=body, kind=kind))


def _daily_report(db: Session, job: ScheduledJob, actor: str) -> dict[str, Any]:
    from app.schemas import ReportGenerateRequest

    today = today_local()
    report = reports.generate_report(
        db,
        ReportGenerateRequest(type="daily", period_end=today),
        actor=actor,
        use_ai=bool((job.payload or {}).get("use_ai", True)),
    )
    _notify(db, "Kunlik hisobot tayyor", f"{report.title} draft holatida tasdiqlashni kutmoqda.", "report")
    return {"report_id": report.id, "title": report.title, "status": report.status}


def _overdue_scan(db: Session, job: ScheduledJob, actor: str) -> dict[str, Any]:
    today = today_local()
    rows = db.execute(
        select(Task).where(
            Task.due_date < today, Task.status.notin_(["completed", "cancelled"])
        )
    ).scalars().all()
    for task in rows:
        if task.priority in {"low", "normal"}:
            task.priority = "high"
    if rows:
        _notify(
            db,
            "Muddatidan oshgan vazifalar",
            f"{len(rows)} ta vazifa muddati o'tgan. Ular yuqori ustuvorlikka o'tkazildi.",
            "warning",
        )
    return {"overdue": len(rows), "ids": [task.id for task in rows[:50]]}


def _legislation_refresh(db: Session, job: ScheduledJob, actor: str) -> dict[str, Any]:
    from app.models import LegislationDocument

    documents = db.execute(
        select(LegislationDocument).order_by(LegislationDocument.retrieved_at).limit(2)
    ).scalars().all()
    refreshed, errors = [], []
    for document in documents:
        try:
            legislation.ingest_document(db, document.source_url, actor=actor)
            refreshed.append(document.source_url)
        except Exception as error:
            db.rollback()
            errors.append(f"{document.id}: {error}"[:300])
    return {"refreshed": refreshed, "errors": errors}


def _programs_refresh(db: Session, job: ScheduledJob, actor: str) -> dict[str, Any]:
    sources = db.execute(select(ProgramSource)).scalars().all()
    now = datetime.now(timezone.utc)
    for source in sources:
        source.retrieved_at = now
    programs = db.execute(select(Program)).scalars().all()
    return {
        "programs": len(programs),
        "sources": len(sources),
        "note": "Manba havolalari yangilandi. Rasmiy shartlar bank filialida tasdiqlanishi shart.",
    }


JOB_HANDLERS = {
    "daily_report": _daily_report,
    "overdue_scan": _overdue_scan,
    "legislation_refresh": _legislation_refresh,
    "programs_refresh": _programs_refresh,
}


def run_job(db: Session, job: ScheduledJob, actor: str = "scheduler") -> dict[str, Any]:
    handler = JOB_HANDLERS.get(job.job_type)
    run = JobRun(job_id=job.id, status="running")
    db.add(run)
    db.flush()
    job.last_run_at = datetime.now(timezone.utc)
    job.attempts = 0
    job.error = ""
    db.commit()
    if handler is None:
        run.status = "failed"
        run.error = f"«{job.job_type}» job turi qo'llab-quvvatlanmaydi."
        run.finished_at = datetime.now(timezone.utc)
        job.next_run_at = next_run_at(job.schedule)
        db.commit()
        return {"job_id": job.id, "status": "failed", "error": run.error}
    try:
        result = handler(db, job, actor)
        run.status = "completed"
        run.result = result
        run.finished_at = datetime.now(timezone.utc)
        job.next_run_at = next_run_at(job.schedule)
        job.status = "active"
        write_audit(
            db,
            action="job.completed",
            entity_type="scheduled_job",
            entity_id=job.id,
            actor_id=actor,
            new_value={"job_type": job.job_type, "result": result},
        )
        db.commit()
        return {"job_id": job.id, "status": "completed", "result": result}
    except Exception as error:
        db.rollback()
        job = db.get(ScheduledJob, job.id)
        run = db.get(JobRun, run.id)
        if job is None or run is None:
            raise
        job.attempts = (job.attempts or 0) + 1
        job.error = f"{type(error).__name__}: {error}"[:1000]
        job.next_run_at = next_run_at(job.schedule)
        if job.attempts >= (job.max_attempts or 3):
            job.status = "failed"
        run.status = "failed"
        run.error = job.error
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {"job_id": job.id, "status": "failed", "error": job.error}


def run_due_jobs(db: Session, limit: int = 5) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    jobs = db.execute(
        select(ScheduledJob)
        .where(
            ScheduledJob.status == "active",
            ScheduledJob.next_run_at.is_not(None),
            ScheduledJob.next_run_at <= now,
        )
        .order_by(ScheduledJob.next_run_at)
        .limit(limit)
    ).scalars().all()
    return [run_job(db, job) for job in jobs]


def list_jobs(db: Session) -> list[dict[str, Any]]:
    jobs = db.execute(select(ScheduledJob).order_by(ScheduledJob.name)).scalars().all()
    result = []
    for job in jobs:
        last_runs = db.execute(
            select(JobRun).where(JobRun.job_id == job.id).order_by(JobRun.started_at.desc()).limit(5)
        ).scalars().all()
        result.append(
            {
                "id": job.id,
                "name": job.name,
                "job_type": job.job_type,
                "schedule": job.schedule,
                "payload": job.payload or {},
                "status": job.status,
                "next_run_at": job.next_run_at,
                "last_run_at": job.last_run_at,
                "attempts": job.attempts,
                "error": job.error,
                "runs": [
                    {
                        "id": run.id,
                        "status": run.status,
                        "started_at": run.started_at,
                        "finished_at": run.finished_at,
                        "error": run.error,
                        "result": run.result or {},
                    }
                    for run in last_runs
                ],
            }
        )
    return result


def get_job(db: Session, job_id: str) -> ScheduledJob:
    job = db.get(ScheduledJob, job_id)
    if job is None:
        raise not_found("Rejalashtirilgan job topilmadi.")
    return job
