"""Tests proving session isolation between users in the same group."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories import UserRepository
from app.services.session_service import SessionService


@pytest.mark.asyncio
async def test_user_a_and_user_b_sessions_are_isolated(
    session_service: SessionService,
    db_session: AsyncSession,
) -> None:
    """User A searching Avengers and User B searching Batman must not share state."""
    user_repo = UserRepository(db_session)
    user_a = await user_repo.get_or_create(telegram_user_id=1, username="user_a", first_name="User A")
    user_b = await user_repo.get_or_create(telegram_user_id=2, username="user_b", first_name="User B")

    session_a = await session_service.create(
        user_id=user_a.id,
        chat_id=-100123,
        query="Avengers",
        message_id=100,
    )
    session_b = await session_service.create(
        user_id=user_b.id,
        chat_id=-100123,
        query="Batman",
        message_id=101,
    )

    assert session_a.id != session_b.id
    assert session_a.user_id != session_b.user_id
    assert session_a.query == "Avengers"
    assert session_b.query == "Batman"

    # User B cannot access User A's session.
    authorized_b_for_a = await session_service.authorize(
        session_id=session_a.id,
        telegram_user_id=2,
        chat_id=-100123,
    )
    assert authorized_b_for_a is None

    # User A cannot access User B's session.
    authorized_a_for_b = await session_service.authorize(
        session_id=session_b.id,
        telegram_user_id=1,
        chat_id=-100123,
    )
    assert authorized_a_for_b is None

    # Correct owners can access their own sessions.
    assert await session_service.authorize(
        session_id=session_a.id,
        telegram_user_id=1,
        chat_id=-100123,
    )
    assert await session_service.authorize(
        session_id=session_b.id,
        telegram_user_id=2,
        chat_id=-100123,
    )


@pytest.mark.asyncio
async def test_session_chat_mismatch_is_rejected(
    session_service: SessionService,
    db_session: AsyncSession,
) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.get_or_create(telegram_user_id=1, username="user_a", first_name="User A")

    session = await session_service.create(
        user_id=user.id,
        chat_id=-100123,
        query="Avengers",
    )
    assert await session_service.authorize(
        session_id=session.id,
        telegram_user_id=1,
        chat_id=-100999,
    ) is None
