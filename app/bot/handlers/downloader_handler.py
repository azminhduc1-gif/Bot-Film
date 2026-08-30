"""Handler for social media download requests, cookies, and document uploads."""
from __future__ import annotations

import asyncio
from pathlib import Path
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards.downloader_kb import (
    facebook_kb,
    soundcloud_kb,
    store_download_task,
    tiktok_photo_kb,
    tiktok_video_kb,
    youtube_playlist_kb,
    youtube_video_kb,
)
from app.logging_config import get_logger
from app.services.downloader import (
    CookieService,
    format_date,
    format_duration,
    format_views,
    get_facebook_info_sync,
    get_playlist_id,
    get_soundcloud_info_sync,
    get_tiktok_info,
    get_youtube_info_sync,
    get_youtube_playlist_info_sync,
    is_facebook,
    is_mix_playlist,
    is_regular_playlist,
    is_social_url,
    is_soundcloud,
    is_tiktok,
    is_youtube,
)

logger = get_logger(__name__)
downloader_router = Router(name="downloader_router")


@downloader_router.message(Command("mycookie"))
async def cmd_mycookie(message: Message) -> None:
    """View user's YouTube cookie status."""
    if not message.from_user:
        return
    user_id = message.from_user.id
    info = CookieService.get_cookie_info(user_id)
    if CookieService.has_cookie(user_id):
        await message.reply(
            f"🍪 <b>Trạng thái Cookie YouTube của bạn</b>\n\n"
            f"{info}\n\n"
            f"✅ YouTube Mix & playlist cá nhân hóa đã được kích hoạt.\n\n"
            f"🗑️ Để xóa: /delcookie\n"
            f"🔄 Để cập nhật: gửi file <code>cookies.txt</code> mới",
            parse_mode="HTML",
        )
    else:
        await message.reply(
            "🍪 <b>Trạng thái Cookie YouTube của bạn</b>\n\n"
            "❌ Chưa có cookie — YouTube Mix sẽ chỉ tải được video đơn.\n\n"
            "<b>Cách thêm cookie:</b>\n"
            "1️⃣ Cài extension <b>Get cookies.txt LOCALLY</b> (Chrome/Firefox)\n"
            "2️⃣ Vào <code>youtube.com</code> khi đang đăng nhập\n"
            "3️⃣ Click extension → Export → lưu file <code>cookies.txt</code>\n"
            "4️⃣ Gửi file đó trực tiếp vào đây là xong ✅",
            parse_mode="HTML",
        )


@downloader_router.message(Command("delcookie"))
async def cmd_delcookie(message: Message) -> None:
    """Delete user's YouTube cookie."""
    if not message.from_user:
        return
    user_id = message.from_user.id
    if CookieService.delete_cookie(user_id):
        await message.reply(
            "🗑️ <b>Cookie đã được xóa thành công.</b>\n\n"
            "YouTube Mix sẽ chỉ tải được video đơn cho đến khi bạn gửi cookie mới.",
            parse_mode="HTML",
        )
    else:
        await message.reply("ℹ️ Bạn chưa có cookie nào được lưu.", parse_mode="HTML")


@downloader_router.message(F.document)
async def handle_cookie_document(message: Message, bot: Bot) -> None:
    """Handle document upload for cookies.txt."""
    if not message.document or not message.from_user:
        return

    doc = message.document
    filename = (doc.file_name or "").lower()
    is_cookie_file = filename.endswith(".txt") and (
        "cookie" in filename or doc.mime_type in ("text/plain", "application/octet-stream")
    )
    if not is_cookie_file:
        return

    user_id = message.from_user.id
    status_msg = await message.reply("⏳ <b>Đang xử lý file cookie...</b>", parse_mode="HTML")

    if doc.file_size and doc.file_size > 2 * 1024 * 1024:
        await status_msg.edit_text("❌ File cookie tối đa 2 MB.", parse_mode="HTML")
        return

    temp_dir = Path("tmp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / f"cookie_{user_id}_{doc.file_id[:10]}.tmp"

    try:
        file_info = await bot.get_file(doc.file_id)
        if not file_info.file_path:
            raise ValueError("Không thể lấy đường dẫn file từ Telegram.")
        await bot.download_file(file_info.file_path, destination=temp_file)

        valid, reason = CookieService.validate_cookies_txt(temp_file)
        if not valid:
            await status_msg.edit_text(
                f"❌ <b>File không hợp lệ</b>\n\n"
                f"Lý do: <code>{reason}</code>\n\n"
                f"Hãy đảm bảo xuất đúng định dạng <b>Netscape cookies.txt</b> "
                f"bằng extension <i>Get cookies.txt LOCALLY</i>.",
                parse_mode="HTML",
            )
            return

        CookieService.save_cookie_file(user_id, temp_file)
        info = CookieService.get_cookie_info(user_id)
        await status_msg.edit_text(
            f"✅ <b>Cookie YouTube đã được lưu thành công!</b>\n\n"
            f"📊 {info}\n\n"
            f"Từ bây giờ bạn có thể gửi link YouTube Mix / Radio — "
            f"bot sẽ tự động dùng cookie để lấy đúng danh sách cá nhân hóa.\n\n"
            f"🍪 Xem trạng thái: /mycookie\n"
            f"🗑️ Xóa cookie: /delcookie",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.exception("Error processing cookie document from user %d: %s", user_id, exc)
        await status_msg.edit_text(f"❌ <b>Không tải được file:</b> <code>{exc}</code>", parse_mode="HTML")
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass


async def handle_social_url_download(message: Message, bot: Bot) -> bool:
    """Detect and process social media URLs. Returns True if handled."""
    text = (message.text or "").strip()
    if not text or not is_social_url(text):
        return False

    user_id = message.from_user.id if message.from_user else 0
    url = text

    # ── YOUTUBE ──────────────────────────────────────────
    if is_youtube(url):
        status_msg = await message.reply("⏳ <b>Đang phân tích liên kết YouTube...</b>", parse_mode="HTML")
        list_id = get_playlist_id(url)
        is_mix = is_mix_playlist(list_id)
        is_pl = is_regular_playlist(url)
        yt_cookie = CookieService.get_cookie_path(user_id)

        # YouTube Mix / Radio
        if list_id and is_mix:
            if yt_cookie:
                pl_info_mix = await asyncio.to_thread(get_youtube_playlist_info_sync, url, yt_cookie)
                if pl_info_mix and pl_info_mix.get("entries"):
                    entries = pl_info_mix["entries"]
                    task_id = store_download_task(
                        {
                            "platform": "youtube_playlist",
                            "url": pl_info_mix["webpage_url"],
                            "title": pl_info_mix["title"],
                            "uploader": pl_info_mix.get("uploader", "Không rõ"),
                            "entries": entries,
                            "total_count": pl_info_mix["total_count"],
                            "yt_cookie": yt_cookie,
                        }
                    )
                    caption = (
                        f"🎲 <b>{pl_info_mix['title'][:70]}</b>\n\n"
                        f"👤 Kênh: <code>{pl_info_mix.get('uploader', 'Không rõ')}</code>\n"
                        f"🎞️ Số video: <code>{len(entries)}</code> / {pl_info_mix['total_count']}\n"
                        f"🍪 Nguồn: <i>Playlist cá nhân hóa (Cookie)</i>\n\n"
                        f"👇 <b>Chọn định dạng tải xuống:</b>"
                    )
                    kb = youtube_playlist_kb(task_id, len(entries))
                    await status_msg.delete()
                    if pl_info_mix.get("thumbnail"):
                        await message.reply_photo(photo=pl_info_mix["thumbnail"], caption=caption, reply_markup=kb, parse_mode="HTML")
                    else:
                        await message.reply(caption, reply_markup=kb, parse_mode="HTML")
                    return True
            # Fallback to single video if no cookie or failed
            is_pl = False

        # Regular YouTube Playlist
        if is_pl:
            pl_info = await asyncio.to_thread(get_youtube_playlist_info_sync, url, yt_cookie)
            if pl_info and pl_info.get("entries"):
                entries = pl_info["entries"]
                task_id = store_download_task(
                    {
                        "platform": "youtube_playlist",
                        "url": pl_info["webpage_url"],
                        "title": pl_info["title"],
                        "uploader": pl_info.get("uploader", "Không rõ"),
                        "entries": entries,
                        "total_count": pl_info["total_count"],
                        "yt_cookie": yt_cookie,
                    }
                )
                caption = (
                    f"📋 <b>{pl_info['title'][:70]}</b>\n\n"
                    f"👤 Kênh: <code>{pl_info.get('uploader', 'Không rõ')}</code>\n"
                    f"🎞️ Số video: <code>{len(entries)}</code> / {pl_info['total_count']}\n\n"
                    f"👇 <b>Chọn định dạng tải xuống:</b>"
                )
                kb = youtube_playlist_kb(task_id, len(entries))
                await status_msg.delete()
                if pl_info.get("thumbnail"):
                    await message.reply_photo(photo=pl_info["thumbnail"], caption=caption, reply_markup=kb, parse_mode="HTML")
                else:
                    await message.reply(caption, reply_markup=kb, parse_mode="HTML")
                return True

        # Single YouTube Video
        info = await asyncio.to_thread(get_youtube_info_sync, url, yt_cookie)
        if not info:
            await status_msg.edit_text(
                "❌ <b>Không thể lấy thông tin video YouTube</b>\n\n"
                "• Video có thể bị riêng tư, giới hạn độ tuổi, hoặc bị xóa.\n"
                "• Vui lòng kiểm tra lại đường dẫn.",
                parse_mode="HTML",
            )
            return True

        if info.get("is_live"):
            await status_msg.edit_text("🔴 <b>Không hỗ trợ tải livestream đang diễn ra.</b>", parse_mode="HTML")
            return True

        task_id = store_download_task(
            {
                "platform": "youtube",
                "url": info["webpage_url"],
                "title": info["title"],
                "uploader": info.get("uploader", "Không rõ"),
                "duration": info.get("duration"),
                "yt_cookie": yt_cookie,
            }
        )
        caption = (
            f"📺 <b>{info['title'][:75]}</b>\n\n"
            f"👤 Kênh: <code>{info.get('uploader', 'Không rõ')}</code>\n"
            f"⏱️ Thời lượng: <code>{format_duration(info.get('duration'))}</code>\n"
            f"👁️ Lượt xem: <code>{format_views(info.get('view_count'))}</code>\n"
            f"📅 Ngày đăng: <code>{format_date(info.get('upload_date'))}</code>\n\n"
            f"👇 <b>Chọn định dạng tải xuống:</b>"
        )
        kb = youtube_video_kb(task_id)
        await status_msg.delete()
        if info.get("thumbnail"):
            await message.reply_photo(photo=info["thumbnail"], caption=caption, reply_markup=kb, parse_mode="HTML")
        else:
            await message.reply(caption, reply_markup=kb, parse_mode="HTML")
        return True

    # ── TIKTOK ───────────────────────────────────────────
    if is_tiktok(url):
        status_msg = await message.reply("⏳ <b>Đang phân tích liên kết TikTok...</b>", parse_mode="HTML")
        data = await get_tiktok_info(url)
        if not data:
            await status_msg.edit_text(
                "❌ <b>Không thể lấy thông tin TikTok</b>\n\n"
                "• Video có thể ở chế độ riêng tư hoặc link không hợp lệ.\n"
                "• Thử sao chép lại link gốc từ ứng dụng TikTok.",
                parse_mode="HTML",
            )
            return True

        is_photo_mode = bool(data.get("images"))
        task_id = store_download_task(
            {
                "platform": "tiktok",
                "id": data["id"],
                "play": data["play"],
                "music": data["music"],
                "title": data["title"],
                "images": data["images"],
                "original_url": url,
            }
        )

        kind_str = "Album ảnh" if is_photo_mode else "Video HD"
        images_list = data.get("images") or []
        detail_str = f"{len(images_list)} ảnh" if is_photo_mode else "Không watermark"
        emoji_prefix = "📸" if is_photo_mode else "🎬"
        caption = (
            f"{emoji_prefix} <b>{data['title'][:75]}</b>\n\n"
            f"📋 Loại nội dung: <code>{kind_str}</code>\n"
            f"ℹ️ Chi tiết: <code>{detail_str}</code>\n\n"
            f"👇 <b>Chọn định dạng tải xuống:</b>"
        )

        kb = tiktok_photo_kb(task_id, len(images_list), bool(data.get("music"))) if is_photo_mode else tiktok_video_kb(task_id, bool(data.get("music")))
        cover = data["images"][0] if is_photo_mode and data["images"] else data.get("cover")
        await status_msg.delete()
        if cover:
            await message.reply_photo(photo=cover, caption=caption, reply_markup=kb, parse_mode="HTML")
        else:
            await message.reply(caption, reply_markup=kb, parse_mode="HTML")
        return True

    # ── FACEBOOK ─────────────────────────────────────────
    if is_facebook(url):
        status_msg = await message.reply("⏳ <b>Đang phân tích liên kết Facebook...</b>", parse_mode="HTML")
        info = await asyncio.to_thread(get_facebook_info_sync, url)
        if isinstance(info, dict) and info.get("_error") == "private":
            await status_msg.edit_text(
                "🔒 <b>Nội dung không thể truy cập</b>\n\n"
                "Video này ở chế độ riêng tư hoặc yêu cầu đăng nhập Facebook.\n"
                "Bot chỉ hỗ trợ tải video công khai (Public).",
                parse_mode="HTML",
            )
            return True

        if not info:
            await status_msg.edit_text(
                "❌ <b>Không thể lấy thông tin nội dung Facebook</b>\n\n"
                "• Video đã bị xóa hoặc ở chế độ riêng tư.\n"
                "• Chỉ hỗ trợ video / reels công khai.",
                parse_mode="HTML",
            )
            return True

        if info.get("is_live"):
            await status_msg.edit_text("🔴 <b>Không hỗ trợ tải livestream đang diễn ra.</b>", parse_mode="HTML")
            return True

        task_id = store_download_task(
            {
                "platform": "facebook",
                "url": info["webpage_url"],
                "title": info["title"],
                "uploader": info.get("uploader", "Không rõ"),
                "duration": info.get("duration"),
            }
        )
        caption = (
            f"📹 <b>{info['title'][:75]}</b>\n\n"
            f"👤 Tác giả: <code>{info.get('uploader', 'Không rõ')}</code>\n"
            f"⏱️ Thời lượng: <code>{format_duration(info.get('duration'))}</code>\n"
            f"👁️ Lượt xem: <code>{format_views(info.get('view_count'))}</code>\n\n"
            f"👇 <b>Chọn định dạng tải xuống:</b>"
        )
        kb = facebook_kb(task_id)
        await status_msg.delete()
        if info.get("thumbnail"):
            await message.reply_photo(photo=info["thumbnail"], caption=caption, reply_markup=kb, parse_mode="HTML")
        else:
            await message.reply(caption, reply_markup=kb, parse_mode="HTML")
        return True

    # ── SOUNDCLOUD ───────────────────────────────────────
    if is_soundcloud(url):
        status_msg = await message.reply("⏳ <b>Đang phân tích bài hát SoundCloud...</b>", parse_mode="HTML")
        sc_info = await asyncio.to_thread(get_soundcloud_info_sync, url)
        if not sc_info:
            await status_msg.edit_text(
                "❌ <b>Không thể truy xuất bài hát SoundCloud</b>\n\n"
                "• Bài hát có thể ở chế độ riêng tư hoặc link không hợp lệ.",
                parse_mode="HTML",
            )
            return True

        task_id = store_download_task(
            {
                "platform": "soundcloud",
                "url": sc_info["url"],
                "title": sc_info["title"],
                "uploader": sc_info.get("uploader", "Không rõ"),
                "duration": sc_info.get("duration"),
                "stream_url": sc_info.get("stream_url"),
            }
        )
        caption = (
            f"🎧 <b>{sc_info['title']}</b>\n\n"
            f"👤 Nghệ sĩ: <code>{sc_info.get('uploader', 'Không rõ')}</code>\n"
            f"⏱️ Thời lượng: <code>{format_duration(sc_info.get('duration'))}</code>\n"
            f"🎚️ Chất lượng: <code>MP3 320kbps</code>\n\n"
            f"👇 <b>Nhấn nút bên dưới để tải xuống:</b>"
        )
        kb = soundcloud_kb(task_id)
        await status_msg.delete()
        if sc_info.get("thumbnail"):
            await message.reply_photo(photo=sc_info["thumbnail"], caption=caption, reply_markup=kb, parse_mode="HTML")
        else:
            await message.reply(caption, reply_markup=kb, parse_mode="HTML")
        return True

    return False
