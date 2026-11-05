"""J-9: Scheduler — urinishlar hisoblagichi, bloklash, eskirgan run, jadval siljisi.

Muqova:
- `run_job` har ishga tushishdan oldin `job.attempts = 0` qilardi -> doim
  yiqiladigan job hech qachon `max_attempts` ga yetib, "failed" bo'lmasdi.
- `run_due_jobs` da `FOR UPDATE SKIP LOCKED` yo'q edi -> cron + qo'lda
  ishga tushirish bir vaqtda ikki marta bajarishga olib kelardi.
- Jarayon o'ldirilsa `JobRun.status="running"` abadiy qolardi.
- `next_run_at = now + 1 kun` -> kechikish har kuni keyingi kunlarga siljidi.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.core.time import TZ
from app.models import JobRun, ScheduledJob

JOB_PREFIX = "j9-test-job"
_SAVED_JOBS: list[tuple] = []


def _cleanup() -> None:
    with SessionLocal() as db:
        job_ids = list(
            db.execute(
                select(ScheduledJob.id).where(ScheduledJob.name.like(f"{JOB_PREFIX}%"))
            ).scalars().all()
        )
        if job_ids:
            db.execute(delete(JobRun).where(JobRun.job_id.in_(job_ids)))
            db.execute(delete(ScheduledJob).where(ScheduledJob.id.in_(job_ids)))
        db.commit()


def _park_other_jobs() -> None:
    """Sinov paytida haqiqiy joblar ishga tushmasligi uchun ularni kechiktiramiz."""
    global _SAVED_JOBS
    _SAVED_JOBS = []
    future = datetime.now(timezone.utc) + timedelta(days=1)
    with SessionLocal() as db:
        for job in db.execute(select(ScheduledJob)).scalars().all():
            _SAVED_JOBS.append(
                (
                    job.id,
                    job.next_run_at,
                    job.status,
                    job.attempts,
                    job.error,
                    job.last_run_at,
                )
            )
            if job.status == "active":
                job.next_run_at = future
        db.commit()


def _restore_jobs() -> None:
    with SessionLocal() as db:
        for job_id, next_run_at, status, attempts, error, last_run_at in _SAVED_JOBS:
            job = db.get(ScheduledJob, job_id)
            if job is None:
                continue
            job.next_run_at = next_run_at
            job.status = status
            job.attempts = attempts
            job.error = error
            job.last_run_at = last_run_at
        db.commit()


@pytest.fixture(autouse=True)
def clean_jobs():
    _cleanup()
    _park_other_jobs()
    yield
    _restore_jobs()
    _cleanup()


def _make_job(
    *,
    job_type: str = "test_ok",
    schedule: str = "daily",
    next_run_at: datetime | None = None,
    max_attempts: int = 3,
    attempts: int = 0,
    status: str = "active",
) -> str:
    with SessionLocal() as db:
        job = ScheduledJob(
            name=f"{JOB_PREFIX}-{job_type}-{datetime.now(timezone.utc).timestamp()}",
            job_type=job_type,
            schedule=schedule,
            status=status,
            next_run_at=next_run_at or (datetime.now(timezone.utc) - timedelta(minutes=1)),
            max_attempts=max_attempts,
            attempts=attempts,
        )
        db.add(job)
        db.flush()
        db.commit()
        return job.id


def _get(job_id: str) -> ScheduledJob:
    with SessionLocal() as db:
        job = db.get(ScheduledJob, job_id)
        assert job is not None
        return job


def _runs(job_id: str) -> list[JobRun]:
    with SessionLocal() as db:
        return list(
            db.execute(select(JobRun).where(JobRun.job_id == job_id)).scalars().all()
        )


def test_always_failing_job_reaches_max_attempts(monkeypatch):
    """Doim yiqiladigan job `max_attempts` dan keyin "failed" bo'lishi kerak."""
    from app.services import scheduler

    calls: list[str] = []

    def _boom(db, job, actor):
        calls.append(job.id)
        raise RuntimeError("Job doim xato beradi")

    monkeypatch.setitem(scheduler.JOB_HANDLERS, "test_fail", _boom)
    job_id = _make_job(job_type="test_fail", max_attempts=3)

    for _ in range(6):
        with SessionLocal() as db:
            scheduler.run_due_jobs(db)
        # Keyingi jadval sloti keldi deb faraz qilamiz (xato -> keyingi urinish).
        with SessionLocal() as db:
            job = db.get(ScheduledJob, job_id)
            if job is not None and job.status == "active":
                job.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
                db.commit()

    job = _get(job_id)
    assert job.attempts == 3, job.attempts
    assert job.status == "failed", job.status
    assert job.error
    # Maksimal urinishdan keyin job qayta ishga tushmaydi.
    assert len(calls) == 3, calls


def test_attempts_reset_after_success(monkeypatch):
    """Muvaffaqiyatli ishdan keyin `attempts` 0 ga qaytishi kerak."""
    from app.services import scheduler

    monkeypatch.setitem(
        scheduler.JOB_HANDLERS, "test_ok", lambda db, job, actor: {"ok": True}
    )
    job_id = _make_job(job_type="test_ok", attempts=2)

    with SessionLocal() as db:
        result = scheduler.run_job(db, db.get(ScheduledJob, job_id))

    assert result["status"] == "completed"
    job = _get(job_id)
    assert job.attempts == 0, job.attempts
    assert job.status == "active"
    assert job.error == ""


def test_failed_job_is_not_picked_again(monkeypatch):
    """`max_attempts` ga yetgan job qayta ishga tushirilmasligi kerak."""
    from app.services import scheduler

    def _boom(db, job, actor):
        raise RuntimeError("xato")

    monkeypatch.setitem(scheduler.JOB_HANDLERS, "test_fail", _boom)
    job_id = _make_job(job_type="test_fail", max_attempts=1)

    with SessionLocal() as db:
        scheduler.run_due_jobs(db)

    assert _get(job_id).status == "failed"
    with SessionLocal() as db:
        results = scheduler.run_due_jobs(db)
    assert results == []


def test_next_run_at_is_computed_from_scheduled_time(monkeypatch):
    """Keyingi vaqt rejalashtirilgan vaqtdan hisoblanadi (kechikish siljimasligi)."""
    from app.services import scheduler

    monkeypatch.setitem(
        scheduler.JOB_HANDLERS, "test_ok", lambda db, job, actor: {"ok": True}
    )
    scheduled = datetime(2026, 3, 10, 6, 0, tzinfo=timezone.utc)  # 11:00 Toshkent
    job_id = _make_job(job_type="test_ok", next_run_at=scheduled)

    with SessionLocal() as db:
        hour, minute = scheduler._scheduler_time_of_day(db)
        scheduler.run_job(
            db,
            db.get(ScheduledJob, job_id),
            scheduled_for=scheduled,
        )

    job = _get(job_id)
    assert job.next_run_at is not None
    local = job.next_run_at.astimezone(TZ)
    # Keyingi bajarilish rejalashtirilgan kunning o'zida (siljigan emas).
    assert local.date() == scheduled.astimezone(TZ).date()
    assert (local.hour, local.minute) == (hour, minute)


def test_daily_next_run_at_aligned_to_local_hour():
    """Kunlik job `scheduler_timezone` bo'yicha soatga tekislanishi kerak."""
    from app.services import scheduler

    with SessionLocal() as db:
        hour, minute = scheduler._scheduler_time_of_day(db)

    # 11:00 Toshkent -> bugungi 21:00
    morning = datetime(2026, 3, 10, 6, 0, tzinfo=timezone.utc)
    same_day = scheduler.next_run_at("daily", from_time=morning, hour=hour, minute=minute)
    local = same_day.astimezone(TZ)
    assert local.date() == morning.astimezone(TZ).date()
    assert (local.hour, local.minute) == (hour, minute)

    # 22:00 Toshkent -> ertangi 21:00
    evening = datetime(2026, 3, 10, 17, 0, tzinfo=timezone.utc)
    next_day = scheduler.next_run_at("daily", from_time=evening, hour=hour, minute=minute)
    local = next_day.astimezone(TZ)
    assert local.date() == evening.astimezone(TZ).date() + timedelta(days=1)
    assert (local.hour, local.minute) == (hour, minute)


def test_next_run_at_hourly_and_weekly():
    """Soatlik va haftalik jadvallar ham to'g'ri hisoblanishi kerak."""
    from app.services import scheduler

    base = datetime(2026, 3, 10, 6, 30, tzinfo=timezone.utc)
    hourly = scheduler.next_run_at("hourly", from_time=base)
    assert hourly == base + timedelta(hours=1)

    weekly = scheduler.next_run_at("weekly", from_time=base, hour=21, minute=0)
    assert weekly.astimezone(TZ).date() == base.astimezone(TZ).date() + timedelta(days=7)
    assert weekly.astimezone(TZ).hour == 21


def test_stale_running_runs_are_closed():
    """10 daqiqadan eski "running" run "failed" deb yopilishi kerak."""
    from app.services import scheduler

    job_id = _make_job(job_type="test_ok")
    with SessionLocal() as db:
        run = JobRun(
            job_id=job_id,
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        db.add(run)
        db.commit()

    with SessionLocal() as db:
        closed = scheduler.close_stale_runs(db)

    assert closed >= 1
    runs = _runs(job_id)
    assert all(run.status != "running" for run in runs)
    assert any(run.finished_at is not None for run in runs)


def test_stuck_running_job_is_reactivated():
    """Jarayon o'ldirilgan job ("running") qayta faollashtirilishi kerak."""
    from app.services import scheduler

    job_id = _make_job(
        job_type="test_ok",
        status="running",
        next_run_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    with SessionLocal() as db:
        job = db.get(ScheduledJob, job_id)
        assert job is not None
        job.last_run_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        db.commit()

    with SessionLocal() as db:
        scheduler.close_stale_runs(db)

    assert _get(job_id).status == "active"


def test_run_due_jobs_uses_skip_locked():
    """Parallel ishga tushishda bir xil job ikki marta bajarilmasligi kerak."""
    import inspect

    from app.services import scheduler

    source = inspect.getsource(scheduler.run_due_jobs)
    assert "with_for_update" in source
    assert "skip_locked" in source


def test_due_job_runs_once(monkeypatch):
    """Mudaqati kelgan job bir marta bajarilishi kerak."""
    from app.services import scheduler

    calls: list[str] = []

    def _ok(db, job, actor):
        calls.append(job.id)
        return {"ok": True}

    monkeypatch.setitem(scheduler.JOB_HANDLERS, "test_ok", _ok)
    job_id = _make_job(job_type="test_ok")

    with SessionLocal() as db:
        scheduler.run_due_jobs(db)
    with SessionLocal() as db:
        scheduler.run_due_jobs(db)

    assert calls == [job_id]
