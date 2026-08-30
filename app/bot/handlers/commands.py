"""Command handlers: /start, /help, shortcuts, free-text search, and inline queries."""
from __future__ import annotations

import html
import re

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks.router import _format_movie_detail
from app.bot.handlers.downloader_handler import handle_social_url_download
from app.bot.keyboards.common import (
    countries_keyboard,
    favorites_keyboard,
    genres_keyboard,
    home_keyboard,
    movie_detail_keyboard,
    search_results_keyboard,
    years_keyboard,
)
from app.config import Config
from app.database.repositories import UserRepository
from app.logging_config import get_logger, session_id_var
from app.providers.kkphim.exceptions import KKPhimError
from app.services.favorite_service import FavoriteService
from app.services.movie_service import MovieService
from app.services.session_service import SessionService

logger = get_logger(__name__)

command_router = Router(name="command_router")


@command_router.message(Command("start"))
async def cmd_start(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.get_or_create(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )

    # Check for deep-linking parameter: /start m_<slug> or /start movie_<slug> or /start <slug>
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].strip():
        payload = args[1].strip()
        slug = payload
        if payload.startswith("m_"):
            slug = payload[2:]
        elif payload.startswith("movie_"):
            slug = payload[6:]

        session_service = SessionService(db_session, config)
        session = await session_service.create(
            user_id=user.id,
            chat_id=message.chat.id,
            query=f"m:{slug}",
            message_id=message.message_id,
        )
        session_id_var.set(session.id)

        try:
            movie = await movie_service.get_detail(slug)
        except KKPhimError:
            await message.answer(
                "❌ Không tìm thấy thông tin bộ phim này hoặc phim đã bị gỡ.",
                reply_markup=home_keyboard(),
            )
            return

        await session_service.set_selected_movie(session.id, movie)
        favorite_service = FavoriteService(db_session)
        is_fav = await favorite_service.is_favorite(user.id, slug)
        text = _format_movie_detail(movie)
        keyboard = movie_detail_keyboard(
            session_id=session.id,
            slug=slug,
            is_favorite=is_fav,
            has_servers=bool(movie.servers),
            trailer_url=movie.trailer_url,
        )
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        return

    # Normal /start
    user_name = html.escape(message.from_user.first_name or "bạn")
    text = (
        f"👋 Xin chào <b>{user_name}</b>!\n\n"
        "🎬 <b>KKPhim & Media Downloader Bot</b>\n\n"
        "<b>1. Xem & Tìm Kiếm Phim:</b>\n"
        "• Gõ trực tiếp tên phim vào ô chat (ví dụ: <code>Mai</code>, <code>One Piece</code>)\n"
        "• Khám phá các danh mục phim bằng nút bên dưới\n\n"
        "<b>2. Tải Media Mạng Xã Hội Đa Nền Tảng:</b>\n"
        "• <b>TikTok</b>: Video không logo, album ảnh, nhạc MP3, file gốc\n"
        "• <b>YouTube</b>: Video 1080p, MP3 320kbps, Playlist, YouTube Mix 🍪\n"
        "• <b>Facebook</b>: Video/Reels 1080p, MP3, file gốc\n"
        "• <b>SoundCloud</b>: Nhạc MP3 320kbps\n"
        "👉 <i>Chỉ cần dán trực tiếp link video/bài hát vào đây!</i>\n\n"
        "❓ Gõ /help để xem hướng dẫn chi tiết."
    )
    await message.answer(text, reply_markup=home_keyboard(), parse_mode="HTML")


@command_router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    text = (
        "📖 <b>Hướng dẫn sử dụng KKPhim & Media Bot</b>\n\n"
        "<b>── 🎬 XEM & TÌM PHIM ──</b>\n"
        "• Gõ trực tiếp: <code>Avengers</code>, <code>One Piece</code>, <code>Lật mặt</code>...\n"
        "• Lệnh tìm: <code>/tim &lt;tên phim&gt;</code> (ví dụ: <code>/tim Conan</code>)\n"
        "• Chia sẻ: Bấm nút <b>🔗 Chia sẻ</b> hoặc gõ <code>@tên_bot &lt;tên phim&gt;</code>\n"
        "• Lệnh danh mục: /phimmoi, /chieurap, /phimbo, /phimle, /hoathinh, /theloai, /quocgia, /nam, /yeuthich\n\n"
        "<b>── 📥 TẢI MEDIA MẠNG XÃ HỘI ──</b>\n"
        "• <b>Cách dùng:</b> Chỉ cần dán link TikTok, YouTube, Facebook, SoundCloud vào đây.\n"
        "• <b>TikTok:</b> Video không logo, album ảnh, tách MP3, MP4 gốc\n"
        "• <b>YouTube:</b> Video 1080p, MP3 320kbps, Playlist (≤50 video), YouTube Mix/Radio\n"
        "• <b>Facebook:</b> Video/Reels 1080p, MP3 320kbps (chỉ hỗ trợ nội dung công khai)\n"
        "• <b>SoundCloud:</b> MP3 320kbps\n\n"
        "<b>── 🍪 YOUTUBE COOKIE & MIX ──</b>\n"
        "• Gửi file <code>cookies.txt</code> trực tiếp vào bot để nạp cookie tải YouTube Mix\n"
        "• /mycookie — Xem trạng thái cookie\n"
        "• /delcookie — Xóa cookie"
    )
    await message.answer(text, reply_markup=home_keyboard(), parse_mode="HTML")


@command_router.message(Command("tim"))
async def cmd_search(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "🔍 Vui lòng nhập tên phim cần tìm.\nVí dụ: <code>/tim Harry Potter</code>",
            parse_mode="HTML",
        )
        return
    await _execute_search(message, db_session, config, movie_service, args[1].strip())


@command_router.message(Command("phimmoi"))
async def cmd_phimmoi(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    await _execute_list(message, db_session, config, movie_service, "new", "🆕 Phim mới cập nhật")


@command_router.message(Command("chieurap"))
async def cmd_chieurap(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    await _execute_list(message, db_session, config, movie_service, "popular", "🔥 Phim chiếu rạp nổi bật")


@command_router.message(Command("phimbo"))
async def cmd_phimbo(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    await _execute_type_list(message, db_session, config, movie_service, "phim-bo", "📺 Danh sách Phim bộ")


@command_router.message(Command("phimle"))
async def cmd_phimle(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    await _execute_type_list(message, db_session, config, movie_service, "phim-le", "🎬 Danh sách Phim lẻ")


@command_router.message(Command("hoathinh"))
async def cmd_hoathinh(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    await _execute_type_list(message, db_session, config, movie_service, "hoat-hinh", "🧸 Danh sách Phim hoạt hình")


@command_router.message(Command("theloai"))
async def cmd_theloai(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.get_or_create(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    session_service = SessionService(db_session, config)
    session = await session_service.create(user_id=user.id, chat_id=message.chat.id)
    genres = await movie_service.get_genres()
    await message.answer(
        "🎭 <b>Danh sách Thể loại:</b>",
        reply_markup=genres_keyboard(session.id, genres, page=1),
        parse_mode="HTML",
    )


@command_router.message(Command("quocgia"))
async def cmd_quocgia(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.get_or_create(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    session_service = SessionService(db_session, config)
    session = await session_service.create(user_id=user.id, chat_id=message.chat.id)
    countries = await movie_service.get_countries()
    await message.answer(
        "🌍 <b>Danh sách Quốc gia:</b>",
        reply_markup=countries_keyboard(session.id, countries, page=1),
        parse_mode="HTML",
    )


@command_router.message(Command("nam"))
async def cmd_nam(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.get_or_create(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    session_service = SessionService(db_session, config)
    session = await session_service.create(user_id=user.id, chat_id=message.chat.id)
    years = await movie_service.get_years()
    await message.answer(
        "📅 <b>Năm phát hành:</b>",
        reply_markup=years_keyboard(session.id, years, page=1),
        parse_mode="HTML",
    )


@command_router.message(Command("yeuthich"))
async def cmd_yeuthich(message: types.Message, db_session: AsyncSession, config: Config) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.get_or_create(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    favorite_service = FavoriteService(db_session)
    favorites = await favorite_service.list(user.id)
    session_service = SessionService(db_session, config)
    session = await session_service.create(user_id=user.id, chat_id=message.chat.id)

    if not favorites:
        await message.answer(
            "❤️ <b>Danh sách yêu thích trống</b>\n\nBạn chưa thêm bộ phim nào vào mục yêu thích.",
            reply_markup=home_keyboard(),
            parse_mode="HTML",
        )
        return

    await message.answer(
        "❤️ <b>Danh sách phim yêu thích của bạn:</b>",
        reply_markup=favorites_keyboard(session.id, [(f[0], f[1]) if isinstance(f, tuple) else (f.movie_slug, f.movie_name) for f in favorites]),
        parse_mode="HTML",
    )


@command_router.inline_query()
async def handle_inline_query(
    inline_query: InlineQuery,
    movie_service: MovieService,
    config: Config,
) -> None:
    """Handle inline queries (@bot query) for movie sharing across chats."""
    query = inline_query.query.strip()
    bot_user = await inline_query.bot.get_me()
    bot_username = bot_user.username or "bot"

    try:
        if not query:
            result = await movie_service.list_popular(page=1)
        else:
            result = await movie_service.search(query, page=1, limit=15)
    except Exception as exc:
        logger.warning("Inline query search failed: %s", exc)
        await inline_query.answer([], cache_time=10, is_personal=False)
        return

    articles: list[InlineQueryResultArticle] = []
    for item in result.items[:15]:
        desc_parts = []
        if item.publish_year:
            desc_parts.append(str(item.publish_year))
        if item.quality:
            desc_parts.append(item.quality)
        if item.episode_current:
            desc_parts.append(item.episode_current)
        description = " • ".join(desc_parts) or "Phim KKPhim"

        msg_text = (
            f"🎬 <b>{html.escape(item.name)}</b>\n"
            f"<i>{html.escape(item.origin_name or '')}</i>\n\n"
            f"📅 Năm phát hành: <b>{item.publish_year or 'N/A'}</b>\n"
            f"🔹 Chất lượng: <b>{html.escape(item.quality or 'HD')}</b>\n"
            f"🎞 Trạng thái: <b>{html.escape(item.episode_current or 'Full')}</b>\n\n"
            f"🍿 <i>Xem phim chất lượng cao miễn phí trên KKPhim Bot!</i>"
        )

        share_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="▶️ Xem phim ngay",
                        url=f"https://t.me/{bot_username}?start=m_{item.slug}",
                    )
                ]
            ]
        )

        articles.append(
            InlineQueryResultArticle(
                id=item.slug,
                title=item.name,
                description=description,
                thumbnail_url=item.thumb_url or item.poster_url,
                input_message_content=InputTextMessageContent(
                    message_text=msg_text,
                    parse_mode="HTML",
                ),
                reply_markup=share_kb,
            )
        )

    await inline_query.answer(articles, cache_time=300, is_personal=False)


@command_router.message(F.text)
async def handle_text_search(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    """Handle free-text search and social media download links."""
    # 1. Ignore empty text or messages sent by any bot
    if not message.text or (message.from_user and message.from_user.is_bot):
        return

    raw_text = message.text.strip()
    if not raw_text or raw_text.startswith("/"):
        return

    # 2. Check if this is a social media download link (TikTok, YouTube, FB, SoundCloud)
    if await handle_social_url_download(message, message.bot):
        return

    # 3. Check group chat vs private chat
    if message.chat.type in {"group", "supergroup"}:
        bot_user = await message.bot.get_me()
        bot_id = bot_user.id
        bot_username = (bot_user.username or "").lower()

        is_reply_to_bot = bool(
            message.reply_to_message
            and message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == bot_id
        )

        is_mentioned = False
        if bot_username and f"@{bot_username}" in raw_text.lower():
            is_mentioned = True
            pattern = re.compile(rf"@{re.escape(bot_username)}\b", re.IGNORECASE)
            raw_text = pattern.sub("", raw_text).strip()

        # In groups, only respond if explicitly replying to or mentioning the bot
        if not is_reply_to_bot and not is_mentioned:
            return

    query = raw_text.strip()
    if not query:
        return

    await _execute_search(message, db_session, config, movie_service, query)


async def _execute_search(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
    query: str,
) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.get_or_create(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )

    session_service = SessionService(db_session, config)
    session = await session_service.create(
        user_id=user.id,
        chat_id=message.chat.id,
        query=query,
        message_id=message.message_id,
    )
    session_id_var.set(session.id)

    if message.chat.type in {"group", "supergroup"}:
        pending = await message.reply("🔍 Đang tìm kiếm, vui lòng chờ...")
    else:
        pending = await message.answer("🔍 Đang tìm kiếm, vui lòng chờ...")

    try:
        result = await movie_service.search(query, page=1)
    except KKPhimError as exc:
        logger.exception("Search failed query=%s", query)
        await pending.edit_text(
            f"❌ Không thể tìm kiếm ngay bây giờ.\n<i>{html.escape(str(exc))}</i>",
            parse_mode="HTML",
        )
        return

    if not result.items:
        await pending.edit_text(
            f'🔍 Không tìm thấy kết quả cho "<b>{html.escape(query)}</b>".\nThử từ khóa khác nhé.',
            parse_mode="HTML",
        )
        return

    text = _format_results_text(result, title=f'Kết quả cho "{html.escape(query)}"')
    keyboard = search_results_keyboard(
        session_id=session.id,
        items=result.items,
        current_page=result.pagination.current_page,
        total_pages=result.pagination.total_pages,
    )
    await pending.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


async def _execute_list(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
    list_type: str,
    title: str,
) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.get_or_create(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    session_service = SessionService(db_session, config)
    session = await session_service.create(
        user_id=user.id,
        chat_id=message.chat.id,
        query=f"list:{list_type}",
    )

    try:
        if list_type == "new":
            result = await movie_service.list_new(page=1)
        else:
            result = await movie_service.list_popular(page=1)
    except KKPhimError:
        await message.answer("❌ Không thể tải danh sách phim. Thử lại sau.")
        return

    text = _format_results_text(result, title=title)
    keyboard = search_results_keyboard(
        session_id=session.id,
        items=result.items,
        current_page=result.pagination.current_page,
        total_pages=result.pagination.total_pages,
    )
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


async def _execute_type_list(
    message: types.Message,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
    movie_type: str,
    title: str,
) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.get_or_create(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    session_service = SessionService(db_session, config)
    session = await session_service.create(
        user_id=user.id,
        chat_id=message.chat.id,
        query=f"type:{movie_type}",
    )

    try:
        result = await movie_service.list_by_type(movie_type, page=1)
    except KKPhimError:
        await message.answer("❌ Không thể tải danh sách phim. Thử lại sau.")
        return

    text = _format_results_text(result, title=title)
    keyboard = search_results_keyboard(
        session_id=session.id,
        items=result.items,
        current_page=result.pagination.current_page,
        total_pages=result.pagination.total_pages,
    )
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


def _format_results_text(result, *, title: str) -> str:
    page = result.pagination.current_page
    total_pages = result.pagination.total_pages
    per_page = result.pagination.items_per_page or 10
    start_idx = (page - 1) * per_page + 1

    page_info = f" (Trang {page}/{max(1, total_pages)})" if total_pages > 1 else ""
    lines = [f"<b>{title}</b>{page_info}\n"]

    for idx, item in enumerate(result.items, start=start_idx):
        line = f"<b>{idx}.</b> {html.escape(item.name)}"
        if item.publish_year:
            line += f" ({item.publish_year})"
        if item.quality:
            line += f" <code>[{item.quality}]</code>"
        if item.episode_current:
            line += f" - <i>{html.escape(item.episode_current)}</i>"
        lines.append(line)
    return "\n".join(lines)
