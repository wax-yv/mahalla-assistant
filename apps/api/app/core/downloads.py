"""Yuklab olish sarlavhalari (Content-Disposition) va eksport xavfsizligi.

J-7: O'zbekcha fayl nomlarida `ʻ`, `‘`, kirill harflari keng tarqalgan. ASCII'ga
majburlash `UnicodeEncodeError` -> 500 beradi. Bundan tashqari nom ichidagi
`"` va CR/LF sarlavhani buzib, header injeksiyasiga olib keladi.

Yechim: RFC 6266/5987 — ASCII `filename` (zaxira) + `filename*` (UTF-8).

O-15: CSV/Excel formula inyeksiyasi (CSV injection) himoyasi.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

UNSAFE_CHARS = re.compile(r'["\\\r\n]')
ASCII_SAFE = re.compile(r"[^A-Za-z0-9._-]")

# O-15: Excel/CSV formulani ifodalovchi bosh belgilar.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: Any) -> Any:
    """Excel/CSV formula inyeksiyasidan himoyalangan qiymat (O-15).

    `=`, `+`, `-`, `@`, TAB va CR bilan boshlanuvchi satrlar apostrof bilan
    niqolanadi: Excel ularni formula emas, matn sifatida o'qiladi
    (`openpyxl` `=` bilan boshlanuvchi satrni avtomatik formula sifatida
    yozadi — `<f>...</f>`).

    Raqam, sana va boshqa turdagi qiymatlar **o'zgarishsiz** qoladi —
    ular matnga aylantirilsa Excel'da son ustuni buziladi.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    if value[:1] in FORMULA_PREFIXES:
        return "'" + value
    return value


def content_disposition(filename: str, *, fallback: str = "file") -> str:
    """Xavfsiz `Content-Disposition` sarlavha qiymati.

    - `filename` — ASCII zaxira nom (brauzerlar uni to'g'ri ko'rsatadi).
    - `filename*` — RFC 5987 UTF-8 nom (haqiqiy o'zbekcha nom saqlanadi).
    """
    raw = (filename or "").strip()
    cleaned = UNSAFE_CHARS.sub("", raw).strip()
    if not cleaned:
        cleaned = fallback
    ascii_name = ASCII_SAFE.sub("_", cleaned.encode("ascii", "ignore").decode())
    ascii_name = ascii_name.strip("._") or fallback
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(cleaned, safe='')}"
    )
