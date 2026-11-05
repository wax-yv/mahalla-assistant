"""Deterministik data-query engine testlari.

Muqova: «2 guruh nogironlarining aniq ro'yxatini va sonini chiqarib ber»,
«ism familiyalarini ayt», «salom, menga qanday yordam bera olasan?».

Asosiy talab: raqamlar va ismlar FAQAT jonli SQL so'rovi bilan keladi —
kodga yozib qo'yilgan ro'yxat yoki LLM'dan olingan javob emas.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import Citizen, Street
from app.services import data_query
from app.services.agents import detect_intent


# --------------------------------------------------------------------------
# Intent routing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "2 guruh nogironlarining aniq ro'yxatini va sonini chiqarib ber",
        "ism familiyalarini ayt",
        "ishsizlar nechta?",
        "Temir daftardagi fuqarolar soni",
        "guruh nogironliki bor shaxslar nechta?",
    ],
)
def test_count_and_list_questions_force_data_stats(message: str):
    intent, intents = detect_intent(message)
    assert intent == "data_stats", f"{message!r} -> {intent} {intents}"
    assert intents[0] == "data_stats"


@pytest.mark.parametrize(
    "message",
    [
        "salom",
        "Salom!",
        "salom, menga qanday yordam bera olasan?",
        "menga nima qila olasan?",
    ],
)
def test_greetings_route_to_deterministic_greeting(message: str):
    intent, intents = detect_intent(message)
    assert intent == "greeting", f"{message!r} -> {intent} {intents}"


@pytest.mark.parametrize(
    "message",
    [
        "Bugun qaysi vazifalar?",
        "murojaatlar holati qanday",
        "O'zbekiston Konstitutsiyasining 1-moddasi",
        "kredit shartlari qanday",
    ],
)
def test_other_domains_are_not_hijacked_by_data_stats(message: str):
    intent, _ = detect_intent(message)
    assert intent != "data_stats", f"{message!r} -> {intent}"


# --------------------------------------------------------------------------
# Bazadan olingan aniq raqamlar
# --------------------------------------------------------------------------


def test_group_two_returns_exact_count_and_names():
    with SessionLocal() as db:
        answer = data_query.build_answer(
            db, "2 guruh nogironlarining aniq ro'yxatini va sonini chiqarib ber"
        )

    assert answer.facets.social == ["Nogironligi bor (II guruh)"]
    assert answer.total > 0
    assert len(answer.rows) == answer.total
    # Ism-familiyalar ro'yxatda bor
    assert all(row.title for row in answer.rows)
    # Ro'yxatdagi har bir shaxs haqiqiy bazadan kelgan
    with SessionLocal() as db:
        names = {
            row[0]
            for row in db.execute(select(Citizen.full_name)).all()
        }
    assert all(row.title in names for row in answer.rows)
    # Javobda son aniq ko'rsatilgan
    assert str(answer.total) in answer.text
    # Foydalanuvchiga «o'zing filtrla» deyilmaydi
    lowered = answer.text.lower()
    assert "o'zingiz" not in lowered
    assert "filterni qo'ling" not in lowered


def test_list_mode_contains_numbered_names_and_count():
    with SessionLocal() as db:
        answer = data_query.build_answer(
            db, "2 guruh nogironlarining aniq ro'yxatini va sonini chiqarib ber"
        )
    assert answer.facets.list_mode is True
    assert "1." in answer.text
    assert "Nogironligi bor (II guruh)" in answer.text
    assert "Manba:" in answer.text


def test_count_mode_returns_breakdown():
    with SessionLocal() as db:
        answer = data_query.build_answer(
            db, "guruh nogironliki bor shaxslar nechta?"
        )
    assert answer.facets.count_mode is True
    assert answer.total > 0
    assert "Jami" in answer.text
    assert answer.breakdown


def test_answer_is_live_database_driven_not_hardcoded():
    """Qiymat bazadagi haqiqiy yozuvlarga mos kelishi kerak."""
    with SessionLocal() as db:
        social_values = {
            row[0]
            for row in db.execute(select(Citizen.social_status).distinct()).all()
            if row[0]
        }
        assert "Temir daftar" in social_values

        expected = db.execute(
            select(func.count())
            .select_from(Citizen)
            .where(
                Citizen.archived_at.is_(None),
                Citizen.social_status == "Temir daftar",
            )
        ).scalar_one()

        answer = data_query.build_answer(db, "temir daftardagi fuqarolar soni")
    assert answer.facets.social == ["Temir daftar"]
    assert answer.total == expected
    assert str(expected) in answer.text


def test_facet_values_are_discovered_from_database():
    """Filtr qiymatlari kodga yozilgan emas — bazadan DISTINCT bilan olinadi."""
    with SessionLocal() as db:
        vocab = data_query._discover(db)
        streets = {
            row[0] for row in db.execute(select(Street.name).distinct()).all()
        }
    assert "Temir daftar" in vocab["social"]
    assert set(vocab["streets"]) == streets
    assert streets  # bazada ko'chalar mavjud


# --------------------------------------------------------------------------
# API orqali (chat)
# --------------------------------------------------------------------------


def test_chat_returns_group_two_list(auth):
    client, token = auth
    response = client.post(
        "/api/v1/agents/chat",
        headers={"X-CSRF-Token": token},
        json={
            "message": "2 guruh nogironlarining aniq ro'yxatini va sonini chiqarib ber"
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "data_stats"
    content = body["message"]["content"]
    assert "Nogironligi bor (II guruh)" in content
    assert "ISM" not in content and "EMIS" not in content
    # Ro'yxat bo'sh emas
    assert "1." in content
    assert "o'zingiz" not in content.lower()


def test_chat_followup_keeps_previous_filter(auth):
    """«...ro'yxatini chiqarib ber» -> «ism familiyalarini ayt» konteksti saqlanadi."""
    client, token = auth
    first = client.post(
        "/api/v1/agents/chat",
        headers={"X-CSRF-Token": token},
        json={"message": "2 guruh nogironlarining aniq ro'yxatini va sonini chiqarib ber"},
    )
    assert first.status_code == 200, first.text
    conversation_id = first.json()["conversation_id"]
    total = first.json()["sources"][0]["facets"]  # filters used

    second = client.post(
        "/api/v1/agents/chat",
        headers={"X-CSRF-Token": token},
        json={
            "message": "ism familiyalarini ayt",
            "conversation_id": conversation_id,
        },
    )
    assert second.status_code == 200, second.text
    content = second.json()["message"]["content"]
    assert "Nogironligi bor (II guruh)" in content
    assert total["social"] == ["Nogironligi bor (II guruh)"]
    assert "1." in content


def test_chat_greeting_returns_capability_answer(auth):
    client, token = auth
    response = client.post(
        "/api/v1/agents/chat",
        headers={"X-CSRF-Token": token},
        json={"message": "salom, menga qanday yordam bera olasan?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "greeting"
    content = body["message"]["content"]
    assert "yordam bera olaman" in content.lower()
    assert "fuqaro" in content.lower()
    # Foydalanuvchiga "savolni qayta yozing" deyilmaydi
    assert "qayta yoz" not in content.lower()
    assert "o'ylab top" not in content.lower()


def test_chat_reset_word_drops_inherited_filter(auth):
    client, token = auth
    first = client.post(
        "/api/v1/agents/chat",
        headers={"X-CSRF-Token": token},
        json={"message": "2 guruh nogironlarining aniq ro'yxatini va sonini chiqarib ber"},
    )
    conversation_id = first.json()["conversation_id"]
    second = client.post(
        "/api/v1/agents/chat",
        headers={"X-CSRF-Token": token},
        json={
            "message": "barcha fuqarolarning ism familiyalarini ayt",
            "conversation_id": conversation_id,
        },
    )
    content = second.json()["message"]["content"]
    assert "Nogironligi bor (II guruh)" not in content


# --------------------------------------------------------------------------
# Modul tozaligi
# --------------------------------------------------------------------------


def test_no_hardcoded_social_facet_table():
    """`data_query` modulida qo'lda yozilgan ijtimoiy holat ro'yxati bo'lmasligi kerak."""
    source = (data_query.__file__ or "")
    with open(source, "r", encoding="utf-8") as handle:
        code = handle.read()
    # "Temir daftar" kabi qiymatlar faqat izohda emas, ro'yxat sifatida yozilmasin
    assert 'SOCIAL_FACETS' not in code
    for literal in ('"Temir daftar"', '"Yoshlar daftari"', '"Kam ta\'minlangan oila"'):
        assert literal not in code, f"{literal} kodga yozib qo'yilgan"
