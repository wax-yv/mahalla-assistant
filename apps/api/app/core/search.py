from __future__ import annotations


def escape_like(value: str | None) -> str:
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )

def like_pattern(value: str | None) -> str:
    return f"%{escape_like(value)}%"
