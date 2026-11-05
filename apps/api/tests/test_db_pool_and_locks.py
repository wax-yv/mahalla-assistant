"""O-12: serverless + Neon — ulanish puli va advisory lock.

Muammo:
- `pool_size=5, max_overflow=5` — har Vercel instansiyasi uchun 10 ta
  ulanish. Neon bepul tarifida ulanishlar tez tugab qoladi.
- `pg_advisory_lock` — **sessiya** darajasidagi lock. Pooled (PgBouncer,
  transaction mode) ulanishda `lock` va `unlock` turli backend'larda bo'lishi
  mumkin -> lock "yopiq" qolib ketadi.
- `create_all()` runtime'da chaqiriladi — u mavjud jadvalga ustun qo'shmaydi,
  ya'ni modeldagi o'zgarishlar productionda jimgina qo'llanmaydi.

To'g'rilash:
- ulanish soni cheklangan va sozlanadi (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`,
  `DB_POOL_NULL` -> NullPool);
- `pg_advisory_xact_lock` — tranzaksiya darajasida (avtomatik ozod bo'ladi);
- sxema o'zgarishlari `scripts/migrate.sql` orqali qo'lda bajariladi
  (DEPLOYMENT.md da hujjatlashtirilgan).
"""

from __future__ import annotations

from sqlalchemy import event, text

from app.core import db as db_module
from app.core.db import advisory_lock, engine

LOCK_NAME = "o12-test-lock"


def _captured_statements() -> list[str]:
    statements: list[str] = []
    return statements


def _capture_sql(statements: list[str]):
    def _listener(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    return _listener


def _advisory_lock_count() -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'")
            ).scalar_one()
        )


# --------------------------------------------------------------- pool


def test_pool_options_are_bounded():
    """PostgreSQL uchun ulanish soni chegaralangan bo'lishi kerak."""
    options = db_module.pool_options("postgresql+psycopg://user@host/db")
    assert "pool_size" in options, "pool_size belgilanmagan"
    assert "max_overflow" in options, "max_overflow belgilanmagan"
    assert options["pool_size"] <= 5, f"pool_size katta: {options['pool_size']}"
    assert options["max_overflow"] <= 5, f"max_overflow katta: {options['max_overflow']}"
    total = options["pool_size"] + options["max_overflow"]
    assert total <= 5, f"ulanshlar soni chegaradan oshdi: {total}"


def test_pool_options_for_sqlite_are_empty():
    """SQLite uchun pool parametrlari qo'yilmasligi kerak."""
    assert db_module.pool_options("sqlite:///./test.db") == {}


def test_pool_null_option_selects_nullpool(monkeypatch):
    """`DB_POOL_NULL=true` -> NullPool (serverless uchun)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "db_pool_null", True)
    options = db_module.pool_options("postgresql+psycopg://user@host/db")
    assert options.get("poolclass") is not None, "NullPool tanlanmagan"
    assert "pool_size" not in options


def test_pool_size_is_configurable(monkeypatch):
    """Pool o'lchami muhitdan o'zgartirilishi mumkin bo'lishi kerak."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "db_pool_size", 3)
    monkeypatch.setattr(settings, "db_max_overflow", 1)
    options = db_module.pool_options("postgresql+psycopg://user@host/db")
    assert options["pool_size"] == 3
    assert options["max_overflow"] == 1


# ------------------------------------------------------- advisory lock


def test_advisory_lock_is_transaction_scoped():
    """Lock tranzaksiya darajasida bo'lishi kerak (`pg_advisory_xact_lock`)."""
    statements: list[str] = []
    listener = _capture_sql(statements)
    event.listen(engine, "before_cursor_execute", listener)
    try:
        with advisory_lock(LOCK_NAME):
            pass
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    lock_statements = [s for s in statements if "pg_advisory" in s]
    assert lock_statements, "advisory lock SQL'i bajarilmadi"
    assert any("pg_advisory_xact_lock" in s for s in lock_statements), (
        f"tranzaksiya darajasidagi lock ishlatilmadi: {lock_statements}"
    )
    assert not any("pg_advisory_unlock" in s for s in lock_statements), (
        "eski sessiya darajasidagi unlock qoldirilgan"
    )


def test_advisory_lock_is_released_after_exit():
    """Lock chiqilgandan keyin ozod bo'lishi kerak."""
    before = _advisory_lock_count()
    with advisory_lock(LOCK_NAME):
        inside = _advisory_lock_count()
        assert inside >= before + 1, "lock ushlab turilmadi"
    after = _advisory_lock_count()
    assert after <= before, f"lock ozod bo'lmadi: {before} -> {after}"


def test_advisory_lock_is_released_after_error():
    """Xatolikdan keyin ham lock ozod bo'lishi kerak (yopiq qolmasin)."""
    before = _advisory_lock_count()
    try:
        with advisory_lock(LOCK_NAME):
            raise RuntimeError("sinov xatosi")
    except RuntimeError:
        pass
    after = _advisory_lock_count()
    assert after <= before, f"lock yopiq qoldi: {before} -> {after}"


# ---------------------------------------------------- sxema migratsiyasi


def test_missing_migrations_reports_actionable_items():
    """Bajarilmagan migratsiyalar aniq ko'rsatilishi kerak."""
    missing = db_module.missing_migrations()
    assert isinstance(missing, list)
    for item in missing:
        assert isinstance(item, str) and item.strip()


def test_migration_script_exists_and_is_documented():
    """Sxema o'zgarishlari `scripts/migrate.sql` orqali bajarilishi kerak."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    script = root / "scripts" / "migrate.sql"
    assert script.exists(), "scripts/migrate.sql topilmadi"
    content = script.read_text(encoding="utf-8")
    assert "ALTER TABLE" in content, "migrate.sql da ALTER TABLE yo'q"
    deployment = (root / "DEPLOYMENT.md").read_text(encoding="utf-8")
    assert "scripts/migrate.sql" in deployment, (
        "DEPLOYMENT.md migratsiya skriptini ko'rsatmaydi"
    )
