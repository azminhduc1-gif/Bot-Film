"""Metadata extractor for TikTok, YouTube, Facebook, and SoundCloud."""
from __future__ import annotations

import asyncio
import os
import re
import urllib.parse
from typing import Any

import requests
import yt_dlp

from app.logging_config import get_logger

logger = get_logger(__name__)

TIKWM_API_URL = "https://tikwm.com/api/"
MAX_PLAYLIST_VIDEOS = 50

_FB_DOMAINS = (
    "facebook.com",
    "fb.com",
    "fb.watch",
    "m.facebook.com",
    "www.facebook.com",
)

_YT_PATTERN = re.compile(
    r"(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)(/.*)?",
    re.IGNORECASE,
)

_MIX_PREFIXES = (
    "RD",
    "RDMIX",
    "RDCL",
    "RDQ",
    "OLAK",
    "LL",
    "WL",
    "FL",
)


def apply_impersonate_opts(ydl_opts: dict[str, Any]) -> dict[str, Any]:
    """Attach Chrome TLS/HTTP2 impersonation to bypass Cloudflare/SoundCloud blocks."""
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget
        ydl_opts["impersonate"] = ImpersonateTarget.from_str("chrome")
    except Exception:
        pass
    return ydl_opts


def format_size(num_bytes: int) -> str:
    """Format bytes into human-readable B / KB / MB / GB."""
    n = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


def format_duration(seconds: float | None) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if not seconds:
        return "Không rõ"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def format_views(n: int | None) -> str:
    """Format view counts with dot separators (1.000.000)."""
    if n is None:
        return "Không rõ"
    return f"{n:,}".replace(",", ".")


def format_date(yyyymmdd: str | int | None) -> str:
    """Format YYYYMMDD into DD/MM/YYYY."""
    if not yyyymmdd or len(str(yyyymmdd)) != 8:
        return "Không rõ"
    s = str(yyyymmdd)
    try:
        return f"{s[6:8]}/{s[4:6]}/{s[:4]}"
    except Exception:
        return str(yyyymmdd)


def is_facebook(url: str) -> bool:
    """Check if URL belongs to Facebook."""
    url_lower = url.lower()
    return any(d in url_lower for d in _FB_DOMAINS)


def is_youtube(url: str) -> bool:
    """Check if URL belongs to YouTube."""
    return bool(_YT_PATTERN.search(url))


def is_tiktok(url: str) -> bool:
    """Check if URL belongs to TikTok or Douyin."""
    url_lower = url.lower()
    return "tiktok.com" in url_lower or "douyin.com" in url_lower


def is_soundcloud(url: str) -> bool:
    """Check if URL belongs to SoundCloud."""
    url_lower = url.lower()
    return "soundcloud.com" in url_lower


def is_social_url(url: str) -> bool:
    """Check if URL matches any supported social media platforms."""
    return is_youtube(url) or is_tiktok(url) or is_facebook(url) or is_soundcloud(url)


def get_playlist_id(url: str) -> str:
    """Extract YouTube list= query param."""
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        return qs.get("list", [""])[0]
    except Exception:
        return ""


def is_mix_playlist(list_id: str) -> bool:
    """Check if playlist is YouTube Mix/Radio."""
    if not list_id:
        return False
    return any(list_id.startswith(p) for p in _MIX_PREFIXES)


def is_regular_playlist(url: str) -> bool:
    """Check if URL is a public YouTube playlist."""
    if not is_youtube(url):
        return False
    list_id = get_playlist_id(url)
    if not list_id or is_mix_playlist(list_id):
        return False
    return list_id.startswith(("PL", "UU", "TL", "OL"))


async def get_tiktok_info(url: str) -> dict[str, Any] | None:
    """Extract TikTok metadata using TikWM (Tier 1) and Douyin.wtf (Tier 2)."""
    proxy = get_download_proxy()

    def _tikwm_request():
        try:
            from curl_cffi import requests as c_requests
            kwargs: dict[str, Any] = {
                "params": {"url": url, "hd": 1},
                "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://www.tikwm.com/"},
                "impersonate": "chrome120",
                "timeout": 25,
            }
            if proxy:
                kwargs["proxy"] = proxy
                kwargs["verify"] = False
            return c_requests.get(TIKWM_API_URL, **kwargs)
        except Exception:
            proxies = {"http": proxy, "https": proxy} if proxy else None
            return requests.get(TIKWM_API_URL, params={"url": url, "hd": 1}, timeout=25, proxies=proxies)

    # Tier 1: TikWM
    for attempt in range(1, 3):
        try:
            logger.info("🔍 [TikWM] Query attempt %d/2 for %s", attempt, url[:60])
            response = await asyncio.to_thread(_tikwm_request)
            if response.status_code == 200:
                data_json = response.json()
                if data_json and data_json.get("code") == 0:
                    data = data_json.get("data", {})
                    return {
                        "id": data.get("id"),
                        "title": data.get("title", "Không có tiêu đề"),
                        "cover": data.get("cover"),
                        "play": data.get("play"),
                        "music": data.get("music"),
                        "images": data.get("images", []),
                        "source": "tikwm",
                    }
            elif response.status_code in (502, 503, 504):
                await asyncio.sleep(1.5)
            else:
                break
        except Exception as exc:
            logger.warning("TikWM attempt %d failed: %s", attempt, exc)
            await asyncio.sleep(1.5)

    # Tier 2: api.douyin.wtf
    logger.info("🔄 Falling back to Tier 2 TikTok API (douyin.wtf)...")
    def _douyin_request():
        try:
            from curl_cffi import requests as c_requests
            kwargs = {
                "params": {"url": url, "minimal": "false"},
                "impersonate": "chrome120",
                "timeout": 20,
            }
            if proxy:
                kwargs["proxy"] = proxy
                kwargs["verify"] = False
            return c_requests.get("https://api.douyin.wtf/api/hybrid/video_data", **kwargs)
        except Exception:
            proxies = {"http": proxy, "https": proxy} if proxy else None
            return requests.get("https://api.douyin.wtf/api/hybrid/video_data", params={"url": url, "minimal": "false"}, timeout=20, proxies=proxies)

    try:
        res = await asyncio.to_thread(_douyin_request)
        if res.status_code == 200:
            data_json = res.json()
            if data_json.get("code") == 200 or "data" in data_json or "video" in data_json:
                data = data_json.get("data", data_json)
                images_list = data.get("image_data", {}).get("no_watermark_image_list", []) or data.get("images", [])

                play_url = None
                video_node = data.get("video_data") or data.get("video")
                if isinstance(video_node, list) and video_node:
                    play_url = video_node[0]
                elif isinstance(video_node, dict):
                    play_url = (
                        video_node.get("nwm_video_url_HQ")
                        or video_node.get("nwm_video_url")
                        or (video_node.get("play_addr") or {}).get("url_list", [None])[0]
                    )
                if not play_url:
                    play_url = data.get("video_url") or data.get("play")
                if isinstance(play_url, list) and play_url:
                    play_url = play_url[0]

                music_url = None
                music_node = data.get("music") or data.get("music_info") or {}
                if isinstance(music_node, dict):
                    pun = music_node.get("play_url") or {}
                    if isinstance(pun, dict):
                        music_url = pun.get("url_list", [None])[0] or pun.get("uri")
                    elif isinstance(pun, str):
                        music_url = pun
                    if not music_url:
                        music_url = music_node.get("play")
                if not music_url:
                    music_url = data.get("music_url")
                if isinstance(music_url, list) and music_url:
                    music_url = music_url[0]

                cover_url = data.get("cover")
                cover_list = (data.get("cover_data") or {}).get("dynamic_cover", {}).get("url_list", [])
                if cover_list:
                    cover_url = cover_list[0]
                elif images_list:
                    cover_url = images_list[0]

                if play_url or images_list:
                    return {
                        "id": "fallback_id",
                        "title": data.get("desc", data.get("title", "Không có tiêu đề")),
                        "cover": cover_url,
                        "play": play_url,
                        "music": music_url,
                        "images": images_list,
                        "source": "douyin.wtf",
                    }
    except Exception as exc:
        logger.warning("Tier 2 TikTok API failed: %s", exc)

    return None


def get_youtube_info_sync(url: str, cookie_path: str = "") -> dict[str, Any] | None:
    """Extract single YouTube video metadata via yt-dlp."""
    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
    }
    if cookie_path and os.path.isfile(cookie_path):
        ydl_opts["cookiefile"] = cookie_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            thumbnail = info.get("thumbnail")
            thumbnails = info.get("thumbnails", [])
            if thumbnails:
                best = max(
                    thumbnails,
                    key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
                    default=None,
                )
                if best:
                    thumbnail = best.get("url", thumbnail)

            return {
                "title": info.get("title", "Không có tiêu đề"),
                "uploader": info.get("uploader") or info.get("channel", "Không rõ"),
                "duration": info.get("duration"),
                "thumbnail": thumbnail,
                "view_count": info.get("view_count"),
                "upload_date": info.get("upload_date"),
                "webpage_url": info.get("webpage_url", url),
                "is_live": bool(info.get("is_live")),
            }
    except Exception as exc:
        logger.warning("YouTube extraction failed for %s: %s", url, exc)
        return None


def get_youtube_playlist_info_sync(url: str, cookie_path: str = "") -> dict[str, Any] | None:
    """Extract YouTube playlist / Mix entries."""
    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "playlistend": MAX_PLAYLIST_VIDEOS,
    }
    if cookie_path and os.path.isfile(cookie_path):
        ydl_opts["cookiefile"] = cookie_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            entries_raw = info.get("entries") or []
            if not entries_raw:
                return None

            entries = []
            for e in entries_raw:
                if not e or not e.get("id"):
                    continue
                entries.append(
                    {
                        "id": e["id"],
                        "title": e.get("title") or "Video không có tên",
                        "url": e.get("url") or e.get("webpage_url") or f"https://www.youtube.com/watch?v={e['id']}",
                        "duration": e.get("duration"),
                    }
                )

            thumbnail = info.get("thumbnail")
            thumbnails = info.get("thumbnails") or []
            if thumbnails:
                best = max(
                    thumbnails,
                    key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
                    default=None,
                )
                if best:
                    thumbnail = best.get("url", thumbnail)

            return {
                "title": info.get("title") or "Playlist không có tên",
                "uploader": info.get("uploader") or info.get("channel") or "Không rõ",
                "webpage_url": info.get("webpage_url", url),
                "thumbnail": thumbnail,
                "total_count": info.get("playlist_count") or len(entries_raw),
                "entries": entries,
            }
    except Exception as exc:
        logger.warning("YouTube playlist extraction failed for %s: %s", url, exc)
        return None


def get_facebook_info_sync(url: str, cookie_path: str = "") -> dict[str, Any] | None:
    """Extract Facebook video / Reels metadata via yt-dlp."""
    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
    }
    fb_cookie = cookie_path or os.environ.get("FB_COOKIES_FILE", "")
    if fb_cookie and os.path.isfile(fb_cookie):
        ydl_opts["cookiefile"] = fb_cookie

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            thumbnail = info.get("thumbnail")
            thumbnails = info.get("thumbnails", [])
            if thumbnails:
                best = max(
                    thumbnails,
                    key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
                    default=None,
                )
                if best:
                    thumbnail = best.get("url", thumbnail)

            formats = info.get("formats", [])
            has_video = any(f.get("vcodec") not in (None, "none", "") for f in formats)

            return {
                "title": info.get("title") or (info.get("description") or "")[:80] or "Nội dung Facebook",
                "uploader": info.get("uploader") or info.get("channel", "Không rõ"),
                "duration": info.get("duration"),
                "thumbnail": thumbnail,
                "view_count": info.get("view_count"),
                "upload_date": info.get("upload_date"),
                "webpage_url": info.get("webpage_url", url),
                "has_video": has_video,
                "is_live": bool(info.get("is_live")),
            }
    except yt_dlp.utils.DownloadError as exc:
        err_str = str(exc).lower()
        if any(kw in err_str for kw in ("private", "login", "not available", "403", "404")):
            return {"_error": "private"}
        return None
    except Exception as exc:
        logger.warning("Facebook extraction failed for %s: %s", url, exc)
        return None


def get_download_proxy() -> str | None:
    """Read proxy configuration from environment variables."""
    return os.environ.get("DOWNLOAD_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or None


def get_soundcloud_info_sync(url: str) -> dict[str, Any] | None:
    """Extract SoundCloud track metadata with direct stream URL resolution."""
    proxy = get_download_proxy()
    req_kwargs: dict[str, Any] = {"impersonate": "chrome120", "timeout": 25}
    if proxy:
        req_kwargs["proxy"] = proxy
        req_kwargs["verify"] = False

    # Method 1: Direct extraction via curl_cffi & hydration data (Bypasses Cloudflare & SSL errors 100%)
    try:
        from curl_cffi import requests as c_requests
        resp = c_requests.get(url, **req_kwargs)
        if resp.status_code == 200 and "window.__sc_hydration" in resp.text:
            import json
            match = re.search(r"window\.__sc_hydration\s*=\s*(\[.*?\]);\s*</script>", resp.text)
            if match:
                data = json.loads(match.group(1))
                sound = next((d["data"] for d in data if d.get("hydratable") == "sound"), None)
                if sound:
                    title = sound.get("title", "Bài hát SoundCloud")
                    user = sound.get("user", {})
                    uploader = user.get("username") or user.get("full_name") or "Nghệ sĩ không rõ"
                    duration_ms = sound.get("duration") or 0
                    duration = duration_ms / 1000.0 if duration_ms else None
                    thumbnail = sound.get("artwork_url") or user.get("avatar_url")
                    if thumbnail and "-large" in thumbnail:
                        thumbnail = thumbnail.replace("-large", "-t500x500")

                    client_id = next((d["data"].get("id") for d in data if d.get("hydratable") == "apiClient"), None)
                    stream_url = None
                    trans = sound.get("media", {}).get("transcodings", [])
                    if trans and client_id:
                        # Prefer progressive mp3 transcoding
                        prog = next((t for t in trans if t.get("format", {}).get("protocol") == "progressive"), trans[0])
                        try:
                            s_kwargs = {"params": {"client_id": client_id}, "impersonate": "chrome120", "timeout": 15}
                            if proxy:
                                s_kwargs["proxy"] = proxy
                                s_kwargs["verify"] = False
                            s_res = c_requests.get(prog["url"], **s_kwargs)
                            if s_res.status_code == 200:
                                stream_url = s_res.json().get("url")
                        except Exception as e:
                            logger.warning("Could not resolve stream URL: %s", e)

                    return {
                        "title": title,
                        "uploader": uploader,
                        "thumbnail": thumbnail,
                        "duration": duration,
                        "url": url,
                        "stream_url": stream_url,
                    }
    except Exception as exc:
        logger.warning("Direct curl_cffi SoundCloud extraction failed: %s", exc)

    # Method 2: Fallback to yt-dlp
    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
        "source_address": "0.0.0.0",
        "socket_timeout": 30,
        "retries": 5,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        },
    }
    apply_impersonate_opts(ydl_opts)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            return {
                "title": info.get("title", "Bài hát SoundCloud"),
                "uploader": info.get("uploader", "Nghệ sĩ không rõ"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "url": url,
            }
    except Exception as exc:
        logger.warning("SoundCloud extraction failed for %s: %s", url, exc)
        return None
