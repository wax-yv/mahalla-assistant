from __future__ import annotations

from app.core import db as db_module
from app.core.db import advisory_lock, engine
from sqlalchemy import event, text

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

def test_pool_options_are_bounded():
    options = db_module.pool_options("postgresql+psycopg://user@host/db")
    assert "pool_size" in options, "pool_size belgilanmagan"
    assert "max_overflow" in options, "max_overflow belgilanmagan"
    assert options["pool_size"] <= 5, f"pool_size katta: {options['pool_size']}"
    assert options["max_overflow"] <= 5, f"max_overflow katta: {options['max_overflow']}"
    total = options["pool_size"] + options["max_overflow"]
    assert total <= 5, f"ulanshlar soni chegaradan oshdi: {total}"

def test_pool_options_for_sqlite_are_empty():
    assert db_module.pool_options("sqlite:///./test.db") == {}

def test_pool_null_option_selects_nullpool(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "db_pool_null", True)
    options = db_module.pool_options("postgresql+psycopg://user@host/db")
    assert options.get("poolclass") is not None, "NullPool tanlanmagan"
    assert "pool_size" not in options

def test_pool_size_is_configurable(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "db_pool_size", 3)
    monkeypatch.setattr(settings, "db_max_overflow", 1)
    options = db_module.pool_options("postgresql+psycopg://user@host/db")
    assert options["pool_size"] == 3
    assert options["max_overflow"] == 1

def test_advisory_lock_is_transaction_scoped():
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
    before = _advisory_lock_count()
    with advisory_lock(LOCK_NAME):
        inside = _advisory_lock_count()
        assert inside >= before + 1, "lock ushlab turilmadi"
    after = _advisory_lock_count()
    assert after <= before, f"lock ozod bo'lmadi: {before} -> {after}"

def test_advisory_lock_is_released_after_error():
    before = _advisory_lock_count()
    try:
        with advisory_lock(LOCK_NAME):
            raise RuntimeError("sinov xatosi")
    except RuntimeError:
        pass
    after = _advisory_lock_count()
    assert after <= before, f"lock yopiq qoldi: {before} -> {after}"

def test_missing_migrations_reports_actionable_items():
    missing = db_module.missing_migrations()
    assert isinstance(missing, list)
    for item in missing:
        assert isinstance(item, str) and item.strip()

def test_migration_script_exists_and_is_documented():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    script = root / "scripts" / "migrate.sql"
    assert script.exists(), "scripts/migrate.sql topilmadi"
    content = script.read_text(encoding="utf-8")
    assert "ALTER TABLE" in content, "migrate.sql da ALTER TABLE yo'q"
