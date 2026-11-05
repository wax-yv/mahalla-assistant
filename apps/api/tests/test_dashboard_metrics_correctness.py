"""N-2: dashboard noto'g'ri hisoblar — `services/dashboard.py`.

Muammo (audit N-2):
- `updated_today` hisobida `archived_at IS NULL` filtr yo'q — raqam va
  ulush mos kelmaydi (arxivlangan fuqarolar ham sanab qo'yiladi).
- Telefoni `NULL` bo'lgan fuqaro "to'liq emas" deb hisoblanmaydi
  (`phone == ""` faqat bo'sh satrni aniqlaydi).
- `_distribution` da foizlar **top-12** qatorlar yig'indisi bo'yicha
  hisoblanadi — haqiqiy jami boshqa, foizlar 100% ga yetmaydi.
- Ustuvorlik tartibi string bo'yicha (`priority.desc()`) — "urgent" oxirgi
  chiqadi (alphabetik: high < low < normal < urgent).
- `_needs_distribution` barcha `needs_text` ni birdan yuklaydi — katta
  bazada xotira (OOM) xavfi.
- `activity_page` yorliqlari lug'ati to'liq emas (5/18) — texnik kalitlar
  (`case.created`) foydalanuvchiga ko'rinadi.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import delete, func, select

from app.core.db import SessionLocal
from app.models import AuditLog, Citizen, Task

MARKER = "N2sinov"
EDUCATION_COUNT = 15  # 12 dan ko'p guruh — top-12 yetarli bo'lmasligi uchun


# ----------------------------------------------------------------- yordamchilar


def _cleanup() -> None:
    with SessionLocal() as db:
        db.execute(delete(Task).where(Task.title.like(f"{MARKER}%")))
        db.execute(delete(Citizen).where(Citizen.full_name.like(f"{MARKER}%")))
        db.execute(
            delete(AuditLog).where(AuditLog.entity_id.like(f"{MARKER}%"))
        )
        db.commit()


@pytest.fixture()
def dataset():
    _cleanup()
    with SessionLocal() as db:
        # 15 ta turli ta'lim qiymati — top-12 dan ko'p guruh.
        for index in range(EDUCATION_COUNT):
            db.add(
                Citizen(
                    full_name=f"{MARKER} ta'lim {index}",
                    gender="Erkak",
                    birth_date=date(1990, 1, 1),
                    phone="+998900000001",
                    education=f"{MARKER} ta'lim {index}",
                )
            )
        # Tug'ilgan sanasi yo'q fuqaro — "to'liq emas" hisobiga kiradi.
        db.add(
            Citizen(
                full_name=f"{MARKER} sanasiz",
                gender="Ayol",
                birth_date=None,
                phone="+998900000002",
            )
        )
        # Arxivlangan, bugun yangilangan fuqaro — `updated_today` ga
        # kirishi kerak emas.
        archived = Citizen(
            full_name=f"{MARKER} arxivlangan",
            gender="Erkak",
            birth_date=date(1980, 1, 1),
            phone="+998900000003",
        )
        archived.archived_at = datetime.now(timezone.utc)
        archived.updated_at = datetime.now(timezone.utc)
        db.add(archived)
        # Faol, bugun yangilangan fuqaro — `updated_today` ga kirishi kerak.
        fresh = Citizen(
            full_name=f"{MARKER} yangilangan",
            gender="Erkak",
            birth_date=date(1985, 1, 1),
            phone="+998900000004",
        )
        fresh.updated_at = datetime.now(timezone.utc)
        db.add(fresh)
        # Ehtiyoji bor fuqaro.
        db.add(
            Citizen(
                full_name=f"{MARKER} ehtiyojli",
                gender="Erkak",
                birth_date=date(1992, 2, 2),
                phone="+998900000005",
                needs_text="Kiyim, Dori",
            )
        )
        # Top-10 ga kiradigan noyob ehtiyoj (40 ta fuqaro).
        for index in range(40):
            db.add(
                Citizen(
                    full_name=f"{MARKER} maxsus {index}",
                    gender="Erkak",
                    birth_date=date(1993, 3, 3),
                    phone=f"+9989000000{index:02d}",
                    needs_text=f"{MARKER} maxsus ehtiyoj",
                )
            )
        db.flush()

        today = date.today()
        for priority in ("low", "normal", "high", "urgent"):
            db.add(
                Task(
                    title=f"{MARKER} vazifa {priority}",
                    status="new",
                    priority=priority,
                    due_date=today,
                )
            )
        db.flush()

        for action in ("case.created", "document.uploaded", "report.generated"):
            db.add(
                AuditLog(
                    actor_type="user",
                    actor_id="tester",
                    action=action,
                    entity_type="test",
                    entity_id=f"{MARKER}-{action}",
                    new_value={"title": f"{MARKER} {action}"},
                )
            )
        db.commit()
    yield
    _cleanup()


# ------------------------------------------------------------------- distribyutsiya


def test_distribution_percent_uses_real_total(dataset):
    """Foiz haqiqiy jami fuqaro bo'yicha hisoblanishi kerak."""
    from app.services import dashboard as service

    with SessionLocal() as db:
        total = int(
            db.execute(
                select(func.count()).select_from(Citizen).where(Citizen.archived_at.is_(None))
            ).scalar_one()
        )
        rows = service._distribution(db, Citizen.education)
        assert len(rows) == 12, "top-12 chegarasi buzilgan"
        assert sum(row["value"] for row in rows) < total, (
            "top-12 jami butun jami bilan teng — test ma'lumotlari yetarli emas"
        )
        for row in rows:
            expected = round(row["value"] / total * 100, 1)
            assert row["percent"] == expected, row


def test_summary_distribution_percent_matches_total(dataset):
    """`summary()` ichidagi foizlar ham haqiqiy jami bo'yicha bo'lishi kerak."""
    from app.services import dashboard as service

    with SessionLocal() as db:
        payload = service.summary(db)
        total = int(
            db.execute(
                select(func.count()).select_from(Citizen).where(Citizen.archived_at.is_(None))
            ).scalar_one()
        )
    for row in payload["education"]:
        expected = round(row["value"] / total * 100, 1)
        assert row["percent"] == expected, row


# ------------------------------------------------------------------ ma'lumot sifati


def test_incomplete_counts_citizen_without_birth_date(dataset):
    """Tug'ilgan sanasi yo'q fuqaro "to'liq emas" hisobiga kirishi kerak."""
    from app.services import dashboard as service

    with SessionLocal() as db:
        payload = service.summary(db)
        total = int(
            db.execute(
                select(func.count()).select_from(Citizen).where(Citizen.archived_at.is_(None))
            ).scalar_one()
        )
    quality = payload["data_quality"]
    assert quality["incomplete"] >= 1, quality
    assert quality["complete"] + quality["incomplete"] == total, quality


def test_incomplete_condition_covers_null_phone():
    """`phone IS NULL` ham "to'liq emas" holatiga kiritilishi kerak."""
    from app.services import dashboard as service

    condition = service._incomplete_condition()
    sql = str(condition.compile(compile_kwargs={"literal_binds": True})).upper()
    assert "PHONE" in sql, sql
    assert "IS NULL" in sql, sql


def test_updated_today_excludes_archived(dataset):
    """Arxivlangan fuqaro `updated_today` ga kirmasligi kerak."""
    from app.services import dashboard as service

    with SessionLocal() as db:
        payload = service.summary(db)
    updated_today = payload["data_quality"]["updated_today"]
    with SessionLocal() as db:
        active = int(
            db.execute(
                select(func.count())
                .select_from(Citizen)
                .where(
                    Citizen.archived_at.is_(None),
                    Citizen.updated_at >= datetime.now(timezone.utc) - __import__("datetime").timedelta(days=1),
                )
            ).scalar_one()
        )
    assert updated_today == active, (updated_today, active)


# ------------------------------------------------------------------- ustuvorlik


def test_today_tasks_are_ordered_by_real_priority(dataset):
    """Ustuvorlik tartibi: urgent > high > normal > low."""
    from app.services import dashboard as service

    with SessionLocal() as db:
        payload = service.summary(db)
    priorities = [row["priority"] for row in payload["today_tasks"]]
    test_priorities = [item for item in priorities if item in {"urgent", "high", "normal", "low"}]
    assert test_priorities, priorities
    order = {"urgent": 4, "high": 3, "normal": 2, "low": 1}
    assert test_priorities == sorted(test_priorities, key=lambda item: order[item], reverse=True), (
        test_priorities
    )


def test_dashboard_tasks_are_ordered_by_real_priority(dataset):
    """`dashboard_tasks()` ham xuddi shu tartibda bo'lishi kerak."""
    from app.services import dashboard as service

    with SessionLocal() as db:
        payload = service.dashboard_tasks(db)
    priorities = [row["priority"] for row in payload["today"]]
    test_priorities = [item for item in priorities if item in {"urgent", "high", "normal", "low"}]
    assert test_priorities, priorities
    order = {"urgent": 4, "high": 3, "normal": 2, "low": 1}
    assert test_priorities == sorted(test_priorities, key=lambda item: order[item], reverse=True), (
        test_priorities
    )

# ------------------------------------------------------------------- ehtiyojlar


def test_needs_distribution_chunks_are_bounded(dataset):
    """Ehtiyoj matnlari chegadan oshmasdan, bo'laklab o'qilishi kerak."""
    from app.services import dashboard as service

    with SessionLocal() as db:
        chunks = list(service._iter_needs_text(db))
    assert chunks, "ehtiyojlar bo'sh qaytarildi"
    assert all(len(chunk) <= service.NEEDS_CHUNK_SIZE for chunk in chunks)


def test_needs_distribution_counts_all_entries(dataset):
    """Ehtiyojlar taqsimoti top-10 ni to'g'ri hisoblaydi."""
    from app.services import dashboard as service

    with SessionLocal() as db:
        rows = service._needs_distribution(db)
        texts = db.execute(
            select(Citizen.needs_text).where(
                Citizen.archived_at.is_(None), Citizen.needs_text != ""
            )
        ).scalars().all()
    expected: dict[str, int] = {}
    for text in texts:
        for item in str(text).split(","):
            item = item.strip()
            if item:
                expected[item] = expected.get(item, 0) + 1
    top = sorted(expected.items(), key=lambda item: item[1], reverse=True)[:10]
    assert [row["label"] for row in rows] == [label for label, _ in top], rows
    assert [row["value"] for row in rows] == [value for _, value in top], rows
    labels = {row["label"]: row["value"] for row in rows}
    assert labels.get(f"{MARKER} maxsus ehtiyoj") == 40, labels
    total = sum(expected.values())
    for row in rows:
        assert row["percent"] == round(row["value"] / total * 100, 1), row


# ------------------------------------------------------------------- faoliyat


def test_activity_page_labels_are_humanised(dataset):
    """`activity_page` texnik kalitlarni ko'rsatmasligi kerak."""
    from app.services import dashboard as service

    with SessionLocal() as db:
        items, _meta = service.activity_page(db, 1, 50)
    titles = {item["action"]: item["title"] for item in items}
    assert titles.get("case.created") == "Yangi case ochildi", titles
    assert titles.get("document.uploaded") == "Hujjat yuklandi", titles
    assert titles.get("report.generated") == "Hisobot yaratildi", titles


def test_activity_page_covers_all_known_actions(dataset):
    """Lug'at barcha amallarni qamrab olishi kerak."""
    from app.services import dashboard as service

    known = {
        "auth.login",
        "auth.logout",
        "auth.login_failed",
        "citizen.created",
        "citizen.updated",
        "citizen.archived",
        "case.created",
        "case.updated",
        "task.created",
        "task.updated",
        "task.completed",
        "task.cancelled",
        "work_log.created",
        "document.uploaded",
        "document.imported",
        "report.generated",
        "report.approved",
        "agent.chat",
        "settings.updated",
    }
    missing = known - set(service.ACTION_LABELS)
    assert not missing, f"yorliq yo'q: {missing}"


def test_recent_activity_and_activity_page_use_same_labels(dataset):
    """Ikkala ro'yxat ham bitta lug'atdan foydalanishi kerak."""
    from app.services import dashboard as service

    with SessionLocal() as db:
        recent = service.recent_activity(db, limit=50)
        paged, _meta = service.activity_page(db, 1, 50)
    by_id = {item["id"]: item["title"] for item in paged}
    for item in recent:
        if item["id"] in by_id:
            assert by_id[item["id"]] == item["title"], item
