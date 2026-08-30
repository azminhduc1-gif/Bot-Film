"""Shared pytest fixtures."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import aiohttp
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Config
from app.database.models import Base
from app.providers.kkphim.client import KKPhimClient
from app.services.cache_service import CacheService, MemoryCache
from app.services.movie_service import MovieService
from app.services.session_service import SessionService


@pytest.fixture(scope="session")
def event_loop():
    """Provide a session-scoped event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_config() -> Config:
    return Config(
        telegram_bot_token="test-token",
        kkphim_api_key=None,
        kkphim_base_url="https://test.kkphim.io",
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url=None,
        cache_ttl_seconds=60,
        request_timeout_seconds=5,
        max_retries=3,
        retry_backoff_seconds=0,
        rate_limit_per_minute=100,
        session_ttl_minutes=30,
        log_level="DEBUG",
        environment="test",
    )


@pytest_asyncio.fixture(scope="session")
async def db_engine(test_config: Config):
    engine = create_async_engine(test_config.database_url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def cache_service() -> CacheService:
    return CacheService(backend=MemoryCache(), default_ttl=60)


@pytest_asyncio.fixture
async def kkphim_client(test_config: Config, aiohttp_client_session: aiohttp.ClientSession):
    return KKPhimClient(test_config, session=aiohttp_client_session)


@pytest_asyncio.fixture
async def aiohttp_client_session() -> AsyncGenerator[aiohttp.ClientSession, None]:
    async with aiohttp.ClientSession() as session:
        yield session


@pytest_asyncio.fixture
async def movie_service(
    kkphim_client: KKPhimClient,
    cache_service: CacheService,
    test_config: Config,
) -> MovieService:
    return MovieService(client=kkphim_client, cache=cache_service, config=test_config)


@pytest_asyncio.fixture
async def session_service(db_session: AsyncSession, test_config: Config) -> SessionService:
    return SessionService(db_session=db_session, config=test_config)
