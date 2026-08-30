"""Aiogram filters for chat types."""
from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import Message


class PrivateChatFilter(BaseFilter):
    """Matches messages sent in private chats."""

    async def __call__(self, message: Message) -> bool:
        return message.chat.type == "private"


class GroupChatFilter(BaseFilter):
    """Matches messages sent in groups or supergroups."""

    async def __call__(self, message: Message) -> bool:
        return message.chat.type in {"group", "supergroup"}
