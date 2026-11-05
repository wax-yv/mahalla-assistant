from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import Program, ProgramSource
from app.services import scheduler

PREFIX = "J10 sinov dasturi"

@pytest.fixture()
def clean_programs():
    def _cleanup():
        with SessionLocal() as db:
            programs = db.execute(
                select(Program).where(Program.name.like(f"{PREFIX}%"))
            ).scalars().all()
            for program in programs:
                db.execute(
                    delete(ProgramSource).where(ProgramSource.program_id == program.id)
                )
                db.delete(program)
            db.commit()

    _cleanup()
    yield
    _cleanup()

def _make_program() -> str:
    with SessionLocal() as db:
        program = Program(
            name=f"{PREFIX} {datetime.now(timezone.utc).timestamp()}",
            type="credit",
            organization="Test bank",
            official_url="https://example.com/credits",
            last_verified_at=None,
            status="verified",
        )
        db.add(program)
        db.flush()
        source = ProgramSource(
            program_id=program.id,
            url="https://example.com/credits",
            title="Test bank rasmiy sayti",
            status="verified",
            notes="Manba sifatida saqlangan rasmiy havola.",
        )
        db.add(source)
        db.commit()
        return program.id

def _isolate(monkeypatch, program_id: str) -> None:
    real_select = scheduler.select

    def _fake_select(model, *args, **kwargs):
        stmt = real_select(model, *args, **kwargs)
        if model is ProgramSource:
            return stmt.where(ProgramSource.program_id == program_id)
        if model is Program:
            return stmt.where(Program.id == program_id)
        return stmt

    monkeypatch.setattr(scheduler, "select", _fake_select)

def _run(monkeypatch, checker, program_id: str):
    monkeypatch.setattr(scheduler, "_check_source", checker)
    _isolate(monkeypatch, program_id)
    with SessionLocal() as db:
        job = scheduler.ScheduledJob(
            name="j10-test-job", job_type="programs_refresh", schedule="monthly"
        )
        result = scheduler._programs_refresh(db, job, "tester")
        db.commit()
        return result

def test_successful_check_updates_verification_time(clean_programs, monkeypatch):
    program_id = _make_program()

    result = _run(monkeypatch, lambda url: (200, "hash-1"), program_id)

    assert result["checked"] == 1
    assert not result["changed"]

    with SessionLocal() as db:
        program = db.get(Program, program_id)
        assert program is not None
        assert program.last_verified_at is not None
        assert program.status == "verified"
        source = db.execute(
            select(ProgramSource).where(ProgramSource.program_id == program_id)
        ).scalars().first()
        assert source is not None
        assert source.status == "verified"
        assert source.content_hash == "hash-1"
        assert source.notes.startswith("Tekshirildi:")

def test_changed_content_requires_review(clean_programs, monkeypatch):
    program_id = _make_program()

    _run(monkeypatch, lambda url: (200, "hash-1"), program_id)
    result = _run(monkeypatch, lambda url: (200, "hash-2"), program_id)

    assert result["changed"], result
    with SessionLocal() as db:
        program = db.get(Program, program_id)
        assert program is not None
        assert program.status == "needs_review"
        source = db.execute(
            select(ProgramSource).where(ProgramSource.program_id == program_id)
        ).scalars().first()
        assert source is not None
        assert source.status == "changed"

def test_failed_check_keeps_last_verified_at(clean_programs, monkeypatch):
    program_id = _make_program()

    _run(monkeypatch, lambda url: (200, "hash-1"), program_id)
    with SessionLocal() as db:
        program = db.get(Program, program_id)
        assert program is not None
        verified_at = program.last_verified_at
        assert verified_at is not None

    result = _run(
        monkeypatch,
        lambda url: (_ for _ in ()).throw(RuntimeError("timeout")),
        program_id,
    )

    assert result["errors"], result
    with SessionLocal() as db:
        program = db.get(Program, program_id)
        assert program is not None
        assert program.last_verified_at == verified_at
        assert program.status == "needs_review"
        source = db.execute(
            select(ProgramSource).where(ProgramSource.program_id == program_id)
        ).scalars().first()
        assert source is not None
        assert source.status == "error"

def test_http_error_marks_needs_review(clean_programs, monkeypatch):
    program_id = _make_program()

    result = _run(monkeypatch, lambda url: (404, "hash"), program_id)

    assert result["errors"], result
    with SessionLocal() as db:
        program = db.get(Program, program_id)
        assert program is not None
        assert program.status == "needs_review"
        assert program.last_verified_at is None

def test_public_url_validation_blocks_internal_hosts():
    from app.core.errors import APIError
    from app.core.urls import validate_public_https_url

    for url in (
        "http://127.0.0.1/admin",
        "https://127.0.0.1/",
        "https://localhost/",
        "https://192.168.1.10/",
        "https://10.0.0.5/",
        "https://user:pass@example.com/",
        "http://example.com/",
    ):
        with pytest.raises(APIError):
            validate_public_https_url(url)

def test_public_url_validation_accepts_normal_url():
    from app.core.urls import validate_public_https_url

    assert validate_public_https_url("https://example.com/credits") == (
        "https://example.com/credits"
    )
