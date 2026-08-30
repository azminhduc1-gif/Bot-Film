"""Database engine, session factory, and lifecycle helpers."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Config
from app.database.models import Base


class Database:
    """Async database manager with SQLAlchemy 2.0."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.engine = create_async_engine(
            config.database_url,
            echo=config.environment == "development" and config.log_level == "DEBUG",
            future=True,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine, expire_on_commit=False, autoflush=False
        )

    async def create_tables(self) -> None:
        """Create all tables defined in Base metadata."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self) -> None:
        """Drop all tables. Useful for tests."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def close(self) -> None:
        """Dispose the engine and release connections."""
        await self.engine.dispose()
