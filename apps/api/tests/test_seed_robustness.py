"""N-8: seed barqarorligi — portable dataset va mos ma'lumot.

Muammo (audit N-8):
- `DATA_FILE` lokal absolyut yo'l (`/home/shohjahon/Downloads/...`) —
  boshqa muhitda noto'g'ri fayl yuklanishi mumkin edi;
- task fuqarosi case fuqarosidan farq qilardi (`cases[index % len]`);
- sikl ichida har iteratsiyada takroriy `SELECT(Task)`;
- zaif `waxs` parol qismi — eganing demo qarori, O'ZGARTIRILMAYDI.
"""

from __future__ import annotations

import inspect

from app import seed


def test_seed_has_no_external_absolute_path():
    """Dataset faqat loyiha ichidan o'qiladi."""
    source = inspect.getsource(seed)
    assert "/home/shohjahon" not in source, "absolyut lokal yo'l qolgan"
    assert "DATA_FILE" not in source


def test_seed_uses_bundled_file():
    """`PREFERRED_FILE` — loyiha ichidagi yo'l."""
    assert seed.PREFERRED_FILE.name == "demo_fuqarolar_bazasi.xlsx"
    assert "apps/api/data" in str(seed.PREFERRED_FILE)


def test_task_citizen_matches_case_citizen():
    """Seed kodi task fuqarosini case fuqarosidan oladi."""
    source = inspect.getsource(seed.seed_operational)
    assert "case_by_index" in source
    assert "citizen_id_for_task" in source


def test_task_select_not_repeated_in_loop():
    """Sikl ichida takroriy SELECT yo'q (bir marta o'qiladi)."""
    source = inspect.getsource(seed.seed_operational)
    assert "first_tasks" in source
    assert source.count("select(Task)") == 2, "seed_operational ikki SELECT dan ko'p ishlatmasligi kerak"
