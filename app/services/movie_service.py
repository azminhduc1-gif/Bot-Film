"""Movie search and listing service with caching and normalization."""
from __future__ import annotations

from typing import Any

from app.config import Config
from app.logging_config import get_logger
from app.providers.kkphim.client import KKPhimClient
from app.providers.kkphim.models import (
    CategoryItem,
    CountryItem,
    Movie,
    PaginatedResult,
)
from app.services.cache_service import CacheService

logger = get_logger(__name__)


class MovieService:
    """High-level service for movie operations with robust caching."""

    def __init__(self, client: KKPhimClient, cache: CacheService, config: Config) -> None:
        self.client = client
        self.cache = cache
        self.config = config

    async def search(
        self,
        query: str,
        page: int = 1,
        limit: int = 10,
        category: str | None = None,
        country: str | None = None,
        year: int | str | None = None,
    ) -> PaginatedResult:
        normalized = self._normalize_query(query)
        cache_key = (normalized, str(page), str(limit), str(category or ""), str(country or ""), str(year or ""))
        cached = await self.cache.get("search", *cache_key)
        if cached is not None:
            logger.debug("Cache hit search query=%s page=%s", normalized, page)
            return PaginatedResult(**cached)

        logger.info("Searching KKPhim query=%s page=%s", normalized, page)
        result = await self.client.search_movie(
            normalized,
            page=page,
            limit=limit,
            category=category,
            country=country,
            year=year,
        )

        await self.cache.set(
            value=result.model_dump(mode="json"),
            namespace="search",
            parts=cache_key,
        )
        return result

    async def get_detail(self, slug: str) -> Movie:
        cached = await self.cache.get("movie", slug)
        if cached is not None:
            return Movie(**cached)

        movie = await self.client.get_movie(slug)
        await self.cache.set(
            value=movie.model_dump(mode="json"),
            namespace="movie",
            parts=(slug,),
        )
        return movie

    async def get_by_id(self, movie_id: str) -> Movie:
        cached = await self.cache.get("movie_id", movie_id)
        if cached is not None:
            return Movie(**cached)

        movie = await self.client.get_movie_by_id(movie_id)
        await self.cache.set(
            value=movie.model_dump(mode="json"),
            namespace="movie_id",
            parts=(movie_id,),
        )
        return movie

    async def list_new(self, page: int = 1, limit: int = 10) -> PaginatedResult:
        return await self._cached_list("new", self.client.list_new_movies, page, limit)

    async def list_popular(self, page: int = 1, limit: int = 10) -> PaginatedResult:
        return await self._cached_list("popular", self.client.list_popular_movies, page, limit)

    async def list_by_type(
        self,
        movie_type: str,
        page: int = 1,
        limit: int = 10,
        category: str | None = None,
        country: str | None = None,
        year: int | str | None = None,
    ) -> PaginatedResult:
        return await self._cached_list(
            f"type:{movie_type}:{category or ''}:{country or ''}:{year or ''}",
            self.client.list_movies_by_type,
            movie_type,
            page,
            limit,
            category,
            country,
            year,
        )

    async def list_by_country(
        self,
        country: str,
        page: int = 1,
        limit: int = 10,
        category: str | None = None,
        year: int | str | None = None,
    ) -> PaginatedResult:
        return await self._cached_list(
            f"country:{country}:{category or ''}:{year or ''}",
            self.client.list_movies_by_country,
            country,
            page,
            limit,
            category,
            year,
        )

    async def list_by_genre(
        self,
        genre: str,
        page: int = 1,
        limit: int = 10,
        country: str | None = None,
        year: int | str | None = None,
    ) -> PaginatedResult:
        return await self._cached_list(
            f"genre:{genre}:{country or ''}:{year or ''}",
            self.client.list_movies_by_genre,
            genre,
            page,
            limit,
            country,
            year,
        )

    async def list_by_year(
        self,
        year: int | str,
        page: int = 1,
        limit: int = 10,
        category: str | None = None,
        country: str | None = None,
    ) -> PaginatedResult:
        return await self._cached_list(
            f"year:{year}:{category or ''}:{country or ''}",
            self.client.list_movies_by_year,
            year,
            page,
            limit,
            category,
            country,
        )

    async def get_genres(self) -> list[CategoryItem]:
        cached = await self.cache.get("meta", "genres")
        if cached is not None and isinstance(cached, list):
            return [CategoryItem(**item) for item in cached]

        genres = await self.client.list_genres()
        await self.cache.set(
            value=[g.model_dump(mode="json") for g in genres],
            namespace="meta",
            parts=("genres",),
            ttl=3600,  # Cache metadata for 1 hour
        )
        return genres

    async def get_countries(self) -> list[CountryItem]:
        cached = await self.cache.get("meta", "countries")
        if cached is not None and isinstance(cached, list):
            return [CountryItem(**item) for item in cached]

        countries = await self.client.list_countries()
        await self.cache.set(
            value=[c.model_dump(mode="json") for c in countries],
            namespace="meta",
            parts=("countries",),
            ttl=3600,
        )
        return countries

    async def get_years(self) -> list[int]:
        cached = await self.cache.get("meta", "years")
        if cached is not None and isinstance(cached, list):
            return cached

        years = await self.client.list_years()
        if not years:
            years = list(range(2026, 2010, -1))

        await self.cache.set(
            value=years,
            namespace="meta",
            parts=("years",),
            ttl=3600,
        )
        return years

    async def get_peoples(self, slug: str) -> dict[str, Any]:
        return await self.client.get_movie_peoples(slug)

    async def get_images(self, slug: str) -> dict[str, Any]:
        return await self.client.get_movie_images(slug)

    async def _cached_list(
        self,
        namespace: str,
        fetcher: Any,
        *args: Any,
    ) -> PaginatedResult:
        clean_args = [str(a) if a is not None else "" for a in args]
        cache_key = namespace.replace(":", "_") + "_" + "_".join(clean_args)
        cached = await self.cache.get("list", cache_key)
        if cached is not None:
            return PaginatedResult(**cached)

        result = await fetcher(*args)
        await self.cache.set(
            value=result.model_dump(mode="json"),
            namespace="list",
            parts=(cache_key,),
        )
        return result

    @staticmethod
    def _normalize_query(query: str) -> str:
        return " ".join(query.strip().lower().split())
