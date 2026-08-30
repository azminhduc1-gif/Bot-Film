"""Session management: create, validate, authorize, and clean up sessions."""
from __future__ import annotations

import datetime as dt
import json
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Config
from app.database.models import Session as SessionModel
from app.database.repositories import SessionRepository
from app.logging_config import get_logger
from app.providers.kkphim.models import Movie

logger = get_logger(__name__)


class SessionService:
    """Manage per-user, per-chat, per-request sessions."""

    def __init__(self, db_session: AsyncSession, config: Config) -> None:
        self.db_session = db_session
        self.config = config
        self.repo = SessionRepository(db_session)

    def _generate_id(self) -> str:
        """Generate a short URL-safe session ID."""
        return secrets.token_urlsafe(12)

    def _ttl(self) -> dt.datetime:
        return dt.datetime.utcnow() + dt.timedelta(minutes=self.config.session_ttl_minutes)

    async def create(
        self,
        user_id: int,
        chat_id: int,
        query: str | None = None,
        message_id: int | None = None,
    ) -> SessionModel:
        """Create a new isolated session."""
        session_id = self._generate_id()
        session = await self.repo.create(
            session_id=session_id,
            user_id=user_id,
            chat_id=chat_id,
            query=query,
            message_id=message_id,
            expires_at=self._ttl(),
        )
        logger.info(
            "Created session=%s user=%s chat=%s query=%s",
            session.id,
            user_id,
            chat_id,
            query,
        )
        return session

    async def get(self, session_id: str) -> SessionModel | None:
        return await self.repo.get_by_id(session_id)

    async def authorize(
        self,
        session_id: str,
        telegram_user_id: int,
        chat_id: int,
    ) -> SessionModel | None:
        """Verify session exists, not expired, and belongs to the user/chat."""
        session = await self.repo.get_by_id(session_id)
        if session is None:
            logger.warning("Session not found session=%s", session_id)
            return None

        if session.expires_at < dt.datetime.utcnow():
            logger.warning("Session expired session=%s", session_id)
            return None

        if session.chat_id != chat_id:
            logger.warning(
                "Session chat mismatch session=%s expected=%s got=%s",
                session_id,
                session.chat_id,
                chat_id,
            )
            return None

        if session.user is None or session.user.telegram_user_id != telegram_user_id:
            logger.warning(
                "Session user mismatch session=%s expected=%s got=%s",
                session_id,
                session.user.telegram_user_id if session.user else None,
                telegram_user_id,
            )
            return None

        return session

    async def update_page(self, session_id: str, page: int) -> None:
        await self.repo.update(session_id, current_page=page)

    async def set_selected_movie(self, session_id: str, movie: Movie) -> None:
        await self.repo.update(session_id, selected_movie=movie.model_dump_json())

    async def get_selected_movie(self, session: SessionModel) -> Movie | None:
        if not session.selected_movie:
            return None
        try:
            return Movie(**json.loads(session.selected_movie))
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to deserialize selected movie for session=%s", session.id)
            return None

    async def refresh_ttl(self, session_id: str) -> None:
        await self.repo.update(session_id, expires_at=self._ttl())

    async def delete(self, session_id: str) -> None:
        await self.repo.delete(session_id)

    async def cleanup_expired(self) -> int:
        deleted = await self.repo.delete_expired()
        logger.info("Cleaned up %d expired sessions", deleted)
        return deleted
