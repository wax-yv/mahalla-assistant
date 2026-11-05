"""K-6: jonli admin kredensiallari ochiq hujjatlarda chiqmasligi kerak.

Muqova: `DEPLOYMENT.md`, `.env.example` va `README.md` da demo admin logini
va paroli chop etilgan edi — repo'ni ko'ruvchi har qanday prod admin panelga
kirishi mumkin edi (login limiti zaifligi bilan birga — K-2).

Yechim:
1. Ochiq hujjatlardan kredensial qiymatlari olib tashlandi.
2. Standart demo qiymati faqat kodda (`core/config.py`) qoladi; ishlab
   chiqarishda (`DEMO_MODE=false`) u admin paroli sifatida ishlatilmaydi.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_public_docs_do_not_contain_admin_credentials():
    """Ochiq hujjatlarda demo login/parol qiymatlari bo'lmasligi kerak."""
    for relative in ("DEPLOYMENT.md", ".env.example", "README.md"):
        text = _read(relative)
        assert "waxs" not in text, f"{relative} da admin paroli topildi"
        # `wax` — faqat GitHub foydalanuvchi nomi sifatida qolishi mumkin
        # (`wax-yv/mahalla-assistant`), alohida credential sifatida emas.
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "wax-yv" in stripped:
                continue
            assert "wax" not in stripped, f"{relative}: {stripped}"


def test_admin_username_env_is_documented_without_value():
    """.env.example kredensial qiymatini ko'rsatmasligi, faqat yo'nalish berishi kerak."""
    text = _read(".env.example")
    assert "ADMIN_USERNAME" in text
    assert "ADMIN_PASSWORD" in text
    active = [
        line
        for line in text.splitlines()
        if line.strip().startswith("ADMIN_")
    ]
    assert not active, active


def test_production_without_demo_mode_rejects_default_password(monkeypatch):
    """Ishlab chiqarishda standart parol bilan admin yaratilmasligi kerak."""
    from app.core import config

    class _FakeSettings:
        is_production = True
        demo_mode = False
        admin_password = "waxs"

    monkeypatch.setattr(config, "settings", _FakeSettings())
    with pytest.raises(RuntimeError):
        config.assert_admin_password_allowed()


def test_production_with_demo_mode_is_allowed(monkeypatch):
    """Demo rejimi (`DEMO_MODE=true`) saqlanadi — standart kirish buzilmaydi."""
    from app.core import config

    class _FakeSettings:
        is_production = True
        demo_mode = True
        admin_password = "waxs"

    monkeypatch.setattr(config, "settings", _FakeSettings())
    config.assert_admin_password_allowed()


def test_production_with_strong_password_is_allowed(monkeypatch):
    """Kuchli parol bilan ishlab chiqarish ishlaydi."""
    from app.core import config

    class _FakeSettings:
        is_production = True
        demo_mode = False
        admin_password = "kuchli-parol-123"

    monkeypatch.setattr(config, "settings", _FakeSettings())
    config.assert_admin_password_allowed()


def test_development_never_blocks_seed(monkeypatch):
    """Development muhitida seed hech qachon to'xtatilmasligi kerak."""
    from app.core import config

    class _FakeSettings:
        is_production = False
        demo_mode = True
        admin_password = "waxs"

    monkeypatch.setattr(config, "settings", _FakeSettings())
    config.assert_admin_password_allowed()
