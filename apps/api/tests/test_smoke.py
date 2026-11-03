from __future__ import annotations


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}


def test_login_success_and_me(client):
    from tests.conftest import clear_login_limit

    clear_login_limit()
    response = client.post("/api/v1/auth/login", json={"username": "wax", "password": "waxs"})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "admin"
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "wax"


def test_login_wrong_password(client):
    from tests.conftest import clear_login_limit

    clear_login_limit()
    response = client.post("/api/v1/auth/login", json={"username": "wax", "password": "nope123"})
    assert response.status_code == 401


def test_protected_requires_session(client):
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app

    fresh = TestClient(fastapi_app)  # no session cookie
    assert fresh.get("/api/v1/citizens").status_code == 401


def test_csrf_required_for_writes(auth):
    client, _ = auth
    response = client.post(
        "/api/v1/tasks",
        json={"title": "CSRF tekshiruvi vazifasi"},
    )
    assert response.status_code == 403


def test_citizens_list_and_filters(auth):
    client, token = auth
    response = client.get(
        "/api/v1/citizens", headers={"X-CSRF-Token": token}, params={"page_size": 5}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] >= 1000
    assert len(body["items"]) == 5
    filtered = client.get(
        "/api/v1/citizens",
        headers={"X-CSRF-Token": token},
        params={"employment_status": "Ishsiz", "page_size": 5},
    )
    assert filtered.status_code == 200
    assert all(item["employment_status"] == "Ishsiz" for item in filtered.json()["items"])


def test_citizen_detail(auth):
    client, token = auth
    listing = client.get("/api/v1/citizens", params={"page_size": 1}).json()
    citizen_id = listing["items"][0]["id"]
    response = client.get(f"/api/v1/citizens/{citizen_id}", headers={"X-CSRF-Token": token})
    assert response.status_code == 200
    assert response.json()["full_name"]


def test_task_create_and_complete(auth):
    client, token = auth
    headers = {"X-CSRF-Token": token}
    created = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"title": "Test vazifasi — avtomatik", "category": "Boshqa", "priority": "low"},
    )
    assert created.status_code == 201, created.text
    task = created.json()
    completed = client.post(
        f"/api/v1/tasks/{task['id']}/complete",
        headers=headers,
        json={"evidence_note": "Test davomida bajarildi."},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"


def test_case_create(auth):
    client, token = auth
    response = client.post(
        "/api/v1/cases",
        headers={"X-CSRF-Token": token},
        json={"title": "Test murojaati — avtomatik", "category": "Boshqa"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "open"


def test_programs_list_and_match(auth):
    client, token = auth
    programs = client.get("/api/v1/programs").json()["items"]
    assert len(programs) >= 5
    listing = client.get("/api/v1/citizens", params={"page_size": 1}).json()
    matches = client.post(
        "/api/v1/programs/match",
        json={"citizen_id": listing["items"][0]["id"]},
    )
    assert matches.status_code == 200
    assert len(matches.json()["items"]) >= 1


def test_legislation_status_and_search(auth):
    client, token = auth
    status = client.get("/api/v1/legislation/status")
    assert status.status_code == 200
    assert status.json()["documents"] >= 1
    hits = client.get("/api/v1/legislation/search", params={"q": "murojaat"})
    assert hits.status_code == 200


def test_agent_chat_credit_asks_bank_first(auth):
    client, token = auth
    response = client.post(
        "/api/v1/agents/chat",
        headers={"X-CSRF-Token": token},
        json={"message": "Kredit olishni xohlayman"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "credit_subsidy"
    assert "bank" in body["message"]["content"].lower()
    assert body["requires_approval"] is False


def test_agent_chat_plan_control(auth):
    client, token = auth
    response = client.post(
        "/api/v1/agents/chat",
        headers={"X-CSRF-Token": token},
        json={"message": "Bugun qaysi vazifalarga e'tibor berishim kerak?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "plan_control"
    assert "vazifa" in body["message"]["content"].lower()


def test_admin_settings_and_audit(auth):
    client, token = auth
    headers = {"X-CSRF-Token": token}
    settings = client.get("/api/v1/admin/settings", headers=headers)
    assert settings.status_code == 200
    audit = client.get("/api/v1/admin/audit", headers=headers)
    assert audit.status_code == 200
    assert audit.json()["meta"]["total"] >= 1
