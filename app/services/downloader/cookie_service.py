"""YouTube user cookies manager for personalized playlists and Mix/Radio."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

COOKIES_DIR = Path("user_cookies")
COOKIES_DIR.mkdir(parents=True, exist_ok=True)


class CookieService:
    """Manage per-user Netscape cookie files."""

    @staticmethod
    def get_cookie_path(user_id: int) -> str:
        """Return the path to a user's cookie file if it exists, otherwise empty string."""
        path = COOKIES_DIR / f"{user_id}.txt"
        return str(path) if path.is_file() else ""

    @staticmethod
    def has_cookie(user_id: int) -> bool:
        """Check if user has an active cookie file."""
        return (COOKIES_DIR / f"{user_id}.txt").is_file()

    @staticmethod
    def delete_cookie(user_id: int) -> bool:
        """Delete user's cookie file. Returns True if deleted."""
        path = COOKIES_DIR / f"{user_id}.txt"
        if path.is_file():
            try:
                path.unlink()
                return True
            except OSError:
                return False
        return False

    @staticmethod
    def validate_cookies_txt(filepath: str | Path) -> tuple[bool, str]:
        """Validate if a file matches Netscape HTTP Cookie File format."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(8192)

            if "# Netscape HTTP Cookie File" in content or "# HTTP Cookie File" in content:
                return True, "ok"

            real_lines = [
                line
                for line in content.splitlines()
                if line.strip() and not line.startswith("#")
            ]
            if real_lines:
                parts = real_lines[0].split("\t")
                if len(parts) >= 6:
                    return True, "ok"

            return False, "Không phải định dạng Netscape cookies.txt"
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def save_cookie_file(user_id: int, source_path: str | Path) -> bool:
        """Save a validated cookie file for the specified user."""
        target_path = COOKIES_DIR / f"{user_id}.txt"
        try:
            if os.path.exists(source_path):
                os.replace(source_path, target_path)
                return True
        except Exception:
            return False
        return False

    @staticmethod
    def get_cookie_info(user_id: int) -> str:
        """Return a human-readable summary of the user's cookie."""
        path = COOKIES_DIR / f"{user_id}.txt"
        if not path.is_file():
            return "Chưa có cookie"
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = [line for line in f if line.strip() and not line.startswith("#")]
            return f"✅ {len(lines)} mục · Cập nhật: {mtime}"
        except Exception:
            return "✅ Có cookie"
