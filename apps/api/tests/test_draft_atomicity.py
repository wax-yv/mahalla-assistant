from __future__ import annotations

import pytest
from app.core.db import SessionLocal
from app.models import AgentWorkflow, DraftAction, Task
from sqlalchemy import delete, select


@pytest.fixture()
def clean_drafts():
    def _cleanup():
        with SessionLocal() as db:
            tasks = db.execute(select(Task).where(Task.title.like("J4 sinov%"))).scalars().all()
            for task in tasks:
                db.delete(task)
            drafts = db.execute(
                select(DraftAction).where(DraftAction.workflow_id.in_(
                    select(AgentWorkflow.id).where(AgentWorkflow.request_id.like("j4-test%"))
                ))
            ).scalars().all()
            for draft in drafts:
                db.delete(draft)
            db.execute(
                delete(AgentWorkflow).where(AgentWorkflow.request_id.like("j4-test%"))
            )
            db.commit()

    _cleanup()
    yield
    _cleanup()

def _make_draft(action_type: str = "create_task", payload: dict | None = None) -> str:
    import uuid

    with SessionLocal() as db:
        workflow = AgentWorkflow(
            request_id=f"j4-test-{uuid.uuid4().hex[:8]}",
            intent="plan_control",
            status="completed",
            input={"message": "j4 sinov"},
            context={},
            result={},
        )
        db.add(workflow)
        db.flush()
        draft = DraftAction(
            workflow_id=workflow.id,
            action_type=action_type,
            payload=payload or {
                "title": "J4 sinov vazifasi",
                "status": "open",
                "priority": "normal",
            },
            status="pending",
        )
        db.add(draft)
        db.flush()
        db.commit()
        return draft.id

def test_draft_cannot_be_executed_twice(clean_drafts):
    from app.core.errors import APIError
    from app.services import agents

    draft_id = _make_draft()
    with SessionLocal() as db:
        agents.decide_draft(db, draft_id, approve=True, actor="tester")
        with pytest.raises(APIError) as error:
            agents.decide_draft(db, draft_id, approve=True, actor="tester")
    assert error.value.status_code in (400, 409), error.value.status_code

    with SessionLocal() as db:
        tasks = db.execute(select(Task).where(Task.title == "J4 sinov vazifasi")).scalars().all()
    assert len(tasks) == 1, "amal ikki marta bajarilgan"

def test_failed_draft_can_be_retried(clean_drafts):
    from app.core.errors import APIError
    from app.services import agents

    draft_id = _make_draft(action_type="sync_legislation", payload={})

    with SessionLocal() as db:
        with pytest.raises(APIError):
            agents.decide_draft(db, draft_id, approve=True, actor="tester")

    with SessionLocal() as db:
        draft = db.get(DraftAction, draft_id)
        assert draft is not None
        assert draft.status == "failed"
        assert draft.error

    with SessionLocal() as db:
        draft = db.get(DraftAction, draft_id)
        assert draft is not None
        draft.payload = {"title": "J4 sinov vazifasi", "status": "open", "priority": "normal"}
        draft.action_type = "create_task"
        db.commit()

    with SessionLocal() as db:
        result = agents.decide_draft(db, draft_id, approve=True, actor="tester", retry=True)
    assert result["status"] == "approved"

def test_failed_draft_requires_retry_flag(clean_drafts):
    from app.core.errors import APIError
    from app.services import agents

    draft_id = _make_draft(action_type="sync_legislation", payload={})
    with SessionLocal() as db:
        with pytest.raises(APIError):
            agents.decide_draft(db, draft_id, approve=True, actor="tester")

    with SessionLocal() as db:
        with pytest.raises(APIError) as error:
            agents.decide_draft(db, draft_id, approve=True, actor="tester")
    assert error.value.status_code in (400, 409)

def test_inner_service_does_not_commit(clean_drafts, monkeypatch):
    from app.services import agents, cases

    seen: dict = {}

    _real = cases.create_task

    def _spy(db, payload, actor, request_id, *, commit=True):
        seen["commit"] = commit
        return _real(db, payload, actor, request_id, commit=False)

    monkeypatch.setattr(agents.cases, "create_task", _spy)

    draft_id = _make_draft()
    with SessionLocal() as db:
        agents.decide_draft(db, draft_id, approve=True, actor="tester")

    assert seen.get("commit") is False

def test_failed_execution_leaves_no_partial_task(clean_drafts, monkeypatch):
    from app.services import agents, cases

    original = cases.create_task

    def _wrapped(db, payload, actor, request_id, *, commit=True):
        original(db, payload, actor, request_id, commit=False)
        raise RuntimeError("Bajarishda xato")

    monkeypatch.setattr(agents.cases, "create_task", _wrapped)

    draft_id = _make_draft()
    with SessionLocal() as db:
        with pytest.raises(Exception):
            agents.decide_draft(db, draft_id, approve=True, actor="tester")

    with SessionLocal() as db:
        tasks = db.execute(select(Task).where(Task.title == "J4 sinov vazifasi")).scalars().all()
    assert not tasks, "yarim bajarilgan vazifa saqlanib qoldi"

def test_reject_is_atomic(clean_drafts):
    from app.core.errors import APIError
    from app.services import agents

    draft_id = _make_draft()
    with SessionLocal() as db:
        result = agents.decide_draft(db, draft_id, approve=False, actor="tester", note="kerak emas")
    assert result["status"] == "rejected"

    with SessionLocal() as db:
        with pytest.raises(APIError):
            agents.decide_draft(db, draft_id, approve=False, actor="tester")
