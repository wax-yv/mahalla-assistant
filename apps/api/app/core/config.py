from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """Application settings.

    Values come from environment variables first, then `.env.local` / `.env`.
    Secrets are never written to the repository; Vercel supplies them at runtime.
    """

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env.local", REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_base_url: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"
    api_base_url: str = "http://127.0.0.1:8000"
    app_version: str = "1.0.0"

    database_url: str = ""
    postgres_url: str = ""

    auth_secret: str = "change-me"
    admin_username: str = "wax"
    admin_password: str = "waxs"
    session_ttl_hours: int = 72
    setup_token: str = "change-me"
    cron_secret: str = "change-me"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    nvidia_nim_api_key: str = ""
    nvidia_nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    ai_default_provider: str = "nvidia"
    ai_request_timeout: int = 55
    # J-1: umumiy zanjir vaqti chegarasi (Vercel funksiyasi 60 s).
    # Bitta so'rov ichida barcha modellar ketma-ket ishga tushmasligi kerak.
    ai_chain_deadline_seconds: int = 45
    ai_attempt_timeout_seconds: int = 15
    ai_max_attempts: int = 4
    ai_daily_token_budget: int = 300_000
    ai_max_output_tokens: int = 1600
    ai_temperature: float = 0.15
    ai_model_config_json: str = ""

    blob_read_write_token: str = ""
    max_upload_mb: int = 4

    scheduler_timezone: str = "Asia/Tashkent"
    demo_mode: bool = True

    # O-1: ishonchli proksi zanjiri uzunligi. X-Forwarded-For sarlavhasining
    # **o'ng** tomonidan shu N-chi element haqiqiy mijoz manzili hisoblanadi.
    # 0 = proksi yo'q (XFF butunlay e'tiborsiz qoldiriladi).
    trusted_proxy_hops: int = 0

    sentry_dsn: str = ""

    @field_validator("ai_temperature")
    @classmethod
    def _temperature(cls, value: float) -> float:
        return max(0.0, min(1.0, value))

    @field_validator("trusted_proxy_hops")
    @classmethod
    def _trusted_proxy_hops(cls, value: int) -> int:
        if value < 0 or value > 10:
            raise ValueError("TRUSTED_PROXY_HOPS 0..10 oralig'ida bo'lishi kerak.")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def sqlalchemy_database_url(self) -> str:
        raw = (self.database_url or self.postgres_url or "").strip()
        if not raw:
            raise RuntimeError(
                "DATABASE_URL (or POSTGRES_URL) is not configured. "
                "Attach a Postgres database in Vercel or set DATABASE_URL in .env.local."
            )
        if raw.startswith("postgres://"):
            raw = "postgresql://" + raw[len("postgres://") :]
        if raw.startswith("postgresql://"):
            raw = "postgresql+psycopg://" + raw[len("postgresql://") :]
        if raw.startswith("postgresql+psycopg://"):
            return raw
        # Already a driver-qualified URL (e.g. postgresql+psycopg://)
        return raw

    @property
    def cors_origins(self) -> list[str]:
        origins = {
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            self.frontend_url.rstrip("/"),
            self.app_base_url.rstrip("/"),
        }
        return sorted({o for o in origins if o})

    @property
    def ai_models_override(self) -> dict[str, Any] | None:
        if not self.ai_model_config_json.strip():
            return None
        try:
            parsed = json.loads(self.ai_model_config_json)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    @property
    def max_upload_bytes(self) -> int:
        return max(1, self.max_upload_mb) * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# K-6: standart demo kredensial (dokumentlarda chop etilmaydi).
DEFAULT_ADMIN_USERNAME = "wax"
DEFAULT_ADMIN_PASSWORD = "waxs"


def admin_password_value() -> str:
    """Admin parolining amaldagi qiymati (bo'sh bo'lsa — standart demo qiymati)."""
    return (settings.admin_password or DEFAULT_ADMIN_PASSWORD).strip()


def assert_admin_password_allowed() -> None:
    """K-6: ishlab chiqarishda standart parol bilan admin yaratilmasligi kerak.

    `DEMO_MODE=true` bo'lgan demo deployment'ida ogohlantirish bilan davom
    etadi (demo kirish saqlanadi). Haqiqiy ishlab chiqarishda
    (`DEMO_MODE=false`) standart/bo'sh parol bilan admin yaratilmaydi.
    """
    password = admin_password_value()
    if not settings.is_production:
        return
    if settings.demo_mode:
        logger.warning(
            "DEMO_MODE=true: admin paroli standart demo qiymatida. "
            "Ishlab chiqarishda DEMO_MODE=false va kuchli ADMIN_PASSWORD qo'ying."
        )
        return
    if password in {"", DEFAULT_ADMIN_PASSWORD, "change-me"}:
        raise RuntimeError(
            "Production'da ADMIN_PASSWORD env ixtiyoriy emas — "
            "standart parol bilan admin yaratilmaydi."
        )
