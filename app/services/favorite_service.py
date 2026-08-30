"""Favorite movies business logic."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories import FavoriteRepository
from app.providers.kkphim.models import Movie, MovieSearchResult


class FavoriteService:
    """Manage user favorite movies."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.repo = FavoriteRepository(db_session)

    async def add(self, user_id: int, movie: Movie | MovieSearchResult) -> None:
        await self.repo.add(user_id, movie.slug, movie.name)

    async def remove(self, user_id: int, movie_slug: str) -> bool:
        return await self.repo.remove(user_id, movie_slug)

    async def list(self, user_id: int) -> list[tuple[str, str]]:
        favorites = await self.repo.list_by_user(user_id)
        return [(f.movie_slug, f.movie_name) for f in favorites]

    async def is_favorite(self, user_id: int, movie_slug: str) -> bool:
        return await self.repo.is_favorite(user_id, movie_slug)
