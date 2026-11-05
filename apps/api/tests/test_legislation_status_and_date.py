"""D-6 va D-7: qonunchilik hujjati holati va kuchga kirish sanasi.

D-6: eski kod butun HTML'da `status_code_y` satrini izlardi — CSS/JS ham
o'sha satrni o'z ichiga olsa hujjat noto'g'ri "amaldagi" deb belgilanardi.
Endi holat aniq DOM elementidan (`.lx_act_state i`) o'qiladi.

D-7: eski kod kuchga kirish sanasini topganda ham `None` qo'yardi —
sana hech qachon saqlanmasdi.
"""

from __future__ import annotations

from datetime import date

from bs4 import BeautifulSoup

from app.services.legislation import _legal_status_from_html, _parse_effective_date


def test_active_status_from_dom_element():
    """`.lx_act_state i` elementida `status_code_y` bo'lsa — amaldagi."""
    html = """
    <html><body>
      <div class="lx_act_state"><i class="status_code_y"></i> <span>Amaldagi</span></div>
    </body></html>
    """
    assert _legal_status_from_html(BeautifulSoup(html, "lxml")) == "amaldagi"


def test_status_in_script_is_not_active():
    """`status_code_y` faqat skript/CSS ichida bo'lsa — 'amaldagi' emas."""
    html = """
    <html><head>
      <style>.i.status_code_y { color: green; }</style>
      <script>var cls = "status_code_y";</script>
    </head><body><h1>Hujjat</h1></body></html>
    """
    assert _legal_status_from_html(BeautifulSoup(html, "lxml")) == "tekshirilgan"


def test_status_without_element_is_checked():
    """Holat elementi yo'q bo'lsa — 'tekshirilgan'."""
    html = "<html><body><p>Matn</p></body></html>"
    assert _legal_status_from_html(BeautifulSoup(html, "lxml")) == "tekshirilgan"


def test_effective_date_with_phrase():
    """`2024-yil 1-yanvardan e'tiboran kuchga kiradi` — sana o'qiladi."""
    text = "Ushbu qonun rasmiy e'lon qilingan.\n2024-yil 1-yanvardan e'tiboran kuchga kiradi."
    assert _parse_effective_date(text) == date(2024, 1, 1)


def test_effective_date_with_typographic_apostrophe():
    """Tipografik apostrof (`eʼtiboran`) ham o'qiladi."""
    text = "2023-yil 15-martdan eʼtiboran kuchga kiradi."
    assert _parse_effective_date(text) == date(2023, 3, 15)


def test_effective_date_without_phrase():
    """Ibora yo'q, lekin sana bor holatda ham o'qiladi."""
    text = "Qaror 2022-yil 9-avgustdan kuchga kirgan hisoblanadi."
    assert _parse_effective_date(text) == date(2022, 8, 9)


def test_effective_date_invalid_month_is_none():
    """Noma'lum oy nomi bo'lsa — `None`."""
    assert _parse_effective_date("2024-yil 1-qwerdan e'tiboran kuchga kuchga kiradi") is None


def test_effective_date_empty_is_none():
    assert _parse_effective_date("") is None
    assert _parse_effective_date("sana yo'q") is None


def test_effective_date_invalid_day_is_none():
    """Mavjud bo'lmagan kun (31-fevral) — `None`."""
    assert _parse_effective_date("2024-yil 31-fevraldan e'tiboran kuchga kiradi.") is None
