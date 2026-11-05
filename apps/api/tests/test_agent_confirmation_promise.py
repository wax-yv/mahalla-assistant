"""O-8: agent "tasdiq talab qiladi" va'dasi bilan amaldagi ziddiyat.

Muammo:
- README "har bir yozuv amali draft va tasdiqlangandan keyin" deydi, lekin
  tanlangan bank tanlovi (`programs.save_preference`) tasdiqsiz yozilardi.
- Intent aniqlanmagan har savol `smalltalk` orqali LLM'ga ketardi;
  `SMALLTALK_SYSTEM` da mahalla/qonun/kredit faktlarini uydirishni
  taqiqlovchi qoida yo'q edi — faqat "raqamlarni bilmaysiz" bor edi.

To'g'rilash:
- `SMALLTALK_SYSTEM` ga "faqat tizim ma'lumotidan, bilmasangiz «bilmayman»"
  qoidasi qo'shiladi;
- bank tanlovi yozuvi foydalanuvchiga **ochiq aytiladi** (javob matnida va
  `data.preference_saved` da) — yashirilmaydi;
- README va'dasi aniqlashtiriladi: biznes yozuvlari draft orqali, suhbat
  bo'yicha eslab qolinadigan tanlov esa ochiq aytilgan holda saqlanadi.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app.services import agents

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_smalltalk_system_forbids_fabricating_facts():
    """Smalltalk promptida fakt uydirishni taqiqlovchi qoda bo'lishi kerak."""
    system = agents.SMALLTALK_SYSTEM
    lowered = system.lower()
    assert "bilmayman" in lowered, "'bilmayman' qoidasi yo'q"
    # Qoida quyidagilarni qamrab olishi kerak.
    assert "mahalla" in lowered
    assert "kredit" in lowered or "subsidiya" in lowered
    assert "qonun" in lowered or "qonunchilik" in lowered


def test_smalltalk_rule_mentions_only_system_data():
    """Faqat tizim ma'lumotidan foydalanish qoidasi bo'lishi kerak."""
    lowered = agents.SMALLTALK_SYSTEM.lower()
    assert "tizim ma'lumot" in lowered or "faqat tizim" in lowered


def test_credit_agent_discloses_saved_preference():
    """Bank tanlovi yozilishi foydalanuvchiga ochiq aytilishi kerak."""
    source = inspect.getsource(agents._credit_subsidy)
    assert "preference_saved" in source, "javobda saqlangan tanlov ko'rsatilmadi"


def test_credit_agent_says_preference_was_saved():
    """Javob matnida tanlovingiz saqlangani aytilishi kerak."""
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        result = agents._credit_subsidy(
            db, "Xalq banki krediti shartlari qanday?", {}
        )

    text = result["text"]
    assert "eslab" in text.lower(), f"tanlov saqlangani aytilmadi: {text[-300:]}"
    assert "preference_saved" in result["data"], (
        "`data.preference_saved` maydoni yo'q"
    )


def test_readme_states_draft_policy_accurately():
    """README va'dasi aniq bo'lishi kerak (yashirilgan yozuv yo'q)."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    lowered = readme.lower()
    assert "draft" in lowered
    # Eslab qolinadigan tanlov (bank tanlovi) haqida ham aniq aytilishi kerak.
    assert "tanlov" in lowered or "preference" in lowered, (
        "README'da tanlov (preference) yozuvi qoidasi ko'rsatilmagan"
    )
