from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

UNSAFE_CHARS = re.compile(r'["\\\r\n]')
ASCII_SAFE = re.compile(r"[^A-Za-z0-9._-]")

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

def safe_cell(value: Any) -> Any:
    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    if value[:1] in FORMULA_PREFIXES:
        return "'" + value
    return value

def safe_filename_part(value: str, *, fallback: str = "eksport", max_length: int = 60) -> str:
    raw = (value or "").strip()
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_")
    return cleaned[:max_length].strip("_") or fallback

def content_disposition(filename: str, *, fallback: str = "file") -> str:
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
