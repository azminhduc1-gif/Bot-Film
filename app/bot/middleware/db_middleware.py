"""Database middleware providing an async SQLAlchemy session per update."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.database.database import Database


class DatabaseMiddleware(BaseMiddleware):
    """Aiogram middleware that injects an active AsyncSession into data['db_session']."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.database.session() as session:
            data["db_session"] = session
            return await handler(event, data)
