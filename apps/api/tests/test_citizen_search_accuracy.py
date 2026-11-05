from __future__ import annotations

import pytest
from sqlalchemy import delete

from app.core.db import SessionLocal
from app.models import Citizen
from app.services import agents

FAMILY = "Testovsinov"
GIVEN = "Testism"
PREFIX = f"{FAMILY} {GIVEN}"

@pytest.fixture()
def clean_citizens():
    def _cleanup():
        with SessionLocal() as db:
            db.execute(delete(Citizen).where(Citizen.full_name.like(f"{FAMILY}%")))
            db.commit()

    _cleanup()
    yield
    _cleanup()

def _make_citizen(suffix: str, birth_year: int = 1990, phone: str = "+998900000001") -> str:
    from datetime import date

    with SessionLocal() as db:
        citizen = Citizen(
            full_name=f"{PREFIX} {suffix}".strip(),
            gender="Erkak",
            birth_date=date(birth_year, 5, 15),
            phone=phone,
        )
        db.add(citizen)
        db.commit()
        return citizen.id

def test_single_name_token_does_not_match(clean_citizens):
    _make_citizen("")

    with SessionLocal() as db:
        matches = agents._citizen_search(db, "Testism")

    assert matches == [], f"bitta token bilan moslik topildi: {matches}"

def test_single_name_token_with_context_does_not_match(clean_citizens):
    _make_citizen("")

    with SessionLocal() as db:
        matches = agents._citizen_search(db, "Testism haqida ma'lumot bering")

    assert matches == [], f"bitta token bilan moslik topildi: {matches}"

def test_surname_and_firstname_match(clean_citizens):
    citizen_id = _make_citizen("")

    with SessionLocal() as db:
        matches = agents._citizen_search(db, "Testovsinov Testism haqida ma'lumot bering")

    assert len(matches) == 1, f"kutilgan 1 moslik, topildi: {len(matches)}"
    assert matches[0].id == citizen_id

def test_cyrillic_name_is_found(clean_citizens):
    with SessionLocal() as db:
        citizen = Citizen(
            full_name="Тестовсинов Тестисм",
            gender="Erkak",
            birth_date=None,
            phone="+998900000002",
        )
        db.add(citizen)
        db.commit()
        citizen_id = citizen.id

    try:
        with SessionLocal() as db:
            matches = agents._citizen_search(db, "Тестовсинов Тестисм")

        assert len(matches) == 1, f"kirill ism topilmadi: {len(matches)}"
        assert matches[0].id == citizen_id
    finally:
        with SessionLocal() as db:
            db.execute(delete(Citizen).where(Citizen.full_name.like("Тестовсинов%")))
            db.commit()

def test_phone_search_still_works(clean_citizens):
    citizen_id = _make_citizen("Telefonli", phone="+998900000003")

    with SessionLocal() as db:
        matches = agents._citizen_search(db, "+998900000003 raqamli fuqaro")

    assert len(matches) == 1, f"telefon orqali topilmadi: {len(matches)}"
    assert matches[0].id == citizen_id

def test_ambiguous_names_return_all_candidates(clean_citizens):
    first = _make_citizen("Birinchi", phone="+998900000004")
    second = _make_citizen("Ikkinchi", phone="+998900000005")

    with SessionLocal() as db:
        matches = agents._citizen_search(db, "Testovsinov Testism haqida ma'lumot")

    ids = {citizen.id for citizen in matches}
    assert len(matches) == 2, f"kutilgan 2 nomzod, topildi: {len(matches)}"
    assert ids == {first, second}

def test_lookup_asks_to_clarify_when_multiple(clean_citizens):
    _make_citizen("Birinchi", phone="+998900000006")
    _make_citizen("Ikkinchi", phone="+998900000007")

    with SessionLocal() as db:
        result = agents._citizen_lookup(db, "Testovsinov Testism haqida ma'lumot", {})

    assert result["confidence"] == "medium"
    assert len(result["data"]["matches"]) >= 2
    assert "aniqlashtiring" in result["text"].lower()
    assert result["data"]["total"] == len(result["data"]["matches"]) or (
        result["data"]["total"] > len(result["data"]["matches"])
    )

def test_single_match_confirms_name_and_birth_year(clean_citizens):
    _make_citizen("Yagona", birth_year=1988, phone="+998900000008")

    with SessionLocal() as db:
        result = agents._citizen_lookup(db, "Testovsinov Testism haqida ma'lumot", {})

    assert result["confidence"] == "high"
    assert "Topildi" in result["text"]
    assert "1988" in result["text"]

def test_credit_confirms_matched_citizen(clean_citizens):
    _make_citizen("Kreditli", birth_year=1988, phone="+998900000009")

    with SessionLocal() as db:
        result = agents._credit_subsidy(
            db, "Testovsinov Testism uchun Xalq banki krediti shartlari", {}
        )

    text = result["text"]
    assert "Testovsinov" in text, f"fuqaro ismi tasdiqlanmadi: {text[:300]}"
    assert "1988" in text, f"tug'ilgan yili tasdiqlanmadi: {text[:300]}"
