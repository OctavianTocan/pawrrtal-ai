"""Tests for the ``app.workspace.preferences_crud`` module."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.legacy import User
from app.workspace.preferences_crud import (
    get_user_default_model_id,
    set_user_default_model_id,
)


@pytest.mark.anyio
async def test_get_default_model_id_returns_none_when_no_row(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """A user without a preferences row reads back ``None``."""
    result = await get_user_default_model_id(session=db_session, user_id=test_user.id)
    assert result is None


@pytest.mark.anyio
async def test_set_default_model_id_creates_row_on_first_write(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Writing the first preference creates the row on demand."""
    await set_user_default_model_id(
        session=db_session,
        user_id=test_user.id,
        model_id="agent-sdk:anthropic/claude-sonnet-4-6",
    )
    persisted = await get_user_default_model_id(session=db_session, user_id=test_user.id)
    assert persisted == "agent-sdk:anthropic/claude-sonnet-4-6"


@pytest.mark.anyio
async def test_set_default_model_id_updates_existing_row(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """A second write updates the column in place, no duplicate row."""
    await set_user_default_model_id(
        session=db_session,
        user_id=test_user.id,
        model_id="gemini-api:google/gemini-3-flash-preview",
    )
    await set_user_default_model_id(
        session=db_session,
        user_id=test_user.id,
        model_id="agent-sdk:anthropic/claude-sonnet-4-6",
    )
    persisted = await get_user_default_model_id(session=db_session, user_id=test_user.id)
    assert persisted == "agent-sdk:anthropic/claude-sonnet-4-6"


@pytest.mark.anyio
async def test_set_default_model_id_clears_when_passed_none(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Passing ``None`` clears the override back to NULL."""
    await set_user_default_model_id(
        session=db_session,
        user_id=test_user.id,
        model_id="agent-sdk:anthropic/claude-sonnet-4-6",
    )
    await set_user_default_model_id(
        session=db_session,
        user_id=test_user.id,
        model_id=None,
    )
    result = await get_user_default_model_id(session=db_session, user_id=test_user.id)
    assert result is None
