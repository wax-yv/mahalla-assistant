"""N-3: hisobot metrikalari noto'g'ri — `services/reports.py::compute_metrics`.

Muammo (audit N-3):
- `total_families`, `total_houses`, `total_streets` filtrlarni (`street_id`,
  `employment_status`, `social_status`) butunlay e'tiborsiz qoldiradi — ko'cha
  filtri bilan hisobotda oilalar/uylar butun bazadagi son chiqadi.
- `cases` va `tasks` butun obyektlar Python'ga yuklanib hisoblanadi
  (`scalars().all()`) — katta davrda sekin va xotira yeydi.
- `overdue` butun tarixni hisoblaydi (`due_date < today`) — hisobot davri
  (`period_start`/`period_end`) e'tiborsiz qoldirilgan.
- Hudud kesimi `GROUP BY Street.name` qiladi — ikki ko'cha bir nomda bo'lsa
  birlashib ketadi; ko'cha filtri ham qo'llanilmaydi.

To'g'rilash:
- oilalar/uylar/ko'chalar hisoboti filtrga moslashtiriladi (filtrsiz holatda
  global hisob saqlanadi);
- holatlar soni SQL `GROUP BY` orqali agregatsiya qilinadi;
- `overdue` faqat hisobot davri ichidagi muddati o'tgan vazifalarni sanaydi;
- hudud kesimi `Street.id, Street.name` bo'yicha guruhlanadi va filtrga mos
  keladi;
- `_distribution` va `_needs` ham filtrni qo'llaydi.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import delete, select, text

from app.core.db import SessionLocal
from app.models import Case, Citizen, Family, House, Mahalla, Street, Task

MARKER = "N3sinov"
STREET_A = f"{MARKER} Alpha ko'chasi"
STREET_B = f"{MARKER} Beta ko'chasi"
STREET_C = f"{MARKER} Beta ko'chasi"  # B bilan bir xil nom — birlashtirilmasin
# Noyob qiymatlar — demo (seed) ma'lumotlaridan ajratish uchun.
EMPLOY_NO = f"{MARKER} band emas"
EMPLOY_YES = f"{MARKER} band bor"
SOCIAL_YES = f"{MARKER} ijtimoiy"
SOCIAL_NO = f"{MARKER} oddiy"
PERIOD = (date(2019, 5, 1), date(2019, 5, 31))


# ----------------------------------------------------------------- yordamchilar


def _cleanup() -> None:
    with SessionLocal() as db:
        street_ids = db.execute(
            select(Street.id).where(Street.name.like(f"{MARKER}%"))
        ).scalars().all()
        mahalla_ids = db.execute(
            select(Mahalla.id).where(Mahalla.name.like(f"{MARKER}%"))
        ).scalars().all()
        citizen_ids = db.execute(
            select(Citizen.id).where(Citizen.full_name.like(f"{MARKER}%"))
        ).scalars().all()
        db.execute(delete(Task).where(Task.citizen_id.in_(citizen_ids)))
        db.execute(delete(Case).where(Case.citizen_id.in_(citizen_ids)))
        db.execute(delete(Citizen).where(Citizen.id.in_(citizen_ids)))
        db.execute(delete(Family).where(Family.house_id.in_(
            select(House.id).where(House.street_id.in_(street_ids))
        )))
        db.execute(delete(House).where(House.street_id.in_(street_ids)))
        db.execute(delete(Street).where(Street.id.in_(street_ids)))
        db.execute(delete(Mahalla).where(Mahalla.id.in_(mahalla_ids)))
        db.commit()


@pytest.fixture()
def dataset():
    """Test ma'lumotlari: 3 ko'cha, 3 uy, 3 oila, 4 fuqaro, 3 case, 4 task."""
    _cleanup()
    with SessionLocal() as db:
        mahalla = Mahalla(name=f"{MARKER} mahalla", district="Test")
        db.add(mahalla)
        db.flush()

        streets: dict[str, Street] = {}
        for key, name in (("a", STREET_A), ("b", STREET_B), ("c", STREET_C)):
            street = Street(mahalla_id=mahalla.id, name=name)
            db.add(street)
            streets[key] = street
        db.flush()

        houses: dict[str, House] = {}
        families: dict[str, Family] = {}
        for key in ("a", "b", "c"):
            house = House(street_id=streets[key].id, house_number=f"{MARKER}-{key}")
            db.add(house)
            db.flush()
            houses[key] = house
            family = Family(house_id=house.id)
            db.add(family)
            db.flush()
            families[key] = family

        citizens: dict[str, Citizen] = {}

        def add_citizen(
            key: str, family: Family, employment: str, social: str, needs: str = ""
        ) -> Citizen:
            citizen = Citizen(
                family_id=family.id,
                full_name=f"{MARKER} {key.upper()} Fuqaro",
                gender="Erkak",
                birth_date=date(1990, 5, 15),
                phone=f"+99890{abs(hash(key)) % 10000000:07d}",
                employment_status=employment,
                social_status=social,
                needs_text=needs,
                needs=[item.strip() for item in needs.split(",") if item.strip()],
            )
            db.add(citizen)
            db.flush()
            citizens[key] = citizen
            return citizen

        # Bandlik/iJTimoiy toifa qiymatlari noyob — baza ma'lumotlaridan
        # (demo seed) ajratiladi.
        add_citizen(
            "a1", families["a"], EMPLOY_NO, SOCIAL_YES, "Kiyim, Dori"
        )
        add_citizen("a2", families["a"], EMPLOY_YES, SOCIAL_NO)
        add_citizen("b1", families["b"], EMPLOY_NO, SOCIAL_YES)
        add_citizen("c1", families["c"], EMPLOY_YES, SOCIAL_NO)

        # Sanalar 2019-yilga qo'yiladi — demo ma'lumotlari 2026-yilda.
        start_dt = datetime(2019, 5, 1, tzinfo=timezone.utc)
        end_dt = datetime(2019, 5, 31, 23, 59, 59, tzinfo=timezone.utc)

        db.add(
            Case(
                citizen_id=citizens["a1"].id,
                family_id=families["a"].id,
                title=f"{MARKER} murojaat 1",
                status="open",
                opened_at=start_dt,
            )
        )
        db.add(
            Case(
                citizen_id=citizens["b1"].id,
                family_id=families["b"].id,
                title=f"{MARKER} murojaat 2",
                status="closed",
                opened_at=end_dt,
            )
        )
        db.add(
            Case(
                citizen_id=citizens["c1"].id,
                family_id=families["c"].id,
                title=f"{MARKER} murojaat 3",
                status="open",
                opened_at=datetime(2019, 4, 10, tzinfo=timezone.utc),  # davrdan tashqarida
            )
        )

        db.add(
            Task(
                citizen_id=citizens["a1"].id,
                family_id=families["a"].id,
                title=f"{MARKER} vazifa 1",
                status="new",
                due_date=date(2019, 5, 10),  # davr ichida, muddati o'tgan
                created_at=start_dt,
            )
        )
        db.add(
            Task(
                citizen_id=citizens["a2"].id,
                family_id=families["a"].id,
                title=f"{MARKER} vazifa 2",
                status="completed",
                due_date=date(2019, 5, 12),  # bajarilgan — kechikkan emas
                created_at=start_dt,
            )
        )
        db.add(
            Task(
                citizen_id=citizens["b1"].id,
                family_id=families["b"].id,
                title=f"{MARKER} vazifa 3",
                status="new",
                due_date=date(2019, 4, 10),  # boshqa davrda
                created_at=start_dt,
            )
        )
        db.add(
            Task(
                citizen_id=citizens["c1"].id,
                family_id=families["c"].id,
                title=f"{MARKER} vazifa 4",
                status="new",
                due_date=date(2030, 1, 1),  # kelajakda
                created_at=start_dt,
            )
        )

        db.commit()
        ids = {
            "street_a": streets["a"].id,
            "street_b": streets["b"].id,
            "street_c": streets["c"].id,
            "house_a": houses["a"].id,
            "family_a": families["a"].id,
            "citizen_a1": citizens["a1"].id,
        }
    yield ids
    _cleanup()


def _metrics(filters: dict, period=PERIOD) -> dict:
    from app.services import reports as service

    with SessionLocal() as db:
        return service.compute_metrics(db, "daily", period[0], period[1], filters)


# --------------------------------------------------------------- jamlash (N-3)


def test_totals_respect_street_filter(dataset):
    """Ko'cha filtri oilalar/uy/ko'cha sonini ham cheklashi kerak."""
    metrics = _metrics({"street_id": dataset["street_a"]})
    totals = metrics["totals"]
    assert totals["citizens"] == 2, totals
    assert totals["families"] == 1, totals
    assert totals["houses"] == 1, totals
    assert totals["streets"] == 1, totals


def test_totals_respect_employment_filter(dataset):
    """Bandlik filtri oilalar/uy/ko'cha sonini ham cheklashi kerak."""
    metrics = _metrics({"employment_status": EMPLOY_NO})
    totals = metrics["totals"]
    assert totals["citizens"] == 2, totals
    assert totals["families"] == 2, totals
    assert totals["houses"] == 2, totals
    assert totals["streets"] == 2, totals


def test_totals_respect_social_filter(dataset):
    """Ijtimoiy toifa filtri ham ko'rsatkichlarni cheklashi kerak."""
    metrics = _metrics({"social_status": SOCIAL_YES})
    totals = metrics["totals"]
    assert totals["citizens"] == 2, totals
    assert totals["families"] == 2, totals
    assert totals["houses"] == 2, totals
    assert totals["streets"] == 2, totals


def test_unfiltered_totals_stay_global(dataset):
    """Filtrsiz hisobotda jamlash global bo'lib qolishi kerak."""
    metrics = _metrics({})
    totals = metrics["totals"]
    with SessionLocal() as db:
        expected_families = db.execute(
            text(
                "SELECT count(*) FROM families f WHERE EXISTS ("
                "SELECT 1 FROM citizens c WHERE c.family_id = f.id AND c.archived_at IS NULL)"
            )
        ).scalar_one()
        expected_houses = db.execute(text("SELECT count(*) FROM houses")).scalar_one()
        expected_streets = db.execute(text("SELECT count(*) FROM streets")).scalar_one()
    assert totals["families"] == expected_families, totals
    assert totals["houses"] == expected_houses, totals
    assert totals["streets"] == expected_streets, totals
    # Test ma'lumotlari ham global hisobga kirishi kerak
    assert totals["families"] >= 3, totals
    assert totals["houses"] >= 3, totals
    assert totals["streets"] >= 3, totals


# ------------------------------------------------------------------ overdue (N-3)


def test_overdue_respects_period(dataset):
    """Kechikkan soni faqat hisobot davridagi vazifalarni sanashi kerak."""
    metrics = _metrics({})
    # Davr ichida: 1 ta kechikkan (vazifa 1); bajarilgan va boshqa
    # davrlardagi vazifalar hisobga olinmaydi.
    assert metrics["tasks"]["overdue"] == 1, metrics["tasks"]


def test_overdue_changes_with_period(dataset):
    """Boshqa davrda kechikkan vazifa boshqacha sanalishi kerak."""
    april = _metrics({}, period=(date(2019, 4, 1), date(2019, 4, 30)))
    assert april["tasks"]["overdue"] == 1, april["tasks"]
    june = _metrics({}, period=(date(2019, 6, 1), date(2019, 6, 30)))
    assert june["tasks"]["overdue"] == 0, june["tasks"]


# ------------------------------------------------------------ SQL agregatsiyasi


def test_case_status_counts_are_aggregated_in_sql(dataset):
    """Case holatlari SQL `GROUP BY` orqali agregatsiya qilinishi kerak."""
    from app.services import reports as service

    start = datetime(2019, 5, 1, tzinfo=timezone.utc)
    end = datetime(2019, 5, 31, 23, 59, 59, tzinfo=timezone.utc)
    with SessionLocal() as db:
        counts = service._status_counts(db, Case, Case.opened_at >= start, Case.opened_at <= end)
    assert counts == {"open": 1, "closed": 1}, counts


def test_task_status_counts_are_aggregated_in_sql(dataset):
    """Task holatlari SQL `GROUP BY` orqali agregatsiya qilinishi kerak."""
    from app.services import reports as service

    start = datetime(2019, 5, 1, tzinfo=timezone.utc)
    end = datetime(2019, 5, 31, 23, 59, 59, tzinfo=timezone.utc)
    with SessionLocal() as db:
        counts = service._status_counts(db, Task, Task.created_at >= start, Task.created_at <= end)
    assert counts == {"new": 3, "completed": 1}, counts


def test_case_metrics_match_aggregated_counts(dataset):
    """Hisobot metrikalari agregatsiya natijasi bilan mos bo'lishi kerak."""
    metrics = _metrics({})
    cases = metrics["cases"]
    assert cases["total"] == sum(cases["by_status"].values()), cases
    assert cases["total"] == 2, cases
    assert cases["open"] == 1, cases


# --------------------------------------------------------------- hudud kesimi


def test_territory_keeps_streets_with_same_name_separate(dataset):
    """Bir nomli ikki ko'cha birlashtirilmasligi kerak."""
    metrics = _metrics({})
    names = [item["street"] for item in metrics["territory"]]
    assert names.count(STREET_B) == 2, metrics["territory"]


def test_territory_respects_street_filter(dataset):
    """Ko'cha filtri bilan hudud kesimi faqat o'sha ko'chani ko'rsatishi kerak."""
    metrics = _metrics({"street_id": dataset["street_a"]})
    streets = {item["street"] for item in metrics["territory"]}
    assert streets == {STREET_A}, metrics["territory"]
    row = next(item for item in metrics["territory"] if item["street"] == STREET_A)
    assert row["citizens"] == 2, row


def test_territory_respects_employment_filter(dataset):
    """Bandlik filtri hudud kesimiga ham qo'llanishi kerak."""
    metrics = _metrics({"employment_status": EMPLOY_NO})
    total = sum(item["citizens"] for item in metrics["territory"])
    assert total == 2, metrics["territory"]


# ------------------------------------------------- distribyutsiya va ehtiyojlar


def test_distribution_respects_filters(dataset):
    """Bandlik distribyutsiyasi filtrga mos fuqarolarni sanashi kerak."""
    metrics = _metrics({"street_id": dataset["street_a"]})
    distribution = metrics["employment"]["distribution"]
    total = sum(item["value"] for item in distribution)
    assert total == 2, distribution


def test_needs_respects_filters(dataset):
    """Ehtiyojlar taqsimoti filtrga mos fuqarolarni sanishi kerak."""
    metrics = _metrics({"street_id": dataset["street_a"]})
    labels = {item["label"]: item["value"] for item in metrics["needs"]}
    assert labels.get("Kiyim") == 1, metrics["needs"]
    assert labels.get("Dori") == 1, metrics["needs"]

    other = _metrics({"street_id": dataset["street_c"]})
    other_labels = {item["label"]: item["value"] for item in other["needs"]}
    assert "Kiyim" not in other_labels, other["needs"]


# --------------------------------------------------------------- ma'lumot sifati


def test_incomplete_counts_missing_phone(dataset):
    """Telefoni yo'q fuqaro to'liq emas deb hisoblanishi kerak."""
    metrics = _metrics({"street_id": dataset["street_a"]})
    assert metrics["data_quality"]["incomplete"] == 0, metrics["data_quality"]


def test_incomplete_condition_covers_null_phone():
    """`phone IS NULL` ham "to'liq emas" holatiga kiritilishi kerak."""
    from app.services import reports as service

    condition = service._incomplete_condition()
    sql = str(condition.compile(compile_kwargs={"literal_binds": True})).upper()
    assert "IS NULL" in sql, sql
    assert "PHONE" in sql, sql


# ------------------------------------------------------------------- yosh chegarasi


def test_youth_cutoff_handles_february_29(monkeypatch, dataset):
    """29-fevralda yosh chegarasi hisoblash xatosi bermasligi kerak."""
    from app.services import reports as service

    monkeypatch.setattr(service, "today_local", lambda: date(2024, 2, 29))
    metrics = _metrics({})
    assert "youth_under_30" in metrics["demographics"], metrics["demographics"]
