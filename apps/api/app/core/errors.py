from __future__ import annotations

from typing import Any


class APIError(Exception):
    """An expected, user-safe API error."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []

    def to_dict(self, request_id: str | None = None) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "request_id": request_id,
            }
        }


def bad_request(message: str, details: list[Any] | None = None) -> APIError:
    return APIError(400, "BAD_REQUEST", message, details)


def validation_error(message: str, details: list[Any] | None = None) -> APIError:
    return APIError(422, "VALIDATION_ERROR", message, details)


def unauthenticated(message: str = "Tizimga kirish talab qilinadi.") -> APIError:
    return APIError(401, "UNAUTHENTICATED", message)


def forbidden(message: str = "Bu amal uchun ruxsat yo'q.") -> APIError:
    return APIError(403, "FORBIDDEN", message)


def not_found(message: str = "Yozuv topilmadi.") -> APIError:
    return APIError(404, "NOT_FOUND", message)


def conflict(message: str, details: list[Any] | None = None) -> APIError:
    return APIError(409, "CONFLICT", message, details)


def too_many_requests(message: str = "So'rovlar soni chegaradan oshdi.") -> APIError:
    return APIError(429, "RATE_LIMITED", message)


def payload_too_large(message: str = "Fayl hajmi chegaradan oshdi.") -> APIError:
    """O'ta katta fayl (O-10: yuklashda 413)."""
    return APIError(413, "PAYLOAD_TOO_LARGE", message)


def service_unavailable(message: str = "Xizmat vaqtincha ishlamayapti.") -> APIError:
    return APIError(503, "SERVICE_UNAVAILABLE", message)
