"""Unit and integration tests for social media downloader."""
from __future__ import annotations

from pathlib import Path

from app.bot.keyboards.downloader_kb import (
    facebook_kb,
    get_download_task,
    soundcloud_kb,
    store_download_task,
    tiktok_photo_kb,
    tiktok_video_kb,
    youtube_playlist_kb,
    youtube_video_kb,
)
from app.services.downloader import (
    CookieService,
    format_date,
    format_duration,
    format_size,
    format_views,
    get_ffmpeg_path,
    get_playlist_id,
    is_facebook,
    is_mix_playlist,
    is_regular_playlist,
    is_social_url,
    is_soundcloud,
    is_tiktok,
    is_youtube,
)


def test_url_detection() -> None:
    """Test URL pattern detection across platforms."""
    # YouTube
    assert is_youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert is_youtube("https://youtu.be/dQw4w9WgXcQ")
    assert is_youtube("https://music.youtube.com/watch?v=abc")
    assert is_social_url("https://youtu.be/dQw4w9WgXcQ")

    # YouTube Playlist vs Mix
    pl_url = "https://www.youtube.com/playlist?list=PL1234567890"
    mix_url = "https://www.youtube.com/watch?v=abc&list=RDabc"
    assert get_playlist_id(pl_url) == "PL1234567890"
    assert is_regular_playlist(pl_url)
    assert not is_mix_playlist(get_playlist_id(pl_url))
    assert is_mix_playlist(get_playlist_id(mix_url))
    assert not is_regular_playlist(mix_url)

    # TikTok
    assert is_tiktok("https://www.tiktok.com/@user/video/123456789")
    assert is_tiktok("https://vt.tiktok.com/ZS123456/")
    assert is_social_url("https://vt.tiktok.com/ZS123456/")

    # Facebook
    assert is_facebook("https://www.facebook.com/watch/?v=123456")
    assert is_facebook("https://fb.watch/xyz123/")
    assert is_social_url("https://fb.watch/xyz123/")

    # SoundCloud
    assert is_soundcloud("https://soundcloud.com/artist/track-name")
    assert is_social_url("https://soundcloud.com/artist/track-name")

    # Non-social
    assert not is_social_url("https://google.com")
    assert not is_social_url("https://phimapi.com/phim/test")
    assert not is_social_url("Avengers Endgame")


def test_formatters() -> None:
    """Test string formatters for size, duration, views, dates."""
    assert format_size(500) == "500.0 B"
    assert format_size(1024 * 1024) == "1.0 MB"
    assert format_size(50 * 1024 * 1024) == "50.0 MB"

    assert format_duration(65) == "01:05"
    assert format_duration(3665) == "01:01:05"
    assert format_duration(None) == "Không rõ"

    assert format_views(1234567) == "1.234.567"
    assert format_views(None) == "Không rõ"

    assert format_date("20240315") == "15/03/2024"
    assert format_date("") == "Không rõ"


def test_cookie_service(tmp_path: Path) -> None:
    """Test Netscape cookie validation and user cookie manager."""
    # Valid Netscape content
    valid_file = tmp_path / "valid.txt"
    valid_file.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t1700000000\tSID\t123\n")
    is_valid, _ = CookieService.validate_cookies_txt(valid_file)
    assert is_valid

    # Invalid content
    invalid_file = tmp_path / "invalid.txt"
    invalid_file.write_text("this is just plain text without tabs")
    is_valid_bad, _ = CookieService.validate_cookies_txt(invalid_file)
    assert not is_valid_bad

    # Save and Delete
    test_user_id = 999888777
    saved = CookieService.save_cookie_file(test_user_id, valid_file)
    assert saved
    assert CookieService.has_cookie(test_user_id)
    info = CookieService.get_cookie_info(test_user_id)
    assert "✅" in info

    deleted = CookieService.delete_cookie(test_user_id)
    assert deleted
    assert not CookieService.has_cookie(test_user_id)


def test_task_storage_and_keyboards() -> None:
    """Test download task storage and inline keyboards compliance with Telegram 64-byte limit."""
    task_data = {"platform": "youtube", "url": "https://youtu.be/test", "title": "Test Video"}
    task_id = store_download_task(task_data)
    assert task_id
    assert len(task_id) == 10
    retrieved = get_download_task(task_id)
    assert retrieved == task_data

    # Test all keyboard callback_data <= 64 bytes
    kbs = [
        youtube_video_kb(task_id),
        youtube_playlist_kb(task_id, 10),
        tiktok_video_kb(task_id, has_music=True),
        tiktok_photo_kb(task_id, photo_count=5, has_music=True),
        facebook_kb(task_id),
        soundcloud_kb(task_id),
    ]

    for kb in kbs:
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data:
                    assert len(btn.callback_data.encode("utf-8")) <= 64, (
                        f"Callback data {btn.callback_data} exceeds 64 bytes!"
                    )


def test_ffmpeg_path_finder() -> None:
    """Verify FFmpeg helper returns an executable path."""
    path = get_ffmpeg_path()
    assert path
    assert isinstance(path, str)

