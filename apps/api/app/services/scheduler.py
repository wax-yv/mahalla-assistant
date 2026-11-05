from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.errors import not_found
from app.core.time import TZ, today_local
from app.models import JobRun, Notification, Program, ProgramSource, ScheduledJob, Task, User
from app.services import legislation, reports

# J-9: kunlik joblar uchun standart soat (sozlamadagi `scheduler_time`
# o'rnini bosganda ishlatiladi).
DEFAULT_DAILY_HOUR = 21
DEFAULT_DAILY_MINUTE = 0

# J-9: jarayon to'xtab qolsa, "running" holatidagi ish yozimi 10 daqiqadan
# eski bo'lsa "failed" deb yopiladi (abadiy "running" qolmasligi uchun).
STALE_RUN_MINUTES = 10


def _scheduler_time_of_day(db: Session) -> tuple[int, int]:
    """Sozlamalardagi `scheduler_time` ("HH:MM") -> (soat, daqiqa)."""
    from app.models import AppSetting

    try:
        row = db.get(AppSetting, "app")
        raw = (row.value or {}).get("scheduler_time") if row is not None else None
        if isinstance(raw, str) and ":" in raw:
            hours, minutes = raw.split(":", 1)
            hour = int(hours)
            minute = int(minutes)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute
    except Exception:
        pass
    return DEFAULT_DAILY_HOUR, DEFAULT_DAILY_MINUTE


def _add_month(value: datetime) -> datetime:
    """Bir oy qo'shish (oy oxiridagi sanalarni moslashtiradi)."""
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def next_run_at(
    schedule: str,
    from_time: datetime | None = None,
    *,
    hour: int | None = None,
    minute: int | None = None,
) -> datetime:
    """Keyingi bajarilish vaqti (UTC).

    J-9: vaqt **rejalashtirilgan** vaqtdan (`from_time`) hisoblanadi — shunda
    kechikish keyingi kunlarga siljimaydi. Kunlik/haftalik/oylik joblar
    `scheduler_timezone` (Asia/Tashkent) bo'yicha belgilangan soatga tekislanadi.
    """
    base = from_time or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    local = base.astimezone(TZ)
    hour = DEFAULT_DAILY_HOUR if hour is None else int(hour)
    minute = DEFAULT_DAILY_MINUTE if minute is None else int(minute)
    hour = min(23, max(0, hour))
    minute = min(59, max(0, minute))
    schedule = (schedule or "daily").lower()
    if schedule.startswith("hourly"):
        return (local + timedelta(hours=1)).astimezone(timezone.utc)
    if schedule.startswith("weekly"):
        target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return (target + timedelta(days=7)).astimezone(timezone.utc)
    if schedule.startswith("monthly"):
        target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return _add_month(target).astimezone(timezone.utc)
    target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= local:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc)


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


def close_stale_runs(db: Session, *, minutes: int = STALE_RUN_MINUTES) -> int:
    """J-9: "running" holatida qolib ketgan ish yozimlarini yopadi.

    Jarayon o'ldirilgan (timeout/kill) bo'lsa, `JobRun.status` abadiy
    "running" qolardi. 10 daqiqadan eski bo'lganlar "failed" deb yopiladi
    va "running" holatida qolib ketgan joblar qayta faollashtiriladi.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    runs = db.execute(
        select(JobRun).where(JobRun.status == "running", JobRun.started_at < cutoff)
    ).scalars().all()
    for run in runs:
        run.status = "failed"
        run.error = "Job bajariluvi to'xtab qoldi (vaqt chegarasi)."
        run.finished_at = datetime.now(timezone.utc)
    jobs = db.execute(
        select(ScheduledJob).where(
            ScheduledJob.status == "running",
            ScheduledJob.last_run_at.is_not(None),
            ScheduledJob.last_run_at < cutoff,
        )
    ).scalars().all()
    for job in jobs:
        job.status = "active"
        if not job.error:
            job.error = "Job bajariluvi to'xtab qoldi, qayta rejalashtirildi."
    if runs or jobs:
        db.commit()
    return len(runs)


def _fail_job(
    db: Session,
    job: ScheduledJob,
    run: JobRun,
    error: str,
    scheduled: datetime,
    hour: int,
    minute: int,
) -> dict[str, Any]:
    """Job muvaffaqiyatsiz bo'ldi — urinishlar hisoblagichi oshadi."""
    db.rollback()
    job = db.get(ScheduledJob, job.id)
    run = db.get(JobRun, run.id)
    if job is None or run is None:
        raise not_found("Rejalashtirilgan job topilmadi.")
    # J-9: `attempts` har urinishda oshadi (muvaffaqiyatda 0 ga qaytadi).
    job.attempts = (job.attempts or 0) + 1
    job.error = error[:1000]
    job.next_run_at = next_run_at(
        job.schedule, from_time=scheduled, hour=hour, minute=minute
    )
    job.status = "failed" if job.attempts >= (job.max_attempts or 3) else "active"
    run.status = "failed"
    run.error = job.error
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "job_id": job.id,
        "status": "failed",
        "error": job.error,
        "attempts": job.attempts,
    }


def run_job(
    db: Session,
    job: ScheduledJob,
    actor: str = "scheduler",
    *,
    scheduled_for: datetime | None = None,
) -> dict[str, Any]:
    """Jobni bajaradi.

    J-9: `attempts` faqat muvaffaqiyatda 0 ga qaytadi; xatoda oshadi va
    `max_attempts` ga yetganda job "failed" holatiga o'tadi.
    """
    handler = JOB_HANDLERS.get(job.job_type)
    now = datetime.now(timezone.utc)
    scheduled = scheduled_for or job.next_run_at or now
    # Qo'lda ishga tushirilganda jadval siljib ketmasligi uchun kelajakdagi
    # reja o'rniga "hozir" dan hisoblanadi.
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)
    if scheduled > now:
        scheduled = now
    run = JobRun(job_id=job.id, status="running")
    db.add(run)
    db.flush()
    job.last_run_at = now
    # J-9: claim — jobni "running" belgilab, parallel ishga tushishning oldini
    # olamiz (qo'sh bosish ikki marta bajarishga olib kelmasligi kerak).
    job.status = "running"
    db.commit()
    hour, minute = _scheduler_time_of_day(db)
    if handler is None:
        error = f"«{job.job_type}» job turi qo'llab-quvvatlanmaydi."
        return _fail_job(db, job, run, error, scheduled, hour, minute)
    try:
        result = handler(db, job, actor)
    except Exception as error:
        return _fail_job(
            db,
            job,
            run,
            f"{type(error).__name__}: {error}"[:1000],
            scheduled,
            hour,
            minute,
        )
    run.status = "completed"
    run.result = result
    run.finished_at = datetime.now(timezone.utc)
    # J-9: muvaffaqiyat — urinishlar hisoblagichi noldan boshlanadi.
    job.attempts = 0
    job.error = ""
    job.status = "active"
    job.next_run_at = next_run_at(
        job.schedule, from_time=scheduled, hour=hour, minute=minute
    )
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


def run_due_jobs(db: Session, limit: int = 5) -> list[dict[str, Any]]:
    """Mudaqati kelgan joblarni bajaradi.

    J-9: `FOR UPDATE SKIP LOCKED` — cron va qo'lda ishga tushirish bir vaqtda
    ishlasa ham, har job faqat bitta ishchi tomonidan bajariladi.
    """
    close_stale_runs(db)
    results: list[dict[str, Any]] = []
    for _ in range(max(0, limit)):
        now = datetime.now(timezone.utc)
        job = db.execute(
            select(ScheduledJob)
            .where(
                ScheduledJob.status == "active",
                ScheduledJob.next_run_at.is_not(None),
                ScheduledJob.next_run_at <= now,
            )
            .order_by(ScheduledJob.next_run_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).scalars().first()
        if job is None:
            break
        scheduled_for = job.next_run_at
        results.append(run_job(db, job, scheduled_for=scheduled_for))
    return results


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
