"""Rate-limiting middleware per user and per chat."""
from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import Config
from app.logging_config import get_logger

logger = get_logger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """Simple in-memory sliding-window rate limiter."""

    def __init__(self, config: Config) -> None:
        self.limit = config.rate_limit_per_minute
        self.window = 60.0
        # user_id/chat_id -> list of timestamps
        self._history: dict[tuple[int, int], list[float]] = defaultdict(list)

    def _is_allowed(self, user_id: int, chat_id: int) -> bool:
        now = time.monotonic()
        key = (user_id, chat_id)
        history = self._history[key]
        # Drop old entries outside the window.
        cutoff = now - self.window
        self._history[key] = [ts for ts in history if ts > cutoff]

        if len(self._history[key]) >= self.limit:
            logger.warning("Rate limit exceeded user=%s chat=%s", user_id, chat_id)
            return False

        self._history[key].append(now)
        return True

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id: int | None = None
        chat_id: int | None = None

        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            chat_id = event.message.chat.id if event.message else None

        if user_id is None or chat_id is None:
            return await handler(event, data)

        if not self._is_allowed(user_id, chat_id):
            if isinstance(event, Message):
                await event.answer("⏱ Bạn gửi yêu cầu quá nhanh. Vui lòng chờ một chút.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⏱ Bạn bấm quá nhanh. Vui lòng chờ một chút.", show_alert=True)
            return None

        return await handler(event, data)
