"""Callback handlers for media download actions."""
from __future__ import annotations

import asyncio
import glob
import os
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto

from app.bot.keyboards.downloader_kb import get_download_task
from app.logging_config import get_logger
from app.services.downloader import (
    MAX_FILE_SIZE,
    download_file_sync,
    format_duration,
    format_size,
    get_ffmpeg_path,
    split_media_sync,
    yt_dlp_download_sync,
)

logger = get_logger(__name__)
downloader_callback_router = Router(name="downloader_callback_router")

TEMP_DIR = Path("tmp")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


@downloader_callback_router.callback_query(F.data.startswith("dl:"))
async def handle_downloader_callback(query: CallbackQuery, bot: Bot) -> None:
    """Handle all media download button actions."""
    await query.answer()
    if not query.data or not query.message:
        return

    parts = query.data.split(":")
    if len(parts) < 4:
        return

    _, platform, action, task_id = parts[0], parts[1], parts[2], parts[3]
    task = get_download_task(task_id)

    if not task:
        try:
            await query.message.reply("⚠️ Phiên làm việc đã hết hạn. Vui lòng gửi lại link.", parse_mode="HTML")
        except Exception:
            pass
        return

    user_id = query.from_user.id
    chat_id = query.message.chat.id
    status_msg = await query.message.reply("🔄 <b>Đang khởi tạo tiến trình tải...</b>", parse_mode="HTML")

    # ══════════════════════════════════════════════════════════════
    #  YOUTUBE VIDEO (1080p)
    # ══════════════════════════════════════════════════════════════
    if platform == "yt" and action == "v":
        title = task.get("title", "Video YouTube")
        url = task["url"]
        temp_base = TEMP_DIR / f"ytv_{user_id}_{task_id}"
        ydl_opts = {
            "format": (
                "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
                "/bestvideo[height<=1080]+bestaudio"
                "/best[height<=1080]"
                "/bv*+ba/b"
            ),
            "outtmpl": f"{temp_base}.%(ext)s",
            "merge_output_format": "mp4",
            "ffmpeg_location": get_ffmpeg_path(),
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "format_sort": ["res:1080", "ext:mp4:m4a", "br", "asr"],
            "postprocessors": [{"key": "FFmpegMetadata", "add_metadata": True}],
        }
        if task.get("yt_cookie") and os.path.isfile(task["yt_cookie"]):
            ydl_opts["cookiefile"] = task["yt_cookie"]

        try:
            await status_msg.edit_text(
                f"⬇️ <b>Đang tải video từ YouTube...</b>\n\n"
                f"📄 <code>{title[:75]}</code>\n"
                f"🎞️ Chất lượng: Tối đa 1080p\n"
                f"<i>Vui lòng đợi trong giây lát...</i>",
                parse_mode="HTML",
            )
            await asyncio.to_thread(yt_dlp_download_sync, ydl_opts, url)

            candidates = [f for f in glob.glob(f"{temp_base}.*") if not f.endswith(".part")]
            if not candidates:
                raise FileNotFoundError("Không tìm thấy file sau khi tải xong.")
            temp_filename = candidates[0]
            file_size = os.path.getsize(temp_filename)

            caption = (
                f"📺 <b>{title[:80]}</b>\n"
                f"👤 {task.get('uploader', '')}\n"
                f"⏱️ {format_duration(task.get('duration'))}"
            )

            await status_msg.edit_text(f"📤 <b>Đang gửi video lên Telegram...</b> ({format_size(file_size)})", parse_mode="HTML")

            if file_size <= MAX_FILE_SIZE:
                await bot.send_video(
                    chat_id=chat_id,
                    video=FSInputFile(temp_filename),
                    caption=caption,
                    parse_mode="HTML",
                    supports_streaming=True,
                    duration=int(task["duration"]) if task.get("duration") else None,
                )
            else:
                chunks = await asyncio.to_thread(split_media_sync, temp_filename, True)
                for idx, chunk_file in enumerate(chunks, 1):
                    await bot.send_video(
                        chat_id=chat_id,
                        video=FSInputFile(chunk_file),
                        caption=f"📺 {title[:60]} — Phần {idx}/{len(chunks)}",
                        supports_streaming=True,
                    )

            await status_msg.delete()
        except Exception as exc:
            logger.exception("Error downloading YouTube video for user %d: %s", user_id, exc)
            await status_msg.edit_text("❌ <b>Tải video thất bại.</b> Vui lòng thử lại sau.", parse_mode="HTML")
        finally:
            for f in glob.glob(f"{temp_base}*"):
                try:
                    os.remove(f)
                except OSError:
                    pass
        return

    # ══════════════════════════════════════════════════════════════
    #  YOUTUBE AUDIO (MP3 320kbps)
    # ══════════════════════════════════════════════════════════════
    if platform == "yt" and action == "a":
        title = task.get("title", "Âm thanh YouTube")
        url = task["url"]
        temp_base = TEMP_DIR / f"yta_{user_id}_{task_id}"
        temp_mp3 = f"{temp_base}.mp3"
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": f"{temp_base}.%(ext)s",
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
                {"key": "FFmpegMetadata", "add_metadata": True},
            ],
            "ffmpeg_location": get_ffmpeg_path(),
            "quiet": True,
            "no_warnings": True,
        }
        if task.get("yt_cookie") and os.path.isfile(task["yt_cookie"]):
            ydl_opts["cookiefile"] = task["yt_cookie"]

        try:
            await status_msg.edit_text(
                f"⬇️ <b>Đang tải & chuyển đổi âm thanh...</b>\n\n"
                f"🎵 <code>{title[:75]}</code>\n"
                f"🎚️ MP3 320kbps",
                parse_mode="HTML",
            )
            await asyncio.to_thread(yt_dlp_download_sync, ydl_opts, url)

            if not os.path.exists(temp_mp3):
                candidates = [f for f in glob.glob(f"{temp_base}.*") if not f.endswith(".part")]
                if not candidates:
                    raise FileNotFoundError("Không tìm thấy file MP3 sau khi xử lý.")
                temp_mp3 = candidates[0]

            file_size = os.path.getsize(temp_mp3)
            caption = f"🎵 <b>{title[:80]}</b>\n👤 {task.get('uploader', '')}"

            await status_msg.edit_text(f"📤 <b>Đang gửi MP3 lên Telegram...</b> ({format_size(file_size)})", parse_mode="HTML")

            if file_size <= MAX_FILE_SIZE:
                await bot.send_audio(
                    chat_id=chat_id,
                    audio=FSInputFile(temp_mp3),
                    caption=caption,
                    title=title[:64],
                    performer=task.get("uploader"),
                    duration=int(task["duration"]) if task.get("duration") else None,
                    parse_mode="HTML",
                )
            else:
                chunks = await asyncio.to_thread(split_media_sync, temp_mp3, False)
                for idx, chunk_file in enumerate(chunks, 1):
                    await bot.send_audio(
                        chat_id=chat_id,
                        audio=FSInputFile(chunk_file),
                        caption=f"🎵 {title[:60]} — Phần {idx}/{len(chunks)}",
                    )
            await status_msg.delete()
        except Exception as exc:
            logger.exception("Error downloading YouTube audio for user %d: %s", user_id, exc)
            await status_msg.edit_text("❌ <b>Tải MP3 thất bại.</b> Vui lòng thử lại sau.", parse_mode="HTML")
        finally:
            for f in glob.glob(f"{temp_base}*"):
                try:
                    os.remove(f)
                except OSError:
                    pass
        return

    # ══════════════════════════════════════════════════════════════
    #  YOUTUBE MP4 DOCUMENT (GỐC · KHÔNG NÉN)
    # ══════════════════════════════════════════════════════════════
    if platform == "yt" and action == "doc":
        title = task.get("title", "Video YouTube")
        url = task["url"]
        temp_base = TEMP_DIR / f"ytdoc_{user_id}_{task_id}"
        ydl_opts = {
            "format": (
                "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
                "/bestvideo[height<=1080]+bestaudio"
                "/best[height<=1080]"
                "/bv*+ba/b"
            ),
            "outtmpl": f"{temp_base}.%(ext)s",
            "merge_output_format": "mp4",
            "ffmpeg_location": get_ffmpeg_path(),
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "postprocessors": [{"key": "FFmpegMetadata", "add_metadata": True}],
        }
        if task.get("yt_cookie") and os.path.isfile(task["yt_cookie"]):
            ydl_opts["cookiefile"] = task["yt_cookie"]

        try:
            await status_msg.edit_text(f"⬇️ <b>Đang tải MP4 1080p gốc...</b>\n\n📄 <code>{title[:75]}</code>", parse_mode="HTML")
            await asyncio.to_thread(yt_dlp_download_sync, ydl_opts, url)

            candidates = [f for f in glob.glob(f"{temp_base}.*") if not f.endswith(".part")]
            if not candidates:
                raise FileNotFoundError("Không tìm thấy file sau khi tải.")
            temp_filename = candidates[0]
            file_size = os.path.getsize(temp_filename)

            caption = f"📁 <b>{title[:80]}</b>\n👤 {task.get('uploader', '')} · MP4 1080p File gốc"
            await status_msg.edit_text(f"📤 <b>Đang gửi file gốc lên Telegram...</b> ({format_size(file_size)})", parse_mode="HTML")

            if file_size <= MAX_FILE_SIZE:
                await bot.send_document(
                    chat_id=chat_id,
                    document=FSInputFile(temp_filename, filename=f"{title[:60]}.mp4"),
                    caption=caption,
                    parse_mode="HTML",
                )
            else:
                chunks = await asyncio.to_thread(split_media_sync, temp_filename, True)
                for idx, chunk_file in enumerate(chunks, 1):
                    await bot.send_document(
                        chat_id=chat_id,
                        document=FSInputFile(chunk_file, filename=f"{title[:50]}_part{idx}.mp4"),
                        caption=f"📁 {title[:60]} — Phần {idx}/{len(chunks)}",
                    )
            await status_msg.delete()
        except Exception as exc:
            logger.exception("Error downloading YouTube doc for user %d: %s", user_id, exc)
            await status_msg.edit_text("❌ <b>Tải MP4 thất bại.</b>", parse_mode="HTML")
        finally:
            for f in glob.glob(f"{temp_base}*"):
                try:
                    os.remove(f)
                except OSError:
                    pass
        return

    # ══════════════════════════════════════════════════════════════
    #  YOUTUBE PLAYLIST (Video, Audio, Doc)
    # ══════════════════════════════════════════════════════════════
    if platform == "yt" and action in ("plv", "pla", "pldoc"):
        is_video_pl = action in ("plv", "pldoc")
        is_doc_pl = action == "pldoc"
        entries = task.get("entries", [])
        pl_title = task.get("title", "Playlist YouTube")
        uploader_pl = task.get("uploader", "")
        cookie_path = task.get("yt_cookie", "")
        cookie_opts = {"cookiefile": cookie_path} if cookie_path and os.path.isfile(cookie_path) else {}

        total = len(entries)
        ok_count, fail_count = 0, 0

        for idx, entry in enumerate(entries, 1):
            vid_title = entry.get("title", f"Video {idx}")
            vid_url = entry.get("url") or f"https://www.youtube.com/watch?v={entry['id']}"
            temp_base = TEMP_DIR / f"pl_{user_id}_{task_id}_{idx}"

            try:
                await status_msg.edit_text(
                    f"📥 <b>Đang tải playlist ({idx}/{total})</b>\n\n"
                    f"📋 <code>{pl_title[:50]}</code>\n"
                    f"🎬 <code>{vid_title[:50]}</code>\n\n"
                    f"✅ Thành công: <code>{ok_count}</code> · ❌ Lỗi: <code>{fail_count}</code>",
                    parse_mode="HTML",
                )
            except Exception:
                pass

            try:
                if is_video_pl:
                    ydl_opts = {
                        "format": (
                            "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
                            "/bestvideo[height<=1080]+bestaudio"
                            "/best[height<=1080]/best"
                        ),
                        "outtmpl": f"{temp_base}.%(ext)s",
                        "merge_output_format": "mp4",
                        "ffmpeg_location": get_ffmpeg_path(),
                        "quiet": True,
                        "no_warnings": True,
                        "postprocessors": [{"key": "FFmpegMetadata", "add_metadata": True}],
                        **cookie_opts,
                    }
                else:
                    ydl_opts = {
                        "format": "bestaudio/best",
                        "outtmpl": f"{temp_base}.%(ext)s",
                        "postprocessors": [
                            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
                            {"key": "FFmpegMetadata", "add_metadata": True},
                        ],
                        "ffmpeg_location": get_ffmpeg_path(),
                        "quiet": True,
                        "no_warnings": True,
                        **cookie_opts,
                    }

                await asyncio.to_thread(yt_dlp_download_sync, ydl_opts, vid_url)
                candidates = [f for f in glob.glob(f"{temp_base}.*") if not f.endswith(".part")]
                if not candidates:
                    raise FileNotFoundError("File not found.")
                temp_file = candidates[0]
                file_size = os.path.getsize(temp_file)

                cap_item = f"<b>{vid_title[:80]}</b>\n👤 {uploader_pl} · [{idx}/{total}]"

                if file_size <= MAX_FILE_SIZE:
                    if is_doc_pl:
                        await bot.send_document(
                            chat_id=chat_id,
                            document=FSInputFile(temp_file, filename=f"{vid_title[:50]}.mp4"),
                            caption=cap_item,
                            parse_mode="HTML",
                        )
                    elif is_video_pl:
                        await bot.send_video(
                            chat_id=chat_id,
                            video=FSInputFile(temp_file),
                            caption=cap_item,
                            parse_mode="HTML",
                            supports_streaming=True,
                        )
                    else:
                        await bot.send_audio(
                            chat_id=chat_id,
                            audio=FSInputFile(temp_file),
                            caption=cap_item,
                            title=vid_title[:64],
                            performer=uploader_pl,
                            parse_mode="HTML",
                        )
                else:
                    chunks = await asyncio.to_thread(split_media_sync, temp_file, is_video_pl)
                    for ci, chunk_file in enumerate(chunks, 1):
                        part_cap = f"{vid_title[:60]} — Phần {ci}/{len(chunks)}"
                        if is_doc_pl:
                            await bot.send_document(
                                chat_id=chat_id,
                                document=FSInputFile(chunk_file, filename=f"{vid_title[:45]}_part{ci}.mp4"),
                                caption=part_cap,
                            )
                        elif is_video_pl:
                            await bot.send_video(
                                chat_id=chat_id,
                                video=FSInputFile(chunk_file),
                                caption=part_cap,
                                supports_streaming=True,
                            )
                        else:
                            await bot.send_audio(
                                chat_id=chat_id,
                                audio=FSInputFile(chunk_file),
                                caption=part_cap,
                            )
                ok_count += 1
            except Exception as exc:
                fail_count += 1
                logger.warning("Playlist item error [%d/%d]: %s", idx, total, exc)
            finally:
                for tmp in glob.glob(f"{temp_base}*"):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass

        try:
            await status_msg.edit_text(
                f"✅ <b>Hoàn tất tải playlist!</b>\n\n"
                f"📋 <code>{pl_title[:60]}</code>\n"
                f"✅ Thành công: <code>{ok_count}/{total}</code>\n"
                f"❌ Lỗi: <code>{fail_count}/{total}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    # ══════════════════════════════════════════════════════════════
    #  TIKTOK (Video, Music, Photo Album, Document)
    # ══════════════════════════════════════════════════════════════
    if platform == "tk":
        title = task.get("title", "Nội dung TikTok")

        # Album Ảnh
        if action == "img":
            images = task.get("images", [])
            try:
                await status_msg.edit_text(f"📸 <b>Đang gửi {len(images)} ảnh...</b>", parse_mode="HTML")
                chunk_size = 10
                for group_idx, i in enumerate(range(0, len(images), chunk_size), 1):
                    image_chunk = images[i : i + chunk_size]
                    media_group = []
                    for j, img_url in enumerate(image_chunk):
                        if i == 0 and j == 0:
                            media_group.append(InputMediaPhoto(media=img_url, caption=f"📸 <b>{title[:80]}</b>", parse_mode="HTML"))
                        else:
                            media_group.append(InputMediaPhoto(media=img_url))
                    await bot.send_media_group(chat_id=chat_id, media=media_group)
                await status_msg.delete()
            except Exception as exc:
                logger.exception("Error sending TikTok photos: %s", exc)
                await status_msg.edit_text("❌ <b>Gửi album ảnh thất bại.</b>", parse_mode="HTML")
            return

        # Video (No Watermark) hoặc Nhạc
        if action in ("v", "a"):
            is_video = action == "v"
            target_url = task["play"] if is_video else task["music"]
            file_ext = ".mp4" if is_video else ".mp3"
            temp_file = TEMP_DIR / f"tk_{user_id}_{task_id}{file_ext}"

            if not target_url:
                await status_msg.edit_text("⚠️ Không tìm thấy đường dẫn tải.", parse_mode="HTML")
                return

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.tiktok.com/",
            }

            try:
                await status_msg.edit_text(f"⬇️ <b>Đang tải {'video' if is_video else 'nhạc'} TikTok...</b>", parse_mode="HTML")
                try:
                    file_size = await asyncio.to_thread(download_file_sync, target_url, str(temp_file), headers)
                except Exception:
                    # Retry with TikWM proxy
                    if task.get("id") and task["id"] != "fallback_id":
                        proxy_url = (
                            f"https://www.tikwm.com/video/media/play/{task['id']}.mp4"
                            if is_video
                            else f"https://www.tikwm.com/video/music/{task['id']}.mp3"
                        )
                        file_size = await asyncio.to_thread(download_file_sync, proxy_url, str(temp_file), headers)
                    else:
                        raise

                caption = f"{'🎬' if is_video else '🎵'} <b>{title[:80]}</b>"
                await status_msg.edit_text(f"📤 <b>Đang gửi lên Telegram...</b> ({format_size(file_size)})", parse_mode="HTML")

                if file_size <= MAX_FILE_SIZE:
                    if is_video:
                        await bot.send_video(
                            chat_id=chat_id,
                            video=FSInputFile(str(temp_file)),
                            caption=caption,
                            supports_streaming=True,
                            parse_mode="HTML",
                        )
                    else:
                        await bot.send_audio(
                            chat_id=chat_id,
                            audio=FSInputFile(str(temp_file)),
                            caption=caption,
                            title=title[:64],
                            parse_mode="HTML",
                        )
                else:
                    chunks = await asyncio.to_thread(split_media_sync, str(temp_file), is_video)
                    for ci, chunk_file in enumerate(chunks, 1):
                        part_cap = f"{title[:60]} — Phần {ci}/{len(chunks)}"
                        if is_video:
                            await bot.send_video(chat_id=chat_id, video=FSInputFile(chunk_file), caption=part_cap, supports_streaming=True)
                        else:
                            await bot.send_audio(chat_id=chat_id, audio=FSInputFile(chunk_file), caption=part_cap)
                await status_msg.delete()
            except Exception as exc:
                logger.exception("Error downloading TikTok: %s", exc)
                await status_msg.edit_text("❌ <b>Tải nội dung TikTok thất bại.</b>", parse_mode="HTML")
            finally:
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except OSError:
                        pass
            return

        # TikTok MP4 1080p qua yt-dlp (File gốc)
        if action == "doc":
            tk_dl_url = task.get("original_url") or task.get("play", "")
            temp_base = TEMP_DIR / f"tkdoc_{user_id}_{task_id}"
            ydl_opts = {
                "format": (
                    "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
                    "/bestvideo[height<=1080]+bestaudio"
                    "/best[height<=1080]/best"
                ),
                "outtmpl": f"{temp_base}.%(ext)s",
                "merge_output_format": "mp4",
                "ffmpeg_location": get_ffmpeg_path(),
                "quiet": True,
                "no_warnings": True,
                "postprocessors": [{"key": "FFmpegMetadata", "add_metadata": True}],
            }
            try:
                await status_msg.edit_text(f"⬇️ <b>Đang tải MP4 TikTok gốc...</b>\n\n📄 <code>{title[:75]}</code>", parse_mode="HTML")
                await asyncio.to_thread(yt_dlp_download_sync, ydl_opts, tk_dl_url)
                candidates = [f for f in glob.glob(f"{temp_base}.*") if not f.endswith(".part")]
                if not candidates:
                    raise FileNotFoundError("File not found.")
                temp_filename = candidates[0]
                file_size = os.path.getsize(temp_filename)

                caption = f"📁 <b>{title[:80]}</b>\n🎬 TikTok · MP4 1080p File gốc"
                await status_msg.edit_text(f"📤 <b>Đang gửi MP4 lên Telegram...</b> ({format_size(file_size)})", parse_mode="HTML")

                if file_size <= MAX_FILE_SIZE:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=FSInputFile(temp_filename, filename=f"{title[:60]}.mp4"),
                        caption=caption,
                        parse_mode="HTML",
                    )
                else:
                    chunks = await asyncio.to_thread(split_media_sync, temp_filename, True)
                    for ci, chunk_file in enumerate(chunks, 1):
                        await bot.send_document(
                            chat_id=chat_id,
                            document=FSInputFile(chunk_file, filename=f"{title[:50]}_part{ci}.mp4"),
                            caption=f"📁 {title[:60]} — Phần {ci}/{len(chunks)}",
                        )
                await status_msg.delete()
            except Exception as exc:
                logger.exception("Error downloading TikTok doc: %s", exc)
                await status_msg.edit_text("❌ <b>Tải MP4 thất bại.</b> Vui lòng thử nút Video thường.", parse_mode="HTML")
            finally:
                for f in glob.glob(f"{temp_base}*"):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
            return

    # ══════════════════════════════════════════════════════════════
    #  FACEBOOK (Video, Audio, Doc)
    # ══════════════════════════════════════════════════════════════
    if platform == "fb":
        title = task.get("title", "Video Facebook")
        url = task["url"]
        temp_base = TEMP_DIR / f"fb_{user_id}_{task_id}"

        # Video / Doc
        if action in ("v", "doc"):
            is_doc = action == "doc"
            ydl_opts = {
                "format": (
                    "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
                    "/bestvideo[height<=1080]+bestaudio"
                    "/best[height<=1080]/best"
                ),
                "outtmpl": f"{temp_base}.%(ext)s",
                "merge_output_format": "mp4",
                "ffmpeg_location": get_ffmpeg_path(),
                "quiet": True,
                "no_warnings": True,
                "postprocessors": [{"key": "FFmpegMetadata", "add_metadata": True}],
            }
            fb_cookie = os.environ.get("FB_COOKIES_FILE", "")
            if fb_cookie and os.path.isfile(fb_cookie):
                ydl_opts["cookiefile"] = fb_cookie

            try:
                await status_msg.edit_text(f"⬇️ <b>Đang tải video Facebook...</b>\n\n📄 <code>{title[:75]}</code>", parse_mode="HTML")
                await asyncio.to_thread(yt_dlp_download_sync, ydl_opts, url)
                candidates = [f for f in glob.glob(f"{temp_base}.*") if not f.endswith(".part")]
                if not candidates:
                    raise FileNotFoundError("File not found.")
                temp_filename = candidates[0]
                file_size = os.path.getsize(temp_filename)

                caption = f"{'📁' if is_doc else '📹'} <b>{title[:80]}</b>\n👤 {task.get('uploader', '')}"
                await status_msg.edit_text(f"📤 <b>Đang gửi lên Telegram...</b> ({format_size(file_size)})", parse_mode="HTML")

                if file_size <= MAX_FILE_SIZE:
                    if is_doc:
                        await bot.send_document(
                            chat_id=chat_id,
                            document=FSInputFile(temp_filename, filename=f"{title[:60]}.mp4"),
                            caption=caption,
                            parse_mode="HTML",
                        )
                    else:
                        await bot.send_video(
                            chat_id=chat_id,
                            video=FSInputFile(temp_filename),
                            caption=caption,
                            supports_streaming=True,
                            duration=int(task["duration"]) if task.get("duration") else None,
                            parse_mode="HTML",
                        )
                else:
                    chunks = await asyncio.to_thread(split_media_sync, temp_filename, True)
                    for ci, chunk_file in enumerate(chunks, 1):
                        part_cap = f"📹 {title[:60]} — Phần {ci}/{len(chunks)}"
                        if is_doc:
                            await bot.send_document(
                                chat_id=chat_id,
                                document=FSInputFile(chunk_file, filename=f"{title[:50]}_part{ci}.mp4"),
                                caption=part_cap,
                            )
                        else:
                            await bot.send_video(chat_id=chat_id, video=FSInputFile(chunk_file), caption=part_cap, supports_streaming=True)
                await status_msg.delete()
            except Exception as exc:
                logger.exception("Error downloading Facebook video: %s", exc)
                await status_msg.edit_text("❌ <b>Tải video Facebook thất bại.</b>", parse_mode="HTML")
            finally:
                for f in glob.glob(f"{temp_base}*"):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
            return

        # Audio
        if action == "a":
            temp_mp3 = f"{temp_base}.mp3"
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": f"{temp_base}.%(ext)s",
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
                    {"key": "FFmpegMetadata", "add_metadata": True},
                ],
                "ffmpeg_location": get_ffmpeg_path(),
                "quiet": True,
                "no_warnings": True,
            }
            try:
                await status_msg.edit_text(f"⬇️ <b>Đang tải âm thanh Facebook...</b>\n\n🎵 <code>{title[:75]}</code>", parse_mode="HTML")
                await asyncio.to_thread(yt_dlp_download_sync, ydl_opts, url)
                if not os.path.exists(temp_mp3):
                    candidates = [f for f in glob.glob(f"{temp_base}.*") if not f.endswith(".part")]
                    if not candidates:
                        raise FileNotFoundError("File not found.")
                    temp_mp3 = candidates[0]
                file_size = os.path.getsize(temp_mp3)

                caption = f"🎵 <b>{title[:80]}</b>\n👤 {task.get('uploader', '')} · MP3 320kbps"
                await status_msg.edit_text(f"📤 <b>Đang gửi MP3 lên Telegram...</b> ({format_size(file_size)})", parse_mode="HTML")

                if file_size <= MAX_FILE_SIZE:
                    await bot.send_audio(
                        chat_id=chat_id,
                        audio=FSInputFile(temp_mp3),
                        caption=caption,
                        title=title[:64],
                        performer=task.get("uploader"),
                        duration=int(task["duration"]) if task.get("duration") else None,
                        parse_mode="HTML",
                    )
                else:
                    chunks = await asyncio.to_thread(split_media_sync, temp_mp3, False)
                    for ci, chunk_file in enumerate(chunks, 1):
                        await bot.send_audio(
                            chat_id=chat_id,
                            audio=FSInputFile(chunk_file),
                            caption=f"🎵 {title[:60]} — Phần {ci}/{len(chunks)}",
                        )
                await status_msg.delete()
            except Exception as exc:
                logger.exception("Error downloading Facebook audio: %s", exc)
                await status_msg.edit_text("❌ <b>Tải âm thanh thất bại.</b>", parse_mode="HTML")
            finally:
                for f in glob.glob(f"{temp_base}*"):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
            return

    # ══════════════════════════════════════════════════════════════
    #  SOUNDCLOUD (MP3 320kbps)
    # ══════════════════════════════════════════════════════════════
    if platform == "sc" and action == "a":
        title = task.get("title", "Bài hát SoundCloud")
        url = task["url"]
        temp_base = TEMP_DIR / f"sc_{user_id}_{task_id}"
        temp_mp3 = f"{temp_base}.mp3"
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": f"{temp_base}.%(ext)s",
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
            ],
            "ffmpeg_location": get_ffmpeg_path(),
            "quiet": True,
            "no_warnings": True,
            "source_address": "0.0.0.0",
            "socket_timeout": 30,
            "retries": 5,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                ),
            },
        }
        try:
            await status_msg.edit_text(f"⬇️ <b>Đang tải bài hát từ SoundCloud...</b>\n\n🎵 <code>{title[:75]}</code>", parse_mode="HTML")
            await asyncio.to_thread(yt_dlp_download_sync, ydl_opts, url)
            if not os.path.exists(temp_mp3):
                candidates = [f for f in glob.glob(f"{temp_base}.*") if not f.endswith(".part")]
                if not candidates:
                    raise FileNotFoundError("File not found.")
                temp_mp3 = candidates[0]
            file_size = os.path.getsize(temp_mp3)

            caption = f"🎧 <b>{title[:80]}</b>\n👤 {task.get('uploader', '')} · MP3 320kbps"
            await status_msg.edit_text(f"📤 <b>Đang gửi bài hát lên Telegram...</b> ({format_size(file_size)})", parse_mode="HTML")

            if file_size <= MAX_FILE_SIZE:
                await bot.send_audio(
                    chat_id=chat_id,
                    audio=FSInputFile(temp_mp3),
                    caption=caption,
                    title=title[:64],
                    performer=task.get("uploader"),
                    duration=int(task["duration"]) if task.get("duration") else None,
                    parse_mode="HTML",
                )
            else:
                chunks = await asyncio.to_thread(split_media_sync, temp_mp3, False)
                for ci, chunk_file in enumerate(chunks, 1):
                    await bot.send_audio(
                        chat_id=chat_id,
                        audio=FSInputFile(chunk_file),
                        caption=f"🎵 {title[:60]} — Phần {ci}/{len(chunks)}",
                    )
            await status_msg.delete()
        except Exception as exc:
            logger.exception("Error downloading SoundCloud: %s", exc)
            await status_msg.edit_text("❌ <b>Tải bài hát thất bại.</b>", parse_mode="HTML")
        finally:
            for f in glob.glob(f"{temp_base}*"):
                try:
                    os.remove(f)
                except OSError:
                    pass
        return
