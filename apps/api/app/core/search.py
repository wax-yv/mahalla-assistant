"""SQL qidiruv yordamchilari.

D-5: foydalanuvchi kiritgan matn `ILIKE` ga to'g'ridan-to'g'ri
berilsa, `%` va `_` belgilari qidiruvni kengaytirib, boshqa yozuvlarni
ko'rsatardi (masalan `%` — "hammasi"). Bunday belgilar escape qilinadi.
"""

from __future__ import annotations


def escape_like(value: str | None) -> str:
    """`ILIKE` pattern'idagi maxsus belgilarni escape qiladi.

    `%` — istalgan belgi, `_` — bitta belgi, `\\` — escape belgisi.
    """
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def like_pattern(value: str | None) -> str:
    """`%qiymat%` pattern — `ilike(..., escape="\\\\")` bilan ishlatish uchun."""
    return f"%{escape_like(value)}%"
