"""J-15: `admin/settings` sxema drift — `ALLOWED_SETTINGS` va sxema mosligi.

Muammo: `ALLOWED_SETTINGS` da `mahalla`, `district`, `region` bor, lekin
`AppSettingsOut`/`AppSettingsUpdate` da bu maydonlar yo'q edi — admin panel
sozlamalari to'liq ko'rinmasdi (va `response_model` ishlatilsa, maydonlar
javobdan kesilib qolardi).
"""

from __future__ import annotations

from app.schemas import AppSettingsOut, AppSettingsUpdate
from app.services.admin import ALLOWED_SETTINGS


def test_settings_schema_covers_allowed():
    """Har bir `ALLOWED_SETTINGS` kaliti sxemalarda mavjud bo'lishi kerak."""
    out_fields = set(AppSettingsOut.model_fields)
    update_fields = set(AppSettingsUpdate.model_fields)

    missing_out = ALLOWED_SETTINGS - out_fields
    missing_update = ALLOWED_SETTINGS - update_fields

    assert not missing_out, f"AppSettingsOut da yo'q: {sorted(missing_out)}"
    assert not missing_update, f"AppSettingsUpdate da yo'q: {sorted(missing_update)}"


def test_mahalla_fields_have_defaults():
    """Yangi maydonlar `get_settings` defaultlariga mos bo'lishi kerak."""
    out = AppSettingsOut()
    assert out.mahalla == "Navbahor mahallasi"
    assert out.district == "Urganch shahri"
    assert out.region == "Xorazm viloyati"


def test_update_schema_accepts_territory_fields():
    """Sozlamalarni yangilashda maydonlar qabul qilinishi kerak."""
    payload = AppSettingsUpdate(mahalla="Yangi mahalla", district="Xorazm", region="Toshkent")
    assert payload.mahalla == "Yangi mahalla"
    assert payload.district == "Xorazm"
    assert payload.region == "Toshkent"
    # Berilmagan maydonlar `None` bo'lib qoladi (qisman yangilash mumkin).
    assert payload.theme is None


def test_admin_settings_service_returns_territory():
    """Servis ham yangi maydonlarni qaytarishi kerak."""
    from app.core.db import SessionLocal
    from app.services import admin

    with SessionLocal() as db:
        values = admin.get_settings(db)

    assert values["mahalla"]
    assert values["district"]
    assert values["region"]


def test_admin_settings_update_accepts_territory(auth):
    """Admin panel orqali mahalla/district/region yangilanishi kerak."""
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

    # Qaytarib qo'yamiz (jamoaviy sozlamalarni buzmaslik uchun).
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
