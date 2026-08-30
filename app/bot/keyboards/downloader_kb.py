"""Inline keyboard builders for social media downloader."""
from __future__ import annotations

import time
import uuid
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# In-memory storage for pending download tasks
_DOWNLOAD_TASKS: dict[str, dict[str, Any]] = {}
_TASK_EXPIRY: dict[str, float] = {}
TASK_TTL = 3600.0  # 1 hour


def store_download_task(data: dict[str, Any]) -> str:
    """Store task metadata and return short task ID."""
    now = time.monotonic()
    # Cleanup expired tasks
    expired = [k for k, exp in _TASK_EXPIRY.items() if now > exp]
    for k in expired:
        _DOWNLOAD_TASKS.pop(k, None)
        _TASK_EXPIRY.pop(k, None)

    task_id = uuid.uuid4().hex[:10]
    _DOWNLOAD_TASKS[task_id] = data
    _TASK_EXPIRY[task_id] = now + TASK_TTL
    return task_id


def get_download_task(task_id: str) -> dict[str, Any] | None:
    """Retrieve stored task metadata."""
    now = time.monotonic()
    exp = _TASK_EXPIRY.get(task_id)
    if exp and now > exp:
        _DOWNLOAD_TASKS.pop(task_id, None)
        _TASK_EXPIRY.pop(task_id, None)
        return None
    return _DOWNLOAD_TASKS.get(task_id)


def youtube_video_kb(task_id: str) -> InlineKeyboardMarkup:
    """Keyboard for single YouTube video."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📺 Tải Video (1080p)", callback_data=f"dl:yt:v:{task_id}"),
                InlineKeyboardButton(text="🎵 Tải MP3 (320kbps)", callback_data=f"dl:yt:a:{task_id}"),
            ],
            [
                InlineKeyboardButton(text="📁 Tải MP4 File (Gốc · Không nén)", callback_data=f"dl:yt:doc:{task_id}"),
            ],
        ]
    )


def youtube_playlist_kb(task_id: str, count: int) -> InlineKeyboardMarkup:
    """Keyboard for YouTube Playlist or Mix."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"📺 Tải {count} Video (1080p)", callback_data=f"dl:yt:plv:{task_id}"),
                InlineKeyboardButton(text=f"🎵 Tải {count} MP3 (320kbps)", callback_data=f"dl:yt:pla:{task_id}"),
            ],
            [
                InlineKeyboardButton(text=f"📁 Tải {count} MP4 File (Gốc)", callback_data=f"dl:yt:pldoc:{task_id}"),
            ],
        ]
    )


def tiktok_video_kb(task_id: str, has_music: bool) -> InlineKeyboardMarkup:
    """Keyboard for TikTok video."""
    row1 = [InlineKeyboardButton(text="🎬 Tải Video (No Watermark)", callback_data=f"dl:tk:v:{task_id}")]
    if has_music:
        row1.append(InlineKeyboardButton(text="🎵 Tải Nhạc", callback_data=f"dl:tk:a:{task_id}"))

    row2 = [InlineKeyboardButton(text="📁 Tải MP4 1080p (File gốc)", callback_data=f"dl:tk:doc:{task_id}")]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])


def tiktok_photo_kb(task_id: str, photo_count: int, has_music: bool) -> InlineKeyboardMarkup:
    """Keyboard for TikTok photo album."""
    row1 = [InlineKeyboardButton(text=f"📸 Tải Album ({photo_count} ảnh)", callback_data=f"dl:tk:img:{task_id}")]
    if has_music:
        row1.append(InlineKeyboardButton(text="🎵 Tải Nhạc", callback_data=f"dl:tk:a:{task_id}"))
    return InlineKeyboardMarkup(inline_keyboard=[row1])


def facebook_kb(task_id: str) -> InlineKeyboardMarkup:
    """Keyboard for Facebook video / reels."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📹 Tải Video (1080p)", callback_data=f"dl:fb:v:{task_id}"),
                InlineKeyboardButton(text="🎵 Tải MP3 (320kbps)", callback_data=f"dl:fb:a:{task_id}"),
            ],
            [
                InlineKeyboardButton(text="📁 Tải MP4 File (Gốc · Không nén)", callback_data=f"dl:fb:doc:{task_id}"),
            ],
        ]
    )


def soundcloud_kb(task_id: str) -> InlineKeyboardMarkup:
    """Keyboard for SoundCloud audio."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎵 Tải MP3 (320kbps)", callback_data=f"dl:sc:a:{task_id}"),
            ]
        ]
    )
