from __future__ import annotations

from app.schemas import AppSettingsOut, AppSettingsUpdate
from app.services.admin import ALLOWED_SETTINGS


def test_settings_schema_covers_allowed():
    out_fields = set(AppSettingsOut.model_fields)
    update_fields = set(AppSettingsUpdate.model_fields)

    missing_out = ALLOWED_SETTINGS - out_fields
    missing_update = ALLOWED_SETTINGS - update_fields

    assert not missing_out, f"AppSettingsOut da yo'q: {sorted(missing_out)}"
    assert not missing_update, f"AppSettingsUpdate da yo'q: {sorted(missing_update)}"

def test_mahalla_fields_have_defaults():
    out = AppSettingsOut()
    assert out.mahalla == "Navbahor mahallasi"
    assert out.district == "Urganch shahri"
    assert out.region == "Xorazm viloyati"

def test_update_schema_accepts_territory_fields():
    payload = AppSettingsUpdate(mahalla="Yangi mahalla", district="Xorazm", region="Toshkent")
    assert payload.mahalla == "Yangi mahalla"
    assert payload.district == "Xorazm"
    assert payload.region == "Toshkent"
    assert payload.theme is None

def test_admin_settings_service_returns_territory():
    from app.core.db import SessionLocal
    from app.services import admin

    with SessionLocal() as db:
        values = admin.get_settings(db)

    assert values["mahalla"]
    assert values["district"]
    assert values["region"]

def test_admin_settings_update_accepts_territory(auth):
    client, token = auth
    headers = {"X-CSRF-Token": token}

    response = client.patch(
        "/api/v1/admin/settings",
        headers=headers,
        json={
            "values": {
                "mahalla": "Sinov mahallasi",
                "district": "Sinov tumani",
                "region": "Sinov viloyati",
            }
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["mahalla"] == "Sinov mahallasi"
    assert data["district"] == "Sinov tumani"
    assert data["region"] == "Sinov viloyati"

    restore = client.patch(
        "/api/v1/admin/settings",
        headers=headers,
        json={
            "values": {
                "mahalla": "Navbahor mahallasi",
                "district": "Urganch shahri",
                "region": "Xorazm viloyati",
            }
        },
    )
    assert restore.status_code == 200, restore.text
