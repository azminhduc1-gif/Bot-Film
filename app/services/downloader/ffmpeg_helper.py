"""FFmpeg locator for cross-platform support (Linux Ubuntu / Docker / Windows)."""
from __future__ import annotations

import shutil


def get_ffmpeg_path() -> str:
    """Find FFmpeg binary path.

    Prioritizes system ffmpeg (standard on Linux / Docker),
    falling back to imageio_ffmpeg if not installed globally.
    """
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg

    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        return get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"
