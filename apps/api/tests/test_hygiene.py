from __future__ import annotations

from app.core.config import settings

def test_max_upload_mb_is_below_platform_limit():
    assert settings.max_upload_mb <= 3.5

def test_needs_rehash_is_wired_into_login():
    import inspect

    from app.services import auth as service

    source = inspect.getsource(service.authenticate)
    assert "needs_rehash" in source
    assert "hash_password" in source

def test_last_seen_at_is_throttled():
    import inspect

    from app.core import deps

    source = inspect.getsource(deps.get_current_session)
    assert "timedelta(minutes=5)" in source
    assert "_commit_last_seen" in source

def test_apply_status_cleanup():
    import inspect

    from app.services import cases as service

    source = inspect.getsource(service._apply_status)
    assert 'elif new_status != "completed"' not in source
    assert "else:" in source
