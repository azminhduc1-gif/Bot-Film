"""Async KKPhim API client with retry, timeout, and normalized models.

Implements the official KKPhim API:
https://kkphim2.com/api-document (Base URL: https://phimapi.com)
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp
from yarl import URL

from app.config import Config
from app.logging_config import get_logger, request_id_var
from app.providers.kkphim.exceptions import (
    KKPhimAPIError,
    KKPhimError,
    KKPhimNotFoundError,
    KKPhimTimeoutError,
    KKPhimValidationError,
)
from app.providers.kkphim.models import (
    CategoryItem,
    CountryItem,
    Movie,
    MovieSearchResult,
    MovieServer,
    PaginatedResult,
    Pagination,
)

logger = get_logger(__name__)

# Type aliases mapping for user-friendly slugs
TYPE_MAPPING = {
    "series": "phim-bo",
    "single": "phim-le",
    "movie": "phim-le",
    "tv": "phim-bo",
    "theater": "phim-chieu-rap",
    "cinema": "phim-chieu-rap",
    "cartoon": "hoat-hinh",
    "anime": "hoat-hinh",
}


def resolve_image_url(url: str | None, path_image: str | None = None) -> str | None:
    """Convert relative image path from KKPhim into full accessible URL."""
    if not url:
        return None
    url = str(url).strip()
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if path_image:
        return f"{path_image.rstrip('/')}/{url.lstrip('/')}"
    if url.startswith("upload/") or url.startswith("/upload/"):
        return f"https://phimimg.com/{url.lstrip('/')}"
    if url.startswith("uploads/") or url.startswith("/uploads/"):
        return f"https://phimapi.com/{url.lstrip('/')}"
    return f"https://phimimg.com/upload/vod/{url.lstrip('/')}"


class KKPhimClient:
    """Production-grade async client for the KKPhim API."""

    def __init__(self, config: Config, session: aiohttp.ClientSession | None = None) -> None:
        self.config = config
        self.base_url = URL(config.kkphim_base_url)
        self.api_key = config.kkphim_api_key
        self.timeout = aiohttp.ClientTimeout(total=config.request_timeout_seconds)
        self.max_retries = config.max_retries
        self.retry_backoff = config.retry_backoff_seconds
        self._owned_session = session is None
        self.session = session or aiohttp.ClientSession(timeout=self.timeout)

    async def close(self) -> None:
        """Close the underlying HTTP session if owned by this client."""
        if self._owned_session and self.session:
            await self.session.close()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "KKPhimTelegramBot/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an HTTP request with retries and structured logging."""
        clean_path = path.lstrip("/")
        url = self.base_url / clean_path
        req_id = request_id_var.get() or "-"
        last_exception: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "KKPhim request attempt=%d method=%s url=%s req=%s",
                    attempt,
                    method,
                    str(url),
                    req_id,
                )
                async with self.session.request(
                    method, str(url), headers=self._headers(), **kwargs
                ) as response:
                    body = await response.text()
                    logger.debug(
                        "KKPhim response status=%s len=%s req=%s",
                        response.status,
                        len(body),
                        req_id,
                    )

                    if response.status == 404:
                        raise KKPhimNotFoundError(f"Resource not found at {path}", status_code=404)

                    if response.status >= 500:
                        raise KKPhimAPIError(
                            f"Server error {response.status}", status_code=response.status
                        )

                    if response.status >= 400:
                        raise KKPhimAPIError(
                            f"Client error {response.status}", status_code=response.status
                        )

                    try:
                        return json.loads(body)
                    except json.JSONDecodeError as exc:
                        raise KKPhimValidationError("Invalid JSON response") from exc

            except asyncio.TimeoutError as exc:
                last_exception = exc
                logger.warning("KKPhim timeout attempt=%d req=%s", attempt, req_id)
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_backoff * attempt)
                else:
                    raise KKPhimTimeoutError("KKPhim request timed out") from exc

            except KKPhimNotFoundError:
                raise

            except (KKPhimAPIError, aiohttp.ClientError) as exc:
                last_exception = exc
                logger.warning(
                    "KKPhim request failed attempt=%d error=%s req=%s",
                    attempt,
                    str(exc),
                    req_id,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_backoff * attempt)
                else:
                    raise KKPhimAPIError(str(exc)) from exc

        raise KKPhimError(f"Request failed after {self.max_retries} attempts") from last_exception

    async def search_movie(
        self,
        query: str,
        page: int = 1,
        limit: int = 10,
        category: str | None = None,
        country: str | None = None,
        year: int | str | None = None,
        sort_field: str | None = None,
        sort_type: str | None = None,
        sort_lang: str | None = None,
    ) -> PaginatedResult:
        """Search movies by keyword using /v1/api/tim-kiem."""
        params: dict[str, str] = {
            "keyword": query,
            "page": str(page),
            "limit": str(limit),
        }
        if category:
            params["category"] = category
        if country:
            params["country"] = country
        if year:
            params["year"] = str(year)
        if sort_field:
            params["sort_field"] = sort_field
        if sort_type:
            params["sort_type"] = sort_type
        if sort_lang:
            params["sort_lang"] = sort_lang

        try:
            data = await self._request("GET", "/v1/api/tim-kiem", params=params)
        except KKPhimNotFoundError:
            return PaginatedResult()

        return self._normalize_paginated(data, page=page, limit=limit)

    async def get_movie(self, slug: str) -> Movie:
        """Fetch full movie details with streaming episodes by slug using /phim/{slug}."""
        data = await self._request("GET", f"/phim/{slug}")
        return self._normalize_movie(data)

    async def get_movie_by_id(self, movie_id: str) -> Movie:
        """Fetch full movie details by database _id using /phim/id/{id}."""
        data = await self._request("GET", f"/phim/id/{movie_id}")
        return self._normalize_movie(data)

    async def get_movie_by_tmdb(self, tmdb_type: str, tmdb_id: str | int) -> Movie:
        """Fetch full movie details by TMDB ID using /tmdb/{type}/{id}."""
        data = await self._request("GET", f"/tmdb/{tmdb_type}/{tmdb_id}")
        return self._normalize_movie(data)

    async def get_movie_by_imdb(self, imdb_id: str) -> Movie:
        """Fetch full movie details by IMDB ID using /imdb/title/{id}."""
        data = await self._request("GET", f"/imdb/title/{imdb_id}")
        return self._normalize_movie(data)

    async def list_new_movies(self, page: int = 1, limit: int = 10) -> PaginatedResult:
        """List newly updated movies using /v1/api/danh-sach or /danh-sach/phim-moi-cap-nhat."""
        params = {"page": str(page), "limit": str(limit)}
        try:
            data = await self._request("GET", "/v1/api/danh-sach", params=params)
        except KKPhimAPIError:
            data = await self._request("GET", "/danh-sach/phim-moi-cap-nhat", params=params)
        return self._normalize_paginated(data, page=page, limit=limit)

    async def list_popular_movies(self, page: int = 1, limit: int = 10) -> PaginatedResult:
        """List popular/cinema movies."""
        return await self.list_movies_by_type("phim-chieu-rap", page=page, limit=limit)

    async def list_movies_by_type(
        self,
        movie_type: str,
        page: int = 1,
        limit: int = 10,
        category: str | None = None,
        country: str | None = None,
        year: int | str | None = None,
    ) -> PaginatedResult:
        """List movies by category type (phim-bo, phim-le, hoat-hinh, tv-shows, phim-chieu-rap)."""
        actual_type = TYPE_MAPPING.get(movie_type, movie_type)
        params: dict[str, str] = {"page": str(page), "limit": str(limit)}
        if category:
            params["category"] = category
        if country:
            params["country"] = country
        if year:
            params["year"] = str(year)

        data = await self._request("GET", f"/v1/api/danh-sach/{actual_type}", params=params)
        return self._normalize_paginated(data, page=page, limit=limit)

    async def list_genres(self) -> list[CategoryItem]:
        """Fetch all movie genres/categories using /the-loai."""
        data = await self._request("GET", "/the-loai")
        items = data.get("data", {}).get("items") or data.get("items") or []
        return [CategoryItem(**item) for item in items]

    async def list_movies_by_genre(
        self,
        genre_slug: str,
        page: int = 1,
        limit: int = 10,
        country: str | None = None,
        year: int | str | None = None,
    ) -> PaginatedResult:
        """List movies belonging to a genre using /v1/api/the-loai/{slug}."""
        params: dict[str, str] = {"page": str(page), "limit": str(limit)}
        if country:
            params["country"] = country
        if year:
            params["year"] = str(year)

        data = await self._request("GET", f"/v1/api/the-loai/{genre_slug}", params=params)
        return self._normalize_paginated(data, page=page, limit=limit)

    async def list_countries(self) -> list[CountryItem]:
        """Fetch all countries using /quoc-gia."""
        data = await self._request("GET", "/quoc-gia")
        items = data.get("data", {}).get("items") or data.get("items") or []
        return [CountryItem(**item) for item in items]

    async def list_movies_by_country(
        self,
        country_slug: str,
        page: int = 1,
        limit: int = 10,
        category: str | None = None,
        year: int | str | None = None,
    ) -> PaginatedResult:
        """List movies belonging to a country using /v1/api/quoc-gia/{slug}."""
        params: dict[str, str] = {"page": str(page), "limit": str(limit)}
        if category:
            params["category"] = category
        if year:
            params["year"] = str(year)

        data = await self._request("GET", f"/v1/api/quoc-gia/{country_slug}", params=params)
        return self._normalize_paginated(data, page=page, limit=limit)

    async def list_years(self) -> list[int]:
        """Fetch all release years using /nam-phat-hanh."""
        data = await self._request("GET", "/nam-phat-hanh")
        items = data.get("data", {}).get("items") or data.get("items") or []
        years: list[int] = []
        for item in items:
            if isinstance(item, dict) and "year" in item:
                years.append(int(item["year"]))
            elif isinstance(item, (int, str)):
                years.append(int(item))
        return years

    async def list_movies_by_year(
        self,
        year: int | str,
        page: int = 1,
        limit: int = 10,
        category: str | None = None,
        country: str | None = None,
    ) -> PaginatedResult:
        """List movies by release year using /v1/api/nam/{year}."""
        params: dict[str, str] = {"page": str(page), "limit": str(limit)}
        if category:
            params["category"] = category
        if country:
            params["country"] = country

        data = await self._request("GET", f"/v1/api/nam/{year}", params=params)
        return self._normalize_paginated(data, page=page, limit=limit)

    async def get_movie_images(self, slug: str) -> dict[str, Any]:
        """Get movie backdrop and poster images using /v1/api/phim/{slug}/images."""
        data = await self._request("GET", f"/v1/api/phim/{slug}/images")
        return data.get("data") or data

    async def get_movie_peoples(self, slug: str) -> dict[str, Any]:
        """Get movie cast and crew using /v1/api/phim/{slug}/peoples."""
        data = await self._request("GET", f"/v1/api/phim/{slug}/peoples")
        return data.get("data") or data

    async def get_movie_keywords(self, slug: str) -> list[str]:
        """Get movie keywords using /v1/api/phim/{slug}/keywords."""
        data = await self._request("GET", f"/v1/api/phim/{slug}/keywords")
        keywords_data = data.get("data", {}).get("keywords") or data.get("keywords") or []
        return [k.get("name", "") if isinstance(k, dict) else str(k) for k in keywords_data]

    def _normalize_movie(self, data: dict[str, Any]) -> Movie:
        """Normalize raw movie JSON into Movie model with resolved image URLs."""
        # Format 1: { "status": true, "movie": {...}, "episodes": [...] }
        movie_dict: dict[str, Any] = {}
        episodes_list: list[Any] = []

        if "movie" in data and isinstance(data["movie"], dict):
            movie_dict = dict(data["movie"])
            episodes_list = data.get("episodes") or []
        # Format 2: { "status": "success", "data": { "item": {..., "episodes": [...]} } }
        elif "data" in data and isinstance(data["data"], dict) and "item" in data["data"]:
            item = dict(data["data"]["item"])
            episodes_list = item.pop("episodes", []) or []
            movie_dict = item
        # Root dict
        else:
            movie_dict = dict(data)
            episodes_list = movie_dict.pop("episodes", []) or movie_dict.pop("servers", []) or []

        # Resolve image URLs
        if "thumb_url" in movie_dict:
            movie_dict["thumb_url"] = resolve_image_url(movie_dict.get("thumb_url"))
        if "poster_url" in movie_dict:
            movie_dict["poster_url"] = resolve_image_url(movie_dict.get("poster_url"))

        # Parse servers/episodes
        servers: list[MovieServer] = []
        for ep_entry in episodes_list:
            if isinstance(ep_entry, dict):
                servers.append(MovieServer(**ep_entry))

        movie_dict["servers"] = servers
        return Movie(**movie_dict)

    def _normalize_paginated(
        self, data: dict[str, Any], *, page: int, limit: int
    ) -> PaginatedResult:
        """Normalize paginated responses across different KKPhim endpoint formats."""
        path_image = data.get("pathImage")

        # Format 1: v1 { "status": "success", "data": { "items": [...], "params": { "pagination": {...} } } }
        if "data" in data and isinstance(data["data"], dict) and "items" in data["data"]:
            d = data["data"]
            items_data = d.get("items") or []
            p_data = d.get("params", {}).get("pagination") or d.get("pagination") or {}
            total_items = p_data.get("totalItems") or p_data.get("total_items") or len(items_data)
            items_per_page = p_data.get("totalItemsPerPage") or p_data.get("items_per_page") or limit
            current_page = p_data.get("currentPage") or p_data.get("current_page") or page
            total_pages = p_data.get("totalPages") or max(1, (total_items + items_per_page - 1) // items_per_page)
        # Format 2: classic { "status": true, "items": [...], "pagination": {...} }
        else:
            items_data = data.get("items") or data.get("movies") or []
            p_data = data.get("pagination") or {}
            total_items = p_data.get("totalItems") or data.get("total") or len(items_data)
            items_per_page = p_data.get("totalItemsPerPage") or limit
            current_page = p_data.get("currentPage") or page
            total_pages = p_data.get("totalPages") or max(1, (total_items + items_per_page - 1) // items_per_page)

        normalized_items: list[MovieSearchResult] = []
        for item in items_data:
            if isinstance(item, dict):
                item_copy = dict(item)
                item_copy["thumb_url"] = resolve_image_url(item_copy.get("thumb_url"), path_image)
                item_copy["poster_url"] = resolve_image_url(item_copy.get("poster_url"), path_image)
                normalized_items.append(MovieSearchResult(**item_copy))

        return PaginatedResult(
            items=normalized_items,
            pagination=Pagination(
                current_page=current_page,
                total_pages=total_pages,
                total_items=total_items,
                items_per_page=items_per_page,
            ),
        )
