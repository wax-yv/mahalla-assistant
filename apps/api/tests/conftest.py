from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.db import SessionLocal
from app.main import app
from app.models import RateLimit


def clear_login_limit() -> None:
    # Tests share one IP; clear the login rate-limit window before authenticating.
    with SessionLocal() as db:
        db.execute(delete(RateLimit).where(RateLimit.key.ilike("%wax%")))
        db.commit()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth(client):
    clear_login_limit()
    response = client.post("/api/v1/auth/login", json={"username": "wax", "password": "waxs"})
    assert response.status_code == 200, response.text
    token = response.json()["csrf_token"]
    return client, token
