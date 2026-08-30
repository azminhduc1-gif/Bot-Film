"""Tests for rate limiting middleware."""
from __future__ import annotations

import pytest

from app.bot.middleware.rate_limit_middleware import RateLimitMiddleware
from app.config import Config


@pytest.mark.asyncio
async def test_rate_limit_allows_under_limit() -> None:
    config = Config(
        telegram_bot_token="x",
        kkphim_api_key=None,
        kkphim_base_url="https://x",
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url=None,
        cache_ttl_seconds=60,
        request_timeout_seconds=5,
        max_retries=1,
        retry_backoff_seconds=0,
        rate_limit_per_minute=3,
        session_ttl_minutes=30,
        log_level="DEBUG",
        environment="test",
    )
    middleware = RateLimitMiddleware(config)

    for _ in range(3):
        assert middleware._is_allowed(1, 1)

    assert not middleware._is_allowed(1, 1)


@pytest.mark.asyncio
async def test_rate_limit_is_per_user_chat() -> None:
    config = Config(
        telegram_bot_token="x",
        kkphim_api_key=None,
        kkphim_base_url="https://x",
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url=None,
        cache_ttl_seconds=60,
        request_timeout_seconds=5,
        max_retries=1,
        retry_backoff_seconds=0,
        rate_limit_per_minute=1,
        session_ttl_minutes=30,
        log_level="DEBUG",
        environment="test",
    )
    middleware = RateLimitMiddleware(config)

    assert middleware._is_allowed(1, 1)
    assert not middleware._is_allowed(1, 1)
    assert middleware._is_allowed(2, 1)
