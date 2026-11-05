from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")

def test_public_config_has_no_admin_credentials():
    text = _read(".env.example")
    assert "waxs" not in text, ".env.example da admin paroli topildi"
    for line in text.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("ADMIN_PASSWORD="), f"parol qatori: {stripped}"

def test_admin_keys_are_absent_from_env_example():
    text = _read(".env.example")
    active = [
        line
        for line in text.splitlines()
        if line.strip().startswith("ADMIN_")
    ]
    assert not active, active

def test_production_without_demo_mode_rejects_default_password(monkeypatch):
    from app.core import config

    class _FakeSettings:
        is_production = True
        demo_mode = False
        admin_password = "waxs"

    monkeypatch.setattr(config, "settings", _FakeSettings())
    with pytest.raises(RuntimeError):
        config.assert_admin_password_allowed()

def test_production_with_demo_mode_is_allowed(monkeypatch):
    from app.core import config

    class _FakeSettings:
        is_production = True
        demo_mode = True
        admin_password = "waxs"

    monkeypatch.setattr(config, "settings", _FakeSettings())
    config.assert_admin_password_allowed()

def test_production_with_strong_password_is_allowed(monkeypatch):
    from app.core import config

    class _FakeSettings:
        is_production = True
        demo_mode = False
        admin_password = "kuchli-parol-123"

    monkeypatch.setattr(config, "settings", _FakeSettings())
    config.assert_admin_password_allowed()

def test_development_never_blocks_seed(monkeypatch):
    from app.core import config

    class _FakeSettings:
        is_production = False
        demo_mode = True
        admin_password = "waxs"

    monkeypatch.setattr(config, "settings", _FakeSettings())
    config.assert_admin_password_allowed()
