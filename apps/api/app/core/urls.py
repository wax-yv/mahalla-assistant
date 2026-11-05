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


def validate_public_https_url(url: str) -> str:
    """Umumiy tashqi manzil (rasmiy bank saytlari va h.k.) — SSRF himoyasi bilan.

    - faqat `https` sxeması;
    - foydalanuvchi ma'lumotlari (`user:pass@`) va maxsus portlar rad etiladi;
    - host ichki/prive tarmoqqa (127.0.0.1, 10.x, 192.168.x, 169.254.x ...)
    yo'nalmasligi kerak.
    """
    raw = (url or "").strip()
    if not raw:
        raise validation_error("URL manzili bo'sh bo'lishi mumkin emas.")
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https":
        raise validation_error("Faqat https:// manzil qabul qilinadi.")
    if parsed.username or parsed.password:
        raise validation_error("URL manzilida foydalanuvchi ma'lumoti bo'lmasligi kerak.")
    if parsed.port not in (None, 443):
        raise validation_error("Faqat 443-portga ruxsat beriladi.")
    host = (parsed.hostname or "").lower()
    if not host:
        raise validation_error("URL manzilida host yo'q.")
    if _is_private_host(host):
        raise validation_error("Ichki tarmoqqa manzil qabul qilinmaydi.")
    return raw


def _is_private_host(host: str) -> bool:
    """Host ichki yoki maxsus IP oralig'iga tegishlimi?"""
    import ipaddress
    import socket

    addresses: list[str] = []
    try:
        for info in socket.getaddrinfo(host, None):
            address = info[4][0]
            if isinstance(address, str):
                addresses.append(address)
    except OSError:
        # Nomni yechib bo'lmasa — manzilni tekshirib bo'lmaydi, rad etamiz.
        return True
    if not addresses:
        return True
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return True
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False
