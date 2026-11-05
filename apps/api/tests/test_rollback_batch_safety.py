from __future__ import annotations

import pytest
from app.core.db import SessionLocal
from app.models import AuditLog, Citizen, Document, ImportBatch, ImportChange
from sqlalchemy import delete, select

MARKER = "N11sinov"

def _cleanup() -> None:
    with SessionLocal() as db:
        citizens = db.execute(
            select(Citizen.id).where(Citizen.full_name.like(f"{MARKER}%"))
        ).scalars().all()
        documents = db.execute(
            select(Document.id).where(Document.original_name.like(f"{MARKER}%"))
        ).scalars().all()
        batches = db.execute(
            select(ImportBatch.id).where(ImportBatch.document_id.in_(documents))
        ).scalars().all()
        db.execute(delete(ImportChange).where(ImportChange.batch_id.in_(batches)))
        db.execute(delete(AuditLog).where(AuditLog.entity_id.in_(batches)))
        db.execute(delete(ImportBatch).where(ImportBatch.id.in_(batches)))
        db.execute(delete(Document).where(Document.id.in_(documents)))
        db.execute(delete(Citizen).where(Citizen.id.in_(citizens)))
        db.commit()

@pytest.fixture()
def clean():
    _cleanup()
    yield
    _cleanup()

def _make_batch_with_citizens(count: int = 2) -> tuple[str, list[str]]:
    with SessionLocal() as db:
        document = Document(
            filename=f"{MARKER}.xlsx",
            original_name=f"{MARKER}.xlsx",
            content_hash=f"hash-{MARKER}",
            kind="xlsx",
            status="imported",
        )
        db.add(document)
        db.flush()
        batch = ImportBatch(document_id=document.id, module="citizens", status="committed")
        db.add(batch)
        db.flush()
        citizen_ids = []
        for index in range(count):
            citizen = Citizen(
                full_name=f"{MARKER} fuqaro {index}",
                gender="Erkak",
                phone=f"+9989000006{index:02d}",
            )
            db.add(citizen)
            db.flush()
            citizen_ids.append(citizen.id)
            db.add(
                ImportChange(
                    batch_id=batch.id,
                    entity_type="citizens",
                    entity_id=citizen.id,
                    action="create",
                    after={"full_name": citizen.full_name},
                )
            )
        db.commit()
        return batch.id, citizen_ids

def test_rollback_after_success_deletes_created(clean):
    from app.services.documents import rollback_batch

    batch_id, citizen_ids = _make_batch_with_citizens()
    with SessionLocal() as db:
        result = rollback_batch(db, batch_id, "tester", None)
    assert result["deleted"] == 2

    with SessionLocal() as db:
        for citizen_id in citizen_ids:
            assert db.get(Citizen, citizen_id) is None
        batch = db.get(ImportBatch, batch_id)
        assert batch is not None
        assert batch.status == "rolled_back"

def test_rollback_survives_row_failure(clean):
    from app.services.documents import rollback_batch

    batch_id, citizen_ids = _make_batch_with_citizens()

    with SessionLocal() as db:
        original_get = db.get
        calls = {"count": 0}

        def _flaky_get(*args, **kwargs):
            if args and args[0] is Citizen and calls["count"] == 0:
                calls["count"] += 1
                raise RuntimeError("sinov xatosi")
            return original_get(*args, **kwargs)

        db.get = _flaky_get
        try:
            result = rollback_batch(db, batch_id, "tester", None)
        finally:
            db.get = original_get

        assert result["batch"]["status"] == "rolled_back"
        db.commit()

    with SessionLocal() as db:
        batch = db.get(ImportBatch, batch_id)
        assert batch is not None
        assert batch.status == "rolled_back"
        remaining = [cid for cid in citizen_ids if db.get(Citizen, cid) is not None]
        assert len(remaining) == 1
