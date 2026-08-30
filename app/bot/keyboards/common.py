"""Common inline keyboard builders for Telegram UI."""
from __future__ import annotations

import math
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.providers.kkphim.models import CategoryItem, CountryItem, Movie, MovieSearchResult


def home_keyboard() -> InlineKeyboardMarkup:
    """Main menu keyboard."""
    buttons = [
        [InlineKeyboardButton(text="🔍 Tìm kiếm phim", callback_data="menu:search")],
        [
            InlineKeyboardButton(text="🆕 Phim mới", callback_data="menu:new"),
            InlineKeyboardButton(text="🔥 Phim chiếu rạp", callback_data="menu:type:phim-chieu-rap"),
        ],
        [
            InlineKeyboardButton(text="📺 Phim bộ", callback_data="menu:type:phim-bo"),
            InlineKeyboardButton(text="🎬 Phim lẻ", callback_data="menu:type:phim-le"),
        ],
        [
            InlineKeyboardButton(text="🧸 Hoạt hình", callback_data="menu:type:hoat-hinh"),
            InlineKeyboardButton(text="🌟 TV Shows", callback_data="menu:type:tv-shows"),
        ],
        [
            InlineKeyboardButton(text="🎭 Thể loại", callback_data="menu:genres:1"),
            InlineKeyboardButton(text="🌍 Quốc gia", callback_data="menu:countries:1"),
        ],
        [
            InlineKeyboardButton(text="📅 Năm phát hành", callback_data="menu:years:1"),
            InlineKeyboardButton(text="❤️ Yêu thích", callback_data="menu:favorites"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def search_prompt_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Keyboard shown when asking user to type a search query."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Tìm kiếm mới", callback_data=f"search:new:{session_id}")],
            [InlineKeyboardButton(text="🏠 Trang chủ", callback_data="menu:home")],
        ]
    )


def search_results_keyboard(
    session_id: str,
    items: list[MovieSearchResult],
    current_page: int,
    total_pages: int,
    per_page: int = 10,
) -> InlineKeyboardMarkup:
    """Keyboard for paginated search or list results."""
    rows: list[list[InlineKeyboardButton]] = []
    start_idx = (current_page - 1) * per_page + 1

    for i, item in enumerate(items):
        item_num = start_idx + i
        year_str = f" ({item.publish_year})" if item.publish_year else ""
        quality_str = f" [{item.quality}]" if item.quality else ""
        label = f"{item_num}. {item.name}{year_str}{quality_str}"
        # Truncate label if too long for Telegram button
        if len(label) > 40:
            label = label[:37] + "..."
        # Pass index i (0..9) for 100% safety under Telegram 64-byte callback limit
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"m:{i}:{session_id}")]
        )

    # Navigation row
    nav_row: list[InlineKeyboardButton] = []
    if current_page > 1:
        nav_row.append(
            InlineKeyboardButton(text="◀️ Trước", callback_data=f"page:{current_page - 1}:{session_id}")
        )
    nav_row.append(
        InlineKeyboardButton(text=f"Trang {current_page}/{max(1, total_pages)}", callback_data="noop")
    )
    if current_page < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="Sau ▶️", callback_data=f"page:{current_page + 1}:{session_id}")
        )
    if nav_row:
        rows.append(nav_row)

    rows.append(
        [
            InlineKeyboardButton(text="🔍 Tìm phim khác", callback_data=f"search:new:{session_id}"),
            InlineKeyboardButton(text="🏠 Trang chủ", callback_data="menu:home"),
            InlineKeyboardButton(text="❌ Đóng", callback_data="menu:close"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def movie_detail_keyboard(
    session_id: str,
    slug: str,
    is_favorite: bool,
    has_servers: bool,
    trailer_url: str | None = None,
) -> InlineKeyboardMarkup:
    """Keyboard for movie detail view."""
    rows: list[list[InlineKeyboardButton]] = []

    if has_servers:
        rows.append(
            [InlineKeyboardButton(text="▶️ Xem phim ngay", callback_data=f"w:open:0:1:{session_id}")]
        )

    if trailer_url and trailer_url.startswith("http"):
        rows.append(
            [InlineKeyboardButton(text="🎬 Xem Trailer (YouTube)", url=trailer_url)]
        )

    fav_label = "💔 Bỏ yêu thích" if is_favorite else "❤️ Thêm vào yêu thích"
    rows.append(
        [
            InlineKeyboardButton(text=fav_label, callback_data=f"fav:toggle:{session_id}"),
            InlineKeyboardButton(text="🔗 Chia sẻ", switch_inline_query=slug),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="◀️ Quay lại", callback_data=f"back:{session_id}"),
            InlineKeyboardButton(text="🏠 Trang chủ", callback_data="menu:home"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def watch_keyboard(
    session_id: str,
    movie: Movie,
    current_server_idx: int = 0,
    page: int = 1,
    per_page: int = 24,
) -> InlineKeyboardMarkup:
    """Keyboard listing available servers and playable episode buttons."""
    rows: list[list[InlineKeyboardButton]] = []

    # If multiple servers exist, show server selector tabs
    if len(movie.servers) > 1:
        server_row: list[InlineKeyboardButton] = []
        for idx, server in enumerate(movie.servers):
            prefix = "🔘 " if idx == current_server_idx else "⚪️ "
            server_name = server.name or f"Server #{idx + 1}"
            server_row.append(
                InlineKeyboardButton(
                    text=f"{prefix}{server_name}",
                    callback_data=f"w:srv:{idx}:{session_id}",
                )
            )
            if len(server_row) == 2:
                rows.append(server_row)
                server_row = []
        if server_row:
            rows.append(server_row)

    # Get active server
    if 0 <= current_server_idx < len(movie.servers):
        active_server = movie.servers[current_server_idx]
    elif movie.servers:
        active_server = movie.servers[0]
        current_server_idx = 0
    else:
        active_server = None

    if active_server and active_server.episodes:
        all_eps = active_server.episodes
        total_eps = len(all_eps)
        total_pages = max(1, math.ceil(total_eps / per_page))
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * per_page
        page_eps = all_eps[start_idx : start_idx + per_page]

        # Arrange episode buttons in rows of 4
        ep_row: list[InlineKeyboardButton] = []
        for ep in page_eps:
            ep_url = str(ep.link_embed or ep.link_m3u8 or "https://phimapi.com")
            ep_label = ep.name if ep.name else "Xem"
            ep_row.append(InlineKeyboardButton(text=ep_label, url=ep_url))
            if len(ep_row) == 4:
                rows.append(ep_row)
                ep_row = []
        if ep_row:
            rows.append(ep_row)

        # Pagination row for episodes if more than 1 page
        if total_pages > 1:
            nav_row: list[InlineKeyboardButton] = []
            if page > 1:
                nav_row.append(
                    InlineKeyboardButton(
                        text="◀️ Tập trước",
                        callback_data=f"w:ep:{page - 1}:{session_id}",
                    )
                )
            nav_row.append(
                InlineKeyboardButton(
                    text=f"Trang {page}/{total_pages}",
                    callback_data="noop",
                )
            )
            if page < total_pages:
                nav_row.append(
                    InlineKeyboardButton(
                        text="Tập sau ▶️",
                        callback_data=f"w:ep:{page + 1}:{session_id}",
                    )
                )
            rows.append(nav_row)

    rows.append(
        [
            InlineKeyboardButton(text="◀️ Quay lại thông tin", callback_data=f"m:detail:{session_id}"),
            InlineKeyboardButton(text="🏠 Trang chủ", callback_data="menu:home"),
            InlineKeyboardButton(text="❌ Đóng", callback_data="menu:close"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def genres_keyboard(
    session_id: str,
    genres: list[CategoryItem],
    page: int = 1,
    per_page: int = 12,
) -> InlineKeyboardMarkup:
    """Dynamic keyboard displaying available movie genres from API."""
    rows: list[list[InlineKeyboardButton]] = []
    total_pages = max(1, math.ceil(len(genres) / per_page))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    page_items = genres[start_idx : start_idx + per_page]

    row: list[InlineKeyboardButton] = []
    for g in page_items:
        row.append(
            InlineKeyboardButton(
                text=f"🎭 {g.name}",
                callback_data=f"genre:{g.slug}:1:{session_id}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"menu:genres:{page - 1}:{session_id}"))
        nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"menu:genres:{page + 1}:{session_id}"))
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🏠 Trang chủ", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def countries_keyboard(
    session_id: str,
    countries: list[CountryItem],
    page: int = 1,
    per_page: int = 12,
) -> InlineKeyboardMarkup:
    """Dynamic keyboard displaying available countries from API."""
    rows: list[list[InlineKeyboardButton]] = []
    total_pages = max(1, math.ceil(len(countries) / per_page))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    page_items = countries[start_idx : start_idx + per_page]

    row: list[InlineKeyboardButton] = []
    for c in page_items:
        row.append(
            InlineKeyboardButton(
                text=f"🌍 {c.name}",
                callback_data=f"country:{c.slug}:1:{session_id}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"menu:countries:{page - 1}:{session_id}"))
        nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"menu:countries:{page + 1}:{session_id}"))
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🏠 Trang chủ", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def years_keyboard(
    session_id: str,
    years: list[int],
    page: int = 1,
    per_page: int = 12,
) -> InlineKeyboardMarkup:
    """Dynamic keyboard displaying release years from API."""
    rows: list[list[InlineKeyboardButton]] = []
    total_pages = max(1, math.ceil(len(years) / per_page))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    page_items = years[start_idx : start_idx + per_page]

    row: list[InlineKeyboardButton] = []
    for y in page_items:
        row.append(
            InlineKeyboardButton(
                text=f"{y}",
                callback_data=f"year:{y}:1:{session_id}",
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"menu:years:{page - 1}:{session_id}"))
        nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"menu:years:{page + 1}:{session_id}"))
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🏠 Trang chủ", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def favorites_keyboard(
    session_id: str,
    favorites: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    """Keyboard for favorite movies list."""
    rows: list[list[InlineKeyboardButton]] = []
    for slug, name in favorites:
        label = f"❤️ {name}"
        if len(label) > 40:
            label = label[:37] + "..."
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"fav:open:{slug}:{session_id}")]
        )

    rows.append(
        [
            InlineKeyboardButton(text="🏠 Trang chủ", callback_data="menu:home"),
            InlineKeyboardButton(text="❌ Đóng", callback_data="menu:close"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
