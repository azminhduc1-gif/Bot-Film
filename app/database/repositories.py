"""Repository layer for database operations."""
from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database.models import Favorite, Session, User


class UserRepository:
    """Repository for user CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self, telegram_user_id: int, username: str | None, first_name: str | None
    ) -> User:
        stmt = select(User).where(User.telegram_user_id == telegram_user_id)
        result = await self.session.execute(stmt)
        user = result.unique().scalar_one_or_none()

        if user is None:
            user = User(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
            )
            self.session.add(user)
            await self.session.flush()
        else:
            user.username = username
            user.first_name = first_name
            user.last_seen_at = dt.datetime.utcnow()

        return user

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        stmt = select(User).where(User.telegram_user_id == telegram_user_id)
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()


class SessionRepository:
    """Repository for session CRUD and ownership checks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        session_id: str,
        user_id: int,
        chat_id: int,
        query: str | None = None,
        current_page: int = 1,
        message_id: int | None = None,
        expires_at: dt.datetime | None = None,
    ) -> Session:
        if expires_at is None:
            expires_at = dt.datetime.utcnow() + dt.timedelta(minutes=30)

        db_session = Session(
            id=session_id,
            user_id=user_id,
            chat_id=chat_id,
            query=query,
            current_page=current_page,
            message_id=message_id,
            expires_at=expires_at,
        )
        self.session.add(db_session)
        await self.session.flush()
        return db_session

    async def get_by_id(self, session_id: str) -> Session | None:
        stmt = select(Session).where(Session.id == session_id).options(
            joinedload(Session.user)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def update(self, session_id: str, **kwargs: object) -> None:
        stmt = update(Session).where(Session.id == session_id).values(**kwargs)
        await self.session.execute(stmt)

    async def delete(self, session_id: str) -> None:
        stmt = delete(Session).where(Session.id == session_id)
        await self.session.execute(stmt)

    async def delete_expired(self) -> int:
        stmt = delete(Session).where(Session.expires_at < dt.datetime.utcnow())
        result = await self.session.execute(stmt)
        return result.rowcount or 0

    async def list_active_by_user(self, telegram_user_id: int) -> Sequence[Session]:
        stmt = (
            select(Session)
            .join(User)
            .where(
                User.telegram_user_id == telegram_user_id,
                Session.expires_at >= dt.datetime.utcnow(),
            )
        )
        result = await self.session.execute(stmt)
        return result.unique().scalars().all()


class FavoriteRepository:
    """Repository for favorite movies."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, user_id: int, movie_slug: str, movie_name: str) -> Favorite:
        stmt = select(Favorite).where(
            Favorite.user_id == user_id, Favorite.movie_slug == movie_slug
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        favorite = Favorite(user_id=user_id, movie_slug=movie_slug, movie_name=movie_name)
        self.session.add(favorite)
        await self.session.flush()
        return favorite

    async def remove(self, user_id: int, movie_slug: str) -> bool:
        stmt = delete(Favorite).where(
            Favorite.user_id == user_id, Favorite.movie_slug == movie_slug
        )
        result = await self.session.execute(stmt)
        return (result.rowcount or 0) > 0

    async def list_by_user(self, user_id: int) -> Sequence[Favorite]:
        stmt = select(Favorite).where(Favorite.user_id == user_id).order_by(Favorite.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def is_favorite(self, user_id: int, movie_slug: str) -> bool:
        stmt = select(Favorite).where(
            Favorite.user_id == user_id, Favorite.movie_slug == movie_slug
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
