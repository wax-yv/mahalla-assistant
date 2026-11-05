from __future__ import annotations

import pytest
from app.core.config import settings


@pytest.fixture()
def fake_secret(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "test-cron-secret")
    yield "test-cron-secret"

@pytest.fixture()
def no_secret(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "change-me")
    yield

def test_cron_requires_authorization(client):
    response = client.get("/api/v1/cron/run-due")
    assert response.status_code in (403, 503), response.text

def test_cron_rejects_wrong_token(client, fake_secret):
    response = client.get(
        "/api/v1/cron/run-due", headers={"Authorization": "Bearer not-the-secret"}
    )
    assert response.status_code == 403, response.text

def test_cron_rejects_non_bearer_scheme(client, fake_secret):
    response = client.get(
        "/api/v1/cron/run-due", headers={"Authorization": fake_secret}
    )
    assert response.status_code == 403, response.text

def test_cron_is_disabled_without_configured_secret(client, no_secret):
    response = client.get(
        "/api/v1/cron/run-due", headers={"Authorization": "Bearer change-me"}
    )
    assert response.status_code == 503, response.text

def test_cron_runs_due_jobs_with_valid_token(client, fake_secret, monkeypatch):
    from app.services import scheduler

    called = {"count": 0}

    def _fake_run(db, limit=5):
        called["count"] += 1
        return [{"job_id": "JOB-1", "status": "completed"}]

    monkeypatch.setattr(scheduler, "run_due_jobs", _fake_run)
    response = client.get(
        "/api/v1/cron/run-due", headers={"Authorization": f"Bearer {fake_secret}"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["job_id"] == "JOB-1"
    assert called["count"] == 1

def test_cron_is_get_only(client, fake_secret):
    response = client.post(
        "/api/v1/cron/run-due", headers={"Authorization": f"Bearer {fake_secret}"}
    )
    assert response.status_code == 405, response.text

def test_vercel_json_has_cron_schedule():
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "vercel.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    crons = data.get("crons") or []
    assert any(
        item.get("path") == "/api/v1/cron/run-due" and item.get("schedule")
        for item in crons
    )
