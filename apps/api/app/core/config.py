from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    ai_daily_token_budget: int = 300_000
    ai_max_output_tokens: int = 1600
    ai_temperature: float = 0.15
    ai_model_config_json: str = ""

    blob_read_write_token: str = ""
    max_upload_mb: int = 4

    scheduler_timezone: str = "Asia/Tashkent"
    demo_mode: bool = True

    sentry_dsn: str = ""

    @field_validator("ai_temperature")
    @classmethod
    def _temperature(cls, value: float) -> float:
        return max(0.0, min(1.0, value))

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
