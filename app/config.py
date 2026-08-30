"""Application configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from app/config.py)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass(frozen=True, slots=True)
class Config:
    """Immutable application configuration."""

    telegram_bot_token: str
    kkphim_api_key: str | None
    kkphim_base_url: str
    database_url: str
    redis_url: str | None
    cache_ttl_seconds: int
    request_timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    rate_limit_per_minute: int
    session_ttl_minutes: int
    log_level: str
    environment: str
    telegram_proxy: str | None = None
    telegram_api_server: str | None = None

    @classmethod
    def from_env(cls) -> Config:
        """Build configuration from environment variables with sensible defaults."""
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        return cls(
            telegram_bot_token=token,
            kkphim_api_key=os.environ.get("KKPHIM_API_KEY") or None,
            kkphim_base_url=os.environ.get("KKPHIM_BASE_URL", "https://phimapi.com").rstrip("/"),
            database_url=os.environ.get(
                "DATABASE_URL", f"sqlite+aiosqlite:///{_PROJECT_ROOT / 'data.db'}"
            ),
            redis_url=os.environ.get("REDIS_URL") or None,
            cache_ttl_seconds=int(os.environ.get("CACHE_TTL_SECONDS", "300")),
            request_timeout_seconds=float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "10")),
            max_retries=int(os.environ.get("MAX_RETRIES", "3")),
            retry_backoff_seconds=float(os.environ.get("RETRY_BACKOFF_SECONDS", "1")),
            rate_limit_per_minute=int(os.environ.get("RATE_LIMIT_PER_MINUTE", "20")),
            session_ttl_minutes=int(os.environ.get("SESSION_TTL_MINUTES", "30")),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            environment=os.environ.get("ENVIRONMENT", "development"),
            telegram_proxy=os.environ.get("TELEGRAM_PROXY") or None,
            telegram_api_server=os.environ.get("TELEGRAM_API_SERVER") or None,
        )
