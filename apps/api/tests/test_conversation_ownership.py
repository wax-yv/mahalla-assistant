from __future__ import annotations

import pytest
from app.core.db import SessionLocal
from app.models import Conversation, User
from sqlalchemy import delete, select


def _ensure_user(username: str, role: str, permissions: list[str]) -> str:
    from app.core.security import hash_password

    with SessionLocal() as db:
        user = db.execute(select(User).where(User.username == username)).scalars().first()
        if user is None:
            user = User(
                username=username,
                display_name=username,
                password_hash=hash_password("test-pass-123"),
                role=role,
                permissions=permissions,
            )
            db.add(user)
        else:
            user.role = role
            user.permissions = permissions
            user.is_active = True
        db.flush()
        db.commit()
        return user.id

def _cleanup() -> None:
    with SessionLocal() as db:
        db.execute(delete(User).where(User.username == "k8-operator"))
        db.execute(delete(Conversation).where(Conversation.user_id.is_(None)))
        db.commit()

@pytest.fixture()
def operator():
    _cleanup()
    user_id = _ensure_user("k8-operator", "operator", ["agents.use"])
    yield user_id
    _cleanup()

def _login(client, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]

def test_conversation_has_owner(auth):
    client, token = auth
    response = client.post("/api/v1/agents/chat", headers={"X-CSRF-Token": token}, json={"message": "salom"})
    assert response.status_code == 200
    conversation_id = response.json()["conversation_id"]
    with SessionLocal() as db:
        conversation = db.get(Conversation, conversation_id)
        assert conversation is not None
        assert conversation.user_id is not None

def test_other_user_cannot_read_conversation(auth, operator, client):
    _admin, admin_token = auth
    created = client.post(
        "/api/v1/agents/chat", headers={"X-CSRF-Token": admin_token}, json={"message": "salom"}
    )
    conversation_id = created.json()["conversation_id"]

    _login(client, "k8-operator", "test-pass-123")
    response = client.get(f"/api/v1/agents/conversations/{conversation_id}")
    assert response.status_code == 404, response.text

def test_other_user_cannot_delete_conversation(auth, operator, client):
    _admin, admin_token = auth
    created = client.post(
        "/api/v1/agents/chat", headers={"X-CSRF-Token": admin_token}, json={"message": "salom"}
    )
    conversation_id = created.json()["conversation_id"]

    operator_token = _login(client, "k8-operator", "test-pass-123")
    response = client.delete(
        f"/api/v1/agents/conversations/{conversation_id}",
        headers={"X-CSRF-Token": operator_token},
    )
    assert response.status_code == 404, response.text
    with SessionLocal() as db:
        assert db.get(Conversation, conversation_id) is not None

def test_other_user_cannot_continue_conversation(auth, operator, client):
    _admin, admin_token = auth
    created = client.post(
        "/api/v1/agents/chat", headers={"X-CSRF-Token": admin_token}, json={"message": "salom"}
    )
    conversation_id = created.json()["conversation_id"]

    operator_token = _login(client, "k8-operator", "test-pass-123")
    response = client.post(
        "/api/v1/agents/chat",
        headers={"X-CSRF-Token": operator_token},
        json={"message": "salom", "conversation_id": conversation_id},
    )
    assert response.status_code == 404, response.text

def test_conversation_list_is_scoped_to_owner(auth, operator, client):
    _admin, admin_token = auth
    created = client.post(
        "/api/v1/agents/chat", headers={"X-CSRF-Token": admin_token}, json={"message": "salom"}
    )
    conversation_id = created.json()["conversation_id"]

    _login(client, "k8-operator", "test-pass-123")
    response = client.get("/api/v1/agents/conversations")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert conversation_id not in ids

def test_delete_archives_instead_of_purging(auth, operator, client):
    _admin, admin_token = auth
    created = client.post(
        "/api/v1/agents/chat", headers={"X-CSRF-Token": admin_token}, json={"message": "salom"}
    )
    conversation_id = created.json()["conversation_id"]

    response = client.delete(
        f"/api/v1/agents/conversations/{conversation_id}",
        headers={"X-CSRF-Token": admin_token},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("purged") is False
    with SessionLocal() as db:
        conversation = db.get(Conversation, conversation_id)
        assert conversation is not None
        assert conversation.archived_at is not None

def test_purge_requires_admin(auth, operator, client):
    operator_token = _login(client, "k8-operator", "test-pass-123")
    created = client.post(
        "/api/v1/agents/chat",
        headers={"X-CSRF-Token": operator_token},
        json={"message": "salom"},
    )
    conversation_id = created.json()["conversation_id"]

    response = client.delete(
        f"/api/v1/agents/conversations/{conversation_id}",
        headers={"X-CSRF-Token": operator_token},
        params={"purge": "true"},
    )
    assert response.status_code == 403, response.text

def test_migration_script_contains_conversation_owner():
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "scripts" / "migrate.sql"
    text = path.read_text(encoding="utf-8")
    assert "conversations" in text
    assert "user_id" in text

def test_preference_of_foreign_conversation_is_not_readable(auth, operator, client):
    _admin, admin_token = auth
    created = client.post(
        "/api/v1/agents/chat", headers={"X-CSRF-Token": admin_token}, json={"message": "salom"}
    )
    conversation_id = created.json()["conversation_id"]

    _login(client, "k8-operator", "test-pass-123")
    response = client.get(f"/api/v1/programs/preference/{conversation_id}")
    assert response.status_code == 404, response.text
