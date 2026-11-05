from __future__ import annotations

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import Citizen


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}


def test_login_success_and_me(client):
    response = client.post("/api/v1/auth/login", json={"username": "wax", "password": "waxs"})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "admin"
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "wax"


def test_login_wrong_password(client):
    response = client.post("/api/v1/auth/login", json={"username": "wax", "password": "nope123"})
    assert response.status_code == 401


def test_protected_requires_session(client):
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app

    fresh = TestClient(fastapi_app)  # no session cookie
    assert fresh.get("/api/v1/citizens").status_code == 401


def test_csrf_required_for_writes(auth):
    """POST, PATCH va DELETE uchun CSRF tekshiruvi (N-13)."""
    client, _ = auth
    post = client.post("/api/v1/tasks", json={"title": "CSRF tekshiruvi vazifasi"})
    assert post.status_code == 403
    patch = client.patch("/api/v1/cases/YOQ-ID", json={"description": "x"})
    assert patch.status_code == 403
    delete_response = client.delete("/api/v1/documents/YOQ-ID")
    assert delete_response.status_code == 403


def test_unauthenticated_returns_401():
    """Autentifikatsiyasiz so'rov — 401 (CSRF 403 emas) (N-13)."""
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app

    fresh = TestClient(fastapi_app)
    response = fresh.get("/api/v1/citizens")
    assert response.status_code == 401


def test_citizens_list_and_filters(auth):
    client, token = auth
    response = client.get(
        "/api/v1/citizens", headers={"X-CSRF-Token": token}, params={"page_size": 5}
    )
    assert response.status_code == 200
    body = response.json()
    # N-13: seed hajmiga bog'langan majburiy son emas — mantiqiy tekshiruv.
    assert body["meta"]["total"] > 0
    assert body["meta"]["total"] >= len(body["items"])
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


# --- Bosqich 4A: AI Routing v2 + Data-Q&A ---


def test_intent_data_stats_keywords():
    from app.services.agents import detect_intent

    cases = [
        ("guruh nogironliki bor shaxslar nechta?", "data_stats"),
        ("ishsizlar nechta?", "data_stats"),
        ("Temir daftardagi fuqarolar soni", "data_stats"),
        ("Salom!", "greeting"),
        ("Bugun qaysi vazifalar?", "plan_control"),
    ]
    for message, expected in cases:
        intent, intents = detect_intent(message)
        if expected == "data_stats":
            # multi bo'lishi mumkin, lekin birlamchi data_stats bo'lishi shart
            assert intent == "data_stats" or (intent == "multi" and intents[0] == "data_stats"), (
                f"{message!r} -> {intent} {intents}"
            )
        else:
            assert intent == expected, f"{message!r} -> {intent}, kutilgan {expected}"


def test_data_stats_nogiron_counts(auth):
    client, token = auth
    response = client.post(
        "/api/v1/agents/chat",
        headers={"X-CSRF-Token": token},
        json={"message": "guruh nogironliki bor shaxslar nechta? aniq sonini ayt"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] in {"data_stats", "multi"}
    assert "reporting" in body["agents_used"] or "data_stats" in body["intent"]
    content = body["message"]["content"]
    assert "Jami" in content
    # N-13: aniq son seed'dan bog'liq — bazadan hisoblanadi (hardcoded 35 emas).
    with SessionLocal() as db:
        expected = int(
            db.execute(
                select(func.count()).select_from(Citizen).where(
                    Citizen.social_status.like("%nogironligi bor%")
                )
            ).scalar_one()
        )
    assert str(expected) in content
    assert "ISM" not in content and "EMIS" not in content


def test_data_stats_with_street_and_gender(auth):
    client, token = auth
    response = client.post(
        "/api/v1/agents/chat",
        headers={"X-CSRF-Token": token},
        json={"message": "ishsiz ayollar nechta?"},
    )
    assert response.status_code == 200
    content = response.json()["message"]["content"]
    assert "Jami" in content


def test_model_routing_order():
    from app.services.ai_gateway import available_models, order_models

    models = available_models()
    assert models, "Model registratsiyasi bo'sh"
    primary = models[-1]["id"]
    ordered = order_models(models, primary)
    assert ordered[0]["id"] == primary
    # qolganlari saqlanadi
    assert {m["id"] for m in ordered} == {m["id"] for m in models}


def test_admin_settings_validates_ai_model(auth):
    client, token = auth
    headers = {"X-CSRF-Token": token}
    bad = client.patch("/api/v1/admin/settings", headers=headers, json={"values": {"ai_model": "yolg'on-model"}})
    assert bad.status_code == 422
    good = client.patch("/api/v1/admin/settings", headers=headers, json={"values": {"ai_model": ""}})
    assert good.status_code == 200
