"""Media download engine utilizing yt-dlp, FFmpeg, and chunked streaming."""
from __future__ import annotations

import glob
import os
import subprocess
from typing import Any

import requests
import yt_dlp

from app.logging_config import get_logger
from app.services.downloader.ffmpeg_helper import get_ffmpeg_path

logger = get_logger(__name__)

MAX_FILE_SIZE = 49 * 1024 * 1024  # 49 MB Telegram limit


def split_media_sync(input_file: str, is_video: bool) -> list[str]:
    """Split media file if it exceeds Telegram 49MB limit.

    Video -> <= 180s per chunk
    Audio -> <= 600s per chunk
    """
    kind = "Video" if is_video else "Audio"
    logger.info("✂️ Splitting %s: '%s'", kind, os.path.basename(input_file))
    ffmpeg_path = get_ffmpeg_path()
    segment_time = 180 if is_video else 600
    extension = ".mp4" if is_video else ".mp3"
    output_pattern = f"{input_file}_part_%03d{extension}"

    cmd = [
        ffmpeg_path,
        "-y",
        "-i",
        input_file,
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        str(segment_time),
        "-reset_timestamps",
        "1",
        output_pattern,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        stderr_tail = result.stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"FFmpeg split failed (exit {result.returncode}): {stderr_tail}")

    parts = sorted(glob.glob(f"{input_file}_part_*{extension}"))
    logger.info("✅ Split completed — %d parts", len(parts))
    return parts


def download_file_sync(url: str, filepath: str, headers: dict[str, str] | None = None) -> int:
    """Download large files with 512KB chunks streaming without holding entire file in RAM."""
    logger.info("⬇️ Streaming download -> '%s'", os.path.basename(filepath))
    req = requests.get(url, stream=True, timeout=60, headers=headers)
    req.raise_for_status()
    with open(filepath, "wb") as f:
        for chunk in req.iter_content(chunk_size=512 * 1024):
            if chunk:
                f.write(chunk)
    return os.path.getsize(filepath)


def yt_dlp_download_sync(ydl_opts: dict[str, Any], url: str) -> None:
    """Run yt-dlp download in background thread."""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
