"""Callback query handlers with strict session authorization."""
from __future__ import annotations

import contextlib
import html
import re

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import (
    countries_keyboard,
    favorites_keyboard,
    genres_keyboard,
    home_keyboard,
    movie_detail_keyboard,
    search_prompt_keyboard,
    search_results_keyboard,
    watch_keyboard,
    years_keyboard,
)
from app.config import Config
from app.database.repositories import UserRepository
from app.logging_config import get_logger, session_id_var
from app.providers.kkphim.exceptions import KKPhimError
from app.providers.kkphim.models import Movie
from app.services.favorite_service import FavoriteService
from app.services.movie_service import MovieService
from app.services.session_service import SessionService

logger = get_logger(__name__)

callback_router = Router()


def _clean_html_text(raw_html: str | None) -> str:
    """Sanitize HTML text from API to prevent Telegram entity parsing errors."""
    if not raw_html:
        return ""
    # Replace <br>, <br/>, </p> with newlines
    text = re.sub(r"<(br|/p|/div)[^>]*>", "\n", raw_html, flags=re.IGNORECASE)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Unescape HTML entities (&amp;, &quot;, &nbsp;, etc.)
    text = html.unescape(text)
    # Collapse multiple whitespace
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


async def _authorize_session(
    callback: CallbackQuery,
    db_session: AsyncSession,
    config: Config,
    session_id: str,
) -> bool:
    """Verify callback belongs to the session owner in the correct chat."""
    if callback.message is None:
        await callback.answer("❌ Không xác định được message.", show_alert=True)
        return False

    session_service = SessionService(db_session, config)
    session = await session_service.authorize(
        session_id=session_id,
        telegram_user_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
    )

    if session is None:
        logger.warning(
            "Unauthorized callback user=%s chat=%s session=%s",
            callback.from_user.id,
            callback.message.chat.id,
            session_id,
        )
        await callback.answer(
            "🔒 Đây là kết quả tìm kiếm của người khác hoặc đã hết hạn.",
            show_alert=True,
        )
        return False

    session_id_var.set(session.id)
    await session_service.refresh_ttl(session_id)
    return True


@callback_router.callback_query(F.data == "menu:home")
async def on_home(callback: CallbackQuery) -> None:
    text = "🏠 <b>Trang chủ KKPhim</b>\n\nChọn danh mục bên dưới để khám phá phim:"
    await _edit_or_answer(callback, text, home_keyboard())


@callback_router.callback_query(F.data == "menu:close")
async def on_close(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.delete()
    await callback.answer()


@callback_router.callback_query(F.data == "noop")
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@callback_router.callback_query(F.data.startswith("menu:"))
async def on_menu(
    callback: CallbackQuery,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    parts = callback.data.split(":")
    action = parts[1]

    user_repo = UserRepository(db_session)
    user = await user_repo.get_or_create(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name,
    )
    session_service = SessionService(db_session, config)

    session = await session_service.create(
        user_id=user.id,
        chat_id=callback.message.chat.id if callback.message else 0,
    )

    if action == "search":
        await _edit_or_answer(
            callback,
            "🔍 <b>Tìm kiếm phim</b>\n\nHãy nhập tên phim hoặc từ khóa bạn muốn xem vào ô chat:",
            search_prompt_keyboard(session.id),
        )
        return

    if action == "new":
        await session_service.update_query(session.id, "list:new")
        await _show_list(callback, db_session, config, movie_service, session.id, "new")
    elif action == "popular":
        await session_service.update_query(session.id, "list:popular")
        await _show_list(callback, db_session, config, movie_service, session.id, "popular")
    elif action == "favorites":
        await _show_favorites(callback, db_session, config, session.id)
    elif action == "genres":
        page = int(parts[2]) if len(parts) > 2 else 1
        genres = await movie_service.get_genres()
        await _edit_or_answer(
            callback,
            "🎭 <b>Danh sách Thể loại:</b>",
            genres_keyboard(session.id, genres, page=page),
        )
    elif action == "countries":
        page = int(parts[2]) if len(parts) > 2 else 1
        countries = await movie_service.get_countries()
        await _edit_or_answer(
            callback,
            "🌍 <b>Danh sách Quốc gia:</b>",
            countries_keyboard(session.id, countries, page=page),
        )
    elif action == "years":
        page = int(parts[2]) if len(parts) > 2 else 1
        years = await movie_service.get_years()
        await _edit_or_answer(
            callback,
            "📅 <b>Năm phát hành:</b>",
            years_keyboard(session.id, years, page=page),
        )
    elif action == "type" and len(parts) > 2:
        movie_type = parts[2]
        await session_service.update_query(session.id, f"type:{movie_type}")
        await _show_list(callback, db_session, config, movie_service, session.id, "type", movie_type)
    else:
        await callback.answer("🚧 Chức năng đang cập nhật.", show_alert=True)


@callback_router.callback_query(F.data.startswith("genre:"))
async def on_genre_item(
    callback: CallbackQuery,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    parts = callback.data.split(":")
    genre_slug = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 1
    session_id = parts[3] if len(parts) > 3 else ""

    if not await _authorize_session(callback, db_session, config, session_id):
        return

    session_service = SessionService(db_session, config)
    await session_service.update_query(session_id, f"genre:{genre_slug}")
    await _show_list(callback, db_session, config, movie_service, session_id, "genre", genre_slug, page=page)


@callback_router.callback_query(F.data.startswith("country:"))
async def on_country_item(
    callback: CallbackQuery,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    parts = callback.data.split(":")
    country_slug = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 1
    session_id = parts[3] if len(parts) > 3 else ""

    if not await _authorize_session(callback, db_session, config, session_id):
        return

    session_service = SessionService(db_session, config)
    await session_service.update_query(session_id, f"country:{country_slug}")
    await _show_list(callback, db_session, config, movie_service, session_id, "country", country_slug, page=page)


@callback_router.callback_query(F.data.startswith("year:"))
async def on_year_item(
    callback: CallbackQuery,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    parts = callback.data.split(":")
    year = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 1
    session_id = parts[3] if len(parts) > 3 else ""

    if not await _authorize_session(callback, db_session, config, session_id):
        return

    session_service = SessionService(db_session, config)
    await session_service.update_query(session_id, f"year:{year}")
    await _show_list(callback, db_session, config, movie_service, session_id, "year", year, page=page)


@callback_router.callback_query(F.data.startswith("search:new:"))
async def on_search_new(callback: CallbackQuery, db_session: AsyncSession, config: Config) -> None:
    session_id = callback.data.split(":", 2)[2]
    if not await _authorize_session(callback, db_session, config, session_id):
        return

    await _edit_or_answer(
        callback,
        "🔍 Nhập tên phim hoặc từ khóa bạn muốn tìm:",
        search_prompt_keyboard(session_id),
    )


@callback_router.callback_query(F.data.startswith("page:"))
async def on_page(
    callback: CallbackQuery,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    _, page_str, session_id = callback.data.split(":", 2)
    if not await _authorize_session(callback, db_session, config, session_id):
        return

    page = int(page_str)
    session_service = SessionService(db_session, config)
    session = await session_service.get(session_id)
    if session is None or not session.query:
        await callback.answer("❌ Phiên tìm kiếm đã hết hạn.", show_alert=True)
        return

    await session_service.update_page(session_id, page)
    q = session.query
    if q.startswith("list:"):
        list_type = q.split(":", 1)[1]
        await _show_list(callback, db_session, config, movie_service, session_id, list_type, page=page)
    elif q.startswith("type:"):
        movie_type = q.split(":", 1)[1]
        await _show_list(callback, db_session, config, movie_service, session_id, "type", movie_type, page=page)
    elif q.startswith("genre:"):
        genre = q.split(":", 1)[1]
        await _show_list(callback, db_session, config, movie_service, session_id, "genre", genre, page=page)
    elif q.startswith("country:"):
        country = q.split(":", 1)[1]
        await _show_list(callback, db_session, config, movie_service, session_id, "country", country, page=page)
    elif q.startswith("year:"):
        year = q.split(":", 1)[1]
        await _show_list(callback, db_session, config, movie_service, session_id, "year", year, page=page)
    else:
        await _show_search_results(callback, db_session, config, movie_service, session_id, q, page=page)


@callback_router.callback_query(F.data.startswith("m:") | F.data.startswith("movie:"))
async def on_movie_detail(
    callback: CallbackQuery,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    parts = callback.data.split(":")
    identifier = parts[1]
    session_id = parts[2] if len(parts) > 2 else ""

    if not await _authorize_session(callback, db_session, config, session_id):
        return

    favorite_service = FavoriteService(db_session)
    session_service = SessionService(db_session, config)
    session = await session_service.get(session_id)
    if session is None:
        await callback.answer("❌ Phiên đã hết hạn.", show_alert=True)
        return

    slug: str | None = None
    if identifier == "detail":
        movie = await session_service.get_selected_movie(session)
        if movie:
            slug = movie.slug
    elif identifier.isdigit() and session.query:
        idx = int(identifier)
        page = session.current_page
        q = session.query
        try:
            if q.startswith("list:"):
                list_type = q.split(":", 1)[1]
                if list_type == "new":
                    res = await movie_service.list_new(page=page)
                else:
                    res = await movie_service.list_popular(page=page)
            elif q.startswith("type:"):
                res = await movie_service.list_by_type(q.split(":", 1)[1], page=page)
            elif q.startswith("genre:"):
                res = await movie_service.list_by_genre(q.split(":", 1)[1], page=page)
            elif q.startswith("country:"):
                res = await movie_service.list_by_country(q.split(":", 1)[1], page=page)
            elif q.startswith("year:"):
                res = await movie_service.list_by_year(q.split(":", 1)[1], page=page)
            else:
                res = await movie_service.search(q, page=page)

            if 0 <= idx < len(res.items):
                slug = res.items[idx].slug
        except KKPhimError:
            slug = None
    else:
        slug = identifier

    if not slug:
        await callback.answer("❌ Không tìm thấy thông tin phim.", show_alert=True)
        return

    try:
        movie = await movie_service.get_detail(slug)
    except KKPhimError:
        await callback.answer("❌ Không thể tải thông tin phim. Thử lại sau.", show_alert=True)
        return

    await session_service.set_selected_movie(session_id, movie)
    user_id = await _get_user_id(callback, db_session)
    is_fav = await favorite_service.is_favorite(user_id, slug)
    text = _format_movie_detail(movie)
    keyboard = movie_detail_keyboard(
        session_id=session_id,
        slug=slug,
        is_favorite=is_fav,
        has_servers=bool(movie.servers),
        trailer_url=movie.trailer_url,
    )
    await _edit_or_answer(callback, text, keyboard)


@callback_router.callback_query(F.data.startswith("w:") | F.data.startswith("watch:"))
async def on_watch(
    callback: CallbackQuery,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    parts = callback.data.split(":")
    action = parts[1]
    session_id = parts[-1]

    if not await _authorize_session(callback, db_session, config, session_id):
        return

    session_service = SessionService(db_session, config)
    session = await session_service.get(session_id)
    if session is None:
        await callback.answer("❌ Phiên đã hết hạn.", show_alert=True)
        return

    movie = await session_service.get_selected_movie(session)
    if not movie:
        await callback.answer("❌ Vui lòng chọn lại phim từ danh sách.", show_alert=True)
        return

    server_idx = 0
    ep_page = 1
    if action == "open" and len(parts) >= 5:
        server_idx = int(parts[2])
        ep_page = int(parts[3])
    elif action == "srv" and len(parts) >= 4:
        server_idx = int(parts[2])
    elif action == "ep" and len(parts) >= 4:
        ep_page = int(parts[2])

    if not movie.servers:
        await callback.answer("❌ Phim chưa có link xem.", show_alert=True)
        return

    text = (
        f"🎬 <b>{html.escape(movie.name)}</b>\n"
        f"<i>{html.escape(movie.origin_name or '')}</i>\n\n"
        f"🎞 Trạng thái: <b>{movie.episode_current or 'Đang cập nhật'}</b>\n"
        f"👇 Bấm vào tập bên dưới để mở player xem trực tiếp:"
    )
    await _edit_or_answer(
        callback,
        text,
        watch_keyboard(
            session_id=session_id,
            movie=movie,
            current_server_idx=server_idx,
            page=ep_page,
        ),
    )


@callback_router.callback_query(F.data.startswith("fav:"))
async def on_favorite(
    callback: CallbackQuery,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    parts = callback.data.split(":")
    action = parts[1]
    session_id = parts[-1]

    if not await _authorize_session(callback, db_session, config, session_id):
        return

    session_service = SessionService(db_session, config)
    session = await session_service.get(session_id)
    if session is None:
        await callback.answer("❌ Phiên đã hết hạn.", show_alert=True)
        return

    user_repo = UserRepository(db_session)
    user = await user_repo.get_or_create(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name,
    )
    favorite_service = FavoriteService(db_session)

    if action == "open" and len(parts) >= 4:
        slug = parts[2]
        try:
            movie = await movie_service.get_detail(slug)
        except KKPhimError:
            await callback.answer("❌ Không thể tải thông tin phim.", show_alert=True)
            return

        await session_service.set_selected_movie(session_id, movie)
        is_fav = await favorite_service.is_favorite(user.id, slug)
        text = _format_movie_detail(movie)
        keyboard = movie_detail_keyboard(
            session_id=session_id,
            slug=slug,
            is_favorite=is_fav,
            has_servers=bool(movie.servers),
            trailer_url=movie.trailer_url,
        )
        await _edit_or_answer(callback, text, keyboard)
        return

    # Toggle favorite for currently selected movie
    movie = await session_service.get_selected_movie(session)
    if not movie:
        await callback.answer("❌ Không tìm thấy phim để yêu thích.", show_alert=True)
        return

    if await favorite_service.is_favorite(user.id, movie.slug):
        await favorite_service.remove(user.id, movie.slug)
        await callback.answer("💔 Đã bỏ khỏi danh sách yêu thích.")
        is_fav = False
    else:
        await favorite_service.add(user.id, movie)
        await callback.answer("❤️ Đã thêm vào danh sách yêu thích!")
        is_fav = True

    # Refresh detail keyboard
    text = _format_movie_detail(movie)
    keyboard = movie_detail_keyboard(
        session_id=session_id,
        slug=movie.slug,
        is_favorite=is_fav,
        has_servers=bool(movie.servers),
        trailer_url=movie.trailer_url,
    )
    await _edit_or_answer(callback, text, keyboard)


@callback_router.callback_query(F.data.startswith("back:"))
async def on_back(
    callback: CallbackQuery,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
) -> None:
    session_id = callback.data.split(":", 1)[1]
    if not await _authorize_session(callback, db_session, config, session_id):
        return

    session_service = SessionService(db_session, config)
    session = await session_service.get(session_id)
    if session and session.query:
        q = session.query
        page = session.current_page
        if q.startswith("list:"):
            list_type = q.split(":", 1)[1]
            await _show_list(callback, db_session, config, movie_service, session_id, list_type, page=page)
        elif q.startswith("type:"):
            movie_type = q.split(":", 1)[1]
            await _show_list(callback, db_session, config, movie_service, session_id, "type", movie_type, page=page)
        elif q.startswith("genre:"):
            genre = q.split(":", 1)[1]
            await _show_list(callback, db_session, config, movie_service, session_id, "genre", genre, page=page)
        elif q.startswith("country:"):
            country = q.split(":", 1)[1]
            await _show_list(callback, db_session, config, movie_service, session_id, "country", country, page=page)
        elif q.startswith("year:"):
            year = q.split(":", 1)[1]
            await _show_list(callback, db_session, config, movie_service, session_id, "year", year, page=page)
        else:
            await _show_search_results(callback, db_session, config, movie_service, session_id, q, page=page)
    else:
        text = "🏠 <b>Trang chủ KKPhim</b>\n\nChọn danh mục bên dưới để khám phá phim:"
        await _edit_or_answer(callback, text, home_keyboard())


async def _show_list(
    callback: CallbackQuery,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
    session_id: str,
    list_type: str,
    value: str | None = None,
    page: int = 1,
) -> None:
    session_service = SessionService(db_session, config)

    type_names = {
        "phim-bo": "Phim bộ",
        "phim-le": "Phim lẻ",
        "hoat-hinh": "Phim hoạt hình",
        "tv-shows": "TV Shows",
        "phim-chieu-rap": "Phim chiếu rạp",
    }
    display_val = type_names.get(value, value) if value else ""

    title_map = {
        "new": "🆕 Phim mới cập nhật",
        "popular": "🔥 Phim chiếu rạp nổi bật",
        "type": f"📁 Danh sách {display_val}",
        "genre": f"🎭 Thể loại: {display_val}",
        "country": f"🌍 Quốc gia: {display_val}",
        "year": f"📅 Phim năm: {display_val}",
    }

    try:
        if list_type == "new":
            result = await movie_service.list_new(page=page)
        elif list_type == "popular":
            result = await movie_service.list_popular(page=page)
        elif list_type == "type" and value:
            result = await movie_service.list_by_type(value, page=page)
        elif list_type == "country" and value:
            result = await movie_service.list_by_country(value, page=page)
        elif list_type == "genre" and value:
            result = await movie_service.list_by_genre(value, page=page)
        elif list_type == "year" and value:
            result = await movie_service.list_by_year(value, page=page)
        else:
            await callback.answer("❌ Danh sách không hợp lệ.", show_alert=True)
            return
    except KKPhimError:
        await callback.answer("❌ Không thể tải danh sách. Thử lại sau.", show_alert=True)
        return

    if not result.items:
        await callback.answer("🔍 Không có phim nào trong mục này.", show_alert=True)
        return

    await session_service.update_page(session_id, page)
    title = title_map.get(list_type, "Danh sách phim")
    text = _format_results_text(result, title=title)
    keyboard = search_results_keyboard(
        session_id=session_id,
        items=result.items,
        current_page=result.pagination.current_page,
        total_pages=result.pagination.total_pages,
    )
    await _edit_or_answer(callback, text, keyboard)


async def _show_search_results(
    callback: CallbackQuery,
    db_session: AsyncSession,
    config: Config,
    movie_service: MovieService,
    session_id: str,
    query: str,
    page: int,
) -> None:
    session_service = SessionService(db_session, config)
    try:
        result = await movie_service.search(query, page=page)
    except KKPhimError:
        await callback.answer("❌ Tìm kiếm thất bại. Thử lại sau.", show_alert=True)
        return

    if not result.items:
        await callback.answer("🔍 Không tìm thấy kết quả nào.", show_alert=True)
        return

    await session_service.update_page(session_id, page)
    text = _format_results_text(result, title=f'🔍 Kết quả tìm kiếm cho: "{html.escape(query)}"')
    keyboard = search_results_keyboard(
        session_id=session_id,
        items=result.items,
        current_page=result.pagination.current_page,
        total_pages=result.pagination.total_pages,
    )
    await _edit_or_answer(callback, text, keyboard)


async def _show_favorites(
    callback: CallbackQuery,
    db_session: AsyncSession,
    config: Config,
    session_id: str,
) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.get_or_create(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name,
    )
    favorite_service = FavoriteService(db_session)
    favorites = await favorite_service.list(user.id)

    if not favorites:
        await _edit_or_answer(
            callback,
            "❤️ <b>Danh sách yêu thích trống</b>\n\nBạn chưa thêm bộ phim nào vào mục yêu thích.",
            home_keyboard(),
        )
        return

    await _edit_or_answer(
        callback,
        "❤️ <b>Danh sách phim yêu thích của bạn:</b>",
        favorites_keyboard(session_id, [(f[0], f[1]) if isinstance(f, tuple) else (f.movie_slug, f.movie_name) for f in favorites]),
    )


async def _get_user_id(callback: CallbackQuery, db_session: AsyncSession) -> int:
    user_repo = UserRepository(db_session)
    user = await user_repo.get_or_create(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name,
    )
    return user.id


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


def _format_movie_detail(movie: Movie) -> str:
    lines = []
    # If poster URL exists, embed invisible link for Telegram rich link preview
    if movie.poster_url or movie.thumb_url:
        img_url = movie.poster_url or movie.thumb_url
        lines.append(f'<a href="{img_url}">&#8205;</a>')

    lines.append(f"🎬 <b>{html.escape(movie.name)}</b>")
    if movie.origin_name:
        lines.append(f"<i>{html.escape(movie.origin_name)}</i>\n")

    meta_lines = []
    if movie.tmdb and movie.tmdb.vote_average:
        meta_lines.append(f"⭐ TMDB: <b>{movie.tmdb.vote_average:.1f}/10</b>")
    elif movie.imdb and movie.imdb.vote_average:
        meta_lines.append(f"⭐ IMDB: <b>{movie.imdb.vote_average:.1f}/10</b>")

    if movie.publish_year:
        meta_lines.append(f"📅 Năm: <b>{movie.publish_year}</b>")
    if movie.quality:
        meta_lines.append(f"🔹 Chất lượng: <b>{html.escape(movie.quality)}</b>")
    if movie.lang:
        meta_lines.append(f"🗣 Ngôn ngữ: <b>{html.escape(movie.lang)}</b>")
    if movie.time:
        meta_lines.append(f"⏱ Thời lượng: <b>{html.escape(movie.time)}</b>")
    if movie.episode_current:
        meta_lines.append(f"🎞 Trạng thái: <b>{html.escape(movie.episode_current)}</b>")
    if movie.genres:
        meta_lines.append(f"🎭 Thể loại: {html.escape(', '.join(movie.genres))}")
    if movie.countries:
        meta_lines.append(f"🌍 Quốc gia: {html.escape(', '.join(movie.countries))}")
    if movie.actors:
        meta_lines.append(f"👥 Diễn viên: {html.escape(', '.join(movie.actors[:5]))}")
    if movie.directors:
        meta_lines.append(f"🎬 Đạo diễn: {html.escape(', '.join(movie.directors[:3]))}")

    lines.extend(meta_lines)

    if movie.content:
        clean_desc = _clean_html_text(movie.content)
        if len(clean_desc) > 600:
            clean_desc = clean_desc[:597] + "..."
        lines.append(f"\n📝 <b>Nội dung:</b>\n{html.escape(clean_desc)}")

    return "\n".join(lines)


async def _edit_or_answer(
    callback: CallbackQuery,
    text: str,
    keyboard,
    parse_mode: str = "HTML",
) -> None:
    """Edit the existing message in private chat; in groups, reply with a new message."""
    if callback.message is None:
        await callback.answer("❌ Không xác định được message.", show_alert=True)
        return

    try:
        if callback.message.chat.type == "private":
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=parse_mode)
        else:
            await callback.message.reply(text, reply_markup=keyboard, parse_mode=parse_mode)
    except Exception as exc:
        logger.warning("Failed to edit or answer message: %s", exc)
    finally:
        with contextlib.suppress(Exception):
            await callback.answer()
