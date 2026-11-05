"""E-1/E-3/E-4/E-5: gigiyena tuzatishlari.

- E-1: `_apply_status` ortiqcha `elif` olib tashlandi;
- E-3: `needs_rehash` login bilan ulandi;
- E-4: `last_seen_at` 5 daqiqalik throttle bilan commit qilinadi;
- E-5: `max_upload_mb` 3.5 (Vercel ~4.5 MB so'rov chegarasi).
"""

from __future__ import annotations


from app.core.config import settings


def test_max_upload_mb_is_below_platform_limit():
    """4.0 MB multipart overhead bilan platforma chegarasiga yaqin edi."""
    assert settings.max_upload_mb <= 3.5


def test_needs_rehash_is_wired_into_login():
    """`authenticate` xeshni yangilashi kerak (E-3)."""
    import inspect

    from app.services import auth as service

    source = inspect.getsource(service.authenticate)
    assert "needs_rehash" in source
    assert "hash_password" in source


def test_last_seen_at_is_throttled():
    """`get_current_session` last_seen_at'ni throttle bilan commit qiladi (E-4)."""
    import inspect

    from app.core import deps

    source = inspect.getsource(deps.get_current_session)
    assert "timedelta(minutes=5)" in source
    assert "_commit_last_seen" in source


def test_apply_status_cleanup():
    """E-1: ortiqcha `elif new_status != "completed"` yo'q (oddiy `else`)."""
    import inspect

    from app.services import cases as service

    source = inspect.getsource(service._apply_status)
    assert 'elif new_status != "completed"' not in source
    assert "else:" in source
