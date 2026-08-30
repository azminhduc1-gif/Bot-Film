"""Middleware to attach request/session context to logs."""
from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.logging_config import clear_request_context, set_request_context


class LoggingMiddleware(BaseMiddleware):
    """Set request_id context for every incoming update."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        request_id = secrets.token_hex(6)
        user_id: int | None = None
        chat_id: int | None = None

        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            chat_id = event.message.chat.id if event.message else None

        set_request_context(request_id=request_id)
        data["request_id"] = request_id
        try:
            return await handler(event, data)
        finally:
            clear_request_context()
