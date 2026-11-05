from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import AgentRun, AgentWorkflow, Conversation, ConversationMessage, User

def _admin_id() -> str:
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.username == "wax")).scalars().first()
        assert user is not None
        return user.id

@pytest.fixture()
def clean_workflows():
    def _cleanup():
        with SessionLocal() as db:
            workflows = db.execute(
                select(AgentWorkflow).where(AgentWorkflow.request_id.like("j5-test%"))
            ).scalars().all()
            for workflow in workflows:
                db.delete(workflow)
            db.execute(delete(AgentRun).where(AgentRun.workflow_id.is_(None)))
            db.commit()

    _cleanup()
    yield
    _cleanup()

def _last_workflow() -> tuple[str, str, str]:
    with SessionLocal() as db:
        workflow = db.execute(
            select(AgentWorkflow).order_by(AgentWorkflow.created_at.desc()).limit(1)
        ).scalars().first()
        assert workflow is not None
        runs = db.execute(
            select(AgentRun).where(AgentRun.workflow_id == workflow.id)
        ).scalars().all()
        run_status = runs[0].status if runs else ""
        run_error = runs[0].error if runs else ""
        return workflow.status, run_status, run_error

def test_failed_agent_marks_run_failed(clean_workflows, monkeypatch):
    from app.services import agents

    def _boom(*args, **kwargs):
        raise RuntimeError("Agent ichki xatosi")

    monkeypatch.setitem(agents.HANDLERS, "data_stats", _boom)
    monkeypatch.setattr(agents, "detect_intent", lambda message: ("data_stats", ["data_stats"]))

    with SessionLocal() as db:
        agents.chat(db, message="ishsizlar nechta?", actor=_admin_id())

    workflow_status, run_status, run_error = _last_workflow()
    assert run_status == "failed"
    assert workflow_status == "failed"
    assert run_error

def test_chat_survives_agent_error_and_saves_message(clean_workflows, monkeypatch):
    from app.services import agents

    def _boom(*args, **kwargs):
        raise RuntimeError("Agent ichki xatosi")

    monkeypatch.setitem(agents.HANDLERS, "data_stats", _boom)
    monkeypatch.setattr(agents, "detect_intent", lambda message: ("data_stats", ["data_stats"]))

    with SessionLocal() as db:
        result = agents.chat(db, message="ishsizlar nechta?", actor=_admin_id())
        assert result["conversation_id"]
        content = result["message"].content
    assert content

    with SessionLocal() as db:
        conversation = db.get(Conversation, result["conversation_id"])
        assert conversation is not None
        messages = db.execute(
            select(ConversationMessage).where(ConversationMessage.conversation_id == conversation.id)
        ).scalars().all()
    assert any(message.role == "assistant" for message in messages)

def test_successful_agent_keeps_completed(clean_workflows):
    from app.services import agents

    with SessionLocal() as db:
        agents.chat(db, message="salom, menga qanday yordam bera olasan?", actor=_admin_id())

    workflow_status, run_status, _ = _last_workflow()
    assert run_status == "completed"
    assert workflow_status == "completed"

def test_workflow_error_is_recorded(clean_workflows, monkeypatch):
    from app.services import agents

    def _boom(*args, **kwargs):
        raise RuntimeError("Agent ichki xatosi")

    monkeypatch.setitem(agents.HANDLERS, "data_stats", _boom)
    monkeypatch.setattr(agents, "detect_intent", lambda message: ("data_stats", ["data_stats"]))

    with SessionLocal() as db:
        agents.chat(db, message="ishsizlar nechta?", actor=_admin_id())

    with SessionLocal() as db:
        workflow = db.execute(
            select(AgentWorkflow).order_by(AgentWorkflow.created_at.desc()).limit(1)
        ).scalars().first()
        assert workflow is not None
        assert workflow.error
