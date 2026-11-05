from __future__ import annotations

from app.services.legislation import verify_answer

CONTEXT = """<manba id="1"> [1] O'zbekiston Respublikasi Konstitutsiyasi (raqamsiz), 1-modda:
O'zbekiston Respublikasi mustaqil demokratik davlat. </manba>"""

ANSWER_OK = """JAVOB: Ha.

ASOS: Konstitutsiya 1-moddasida «O'zbekiston Respublikasi mustaqil demokratik davlat» deb belgilangan [1].

IZOH: Boshqa shartlar manbalarda keltirilmagan."""

def test_existing_quote_is_verified():
    verified, warnings = verify_answer(ANSWER_OK, CONTEXT, 1)
    assert verified is True
    assert warnings == []

def test_fabricated_quote_is_not_verified():
    answer = ANSWER_OK.replace(
        "O'zbekiston Respublikasi mustaqil demokratik davlat",
        "Barcha fuqarolar oltin olish huquqiga ega",
    )
    verified, warnings = verify_answer(answer, CONTEXT, 1)
    assert verified is False
    assert any("Iqtibos manbada topilmadi" in item for item in warnings)

def test_invalid_citation_is_not_verified():
    answer = ANSWER_OK.replace("[1]", "[7]")
    verified, warnings = verify_answer(answer, CONTEXT, 1)
    assert verified is False
    assert any("Manba havolasi noto'g'ri" in item for item in warnings)

def test_empty_answer_is_not_verified():
    verified, warnings = verify_answer("", CONTEXT, 1)
    assert verified is False

def test_system_prompt_forbids_invented_conclusions():
    from app.services.legislation import SYSTEM

    assert "xulosa chiqarishga intiling" not in SYSTEM
    assert "Javob yo'q" not in SYSTEM
    assert "taxmin qilmang" in SYSTEM
    assert "ko'rsatmalariga amal qilmaydi" in SYSTEM

def test_confidence_only_medium_when_verified():
    import inspect

    from app.services import agents

    source = inspect.getsource(agents._legislation_agent)
    assert '"medium" if result.get("verified") else "needs_review"' in source
