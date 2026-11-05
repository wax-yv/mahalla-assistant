"""Tashqi manzillarni tekshirish (SSRF himoyasi).

Faqat Lex.uz dagi hujjat sahifalari serverdan yuklanishi mumkin. Boshqa
host, port, sxema yoki yo'l — rad etiladi.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.errors import validation_error

ALLOWED_HOSTS = {"lex.uz", "www.lex.uz"}
# /docs/<raqam> yoki /uz|ru|oz/docs/<raqam>
_DOC_PATH_RE = re.compile(r"^/(?:(?:uz|ru|oz)/)?docs/[A-Za-z0-9][A-Za-z0-9._-]*$")
REDIRECT_CODES = {301, 302, 303, 307, 308}


def validate_lex_host(url: str) -> str:
    """Faqat ruxsat etilgan host va https sxemasini tekshiradi."""
    raw = (url or "").strip()
    if not raw:
        raise validation_error("URL manzili bo'sh bo'lishi mumkin emas.")
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https":
        raise validation_error("Faqat https:// manzil qabul qilinadi.")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise validation_error("Faqat lex.uz manzillari qabul qilinadi.")
    if parsed.username or parsed.password:
        raise validation_error("URL manzilida foydalanuvchi ma'lumoti bo'lmasligi kerak.")
    if parsed.port not in (None, 443):
        raise validation_error("Faqat 443-portga ruxsat beriladi.")
    return raw


def validate_lex_url(url: str) -> str:
    """Hujjat manzili: ruxsat etilgan host + `/docs/<raqam>` yo'li."""
    raw = validate_lex_host(url)
    parsed = urlparse(raw)
    if not _DOC_PATH_RE.match(parsed.path):
        raise validation_error(
            "Faqat lex.uz/docs/<hujjat raqami> manzillari qabul qilinadi."
        )
    return raw
