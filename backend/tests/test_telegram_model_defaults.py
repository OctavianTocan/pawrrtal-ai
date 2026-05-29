"""Tests for :func:`app.channels.telegram.model_defaults.resolve_effective_model_id`.

The resolver owns the three-step fallback chain that every Telegram
surface walks. Centralising it means every regression here is caught
once; centralising it also means the breadcrumb logged for stale
user-defaults must be exercised explicitly.
"""

from __future__ import annotations

import logging
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.telegram.model_defaults import resolve_effective_model_id
from app.core.providers.catalog import MODEL_CATALOG, default_model
from app.infrastructure.database.legacy import User


@pytest.mark.anyio
async def test_resolve_returns_conversation_override_when_set(
    db_session: AsyncSession, test_user: User
) -> None:
    """Conversation override beats user default beats catalog default."""
    pinned = MODEL_CATALOG[1].id
    resolved = await resolve_effective_model_id(
        session=db_session,
        user_id=test_user.id,
        conversation_model_id=pinned,
    )
    assert resolved == pinned


@pytest.mark.anyio
async def test_resolve_falls_back_to_user_default_when_no_override(
    db_session: AsyncSession, test_user: User
) -> None:
    """When conversation has no override, the user's pinned default wins."""
    from app.workspace.preferences_crud import set_user_default_model_id

    user_default = MODEL_CATALOG[2].id
    await set_user_default_model_id(
        session=db_session,
        user_id=test_user.id,
        model_id=user_default,
    )
    resolved = await resolve_effective_model_id(
        session=db_session,
        user_id=test_user.id,
        conversation_model_id=None,
    )
    assert resolved == user_default


@pytest.mark.anyio
async def test_resolve_falls_back_to_catalog_default_when_user_default_unset(
    db_session: AsyncSession, test_user: User
) -> None:
    """No conversation override + no user default → catalog default."""
    resolved = await resolve_effective_model_id(
        session=db_session,
        user_id=test_user.id,
        conversation_model_id=None,
    )
    assert resolved == default_model().id


@pytest.mark.anyio
async def test_resolve_skips_stale_user_default_and_logs(
    db_session: AsyncSession,
    test_user: User,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A user default removed from the catalog must fall through + log."""
    from app.workspace.preferences_crud import set_user_default_model_id

    stale = "agent-sdk:anthropic/this-was-removed"
    await set_user_default_model_id(
        session=db_session,
        user_id=test_user.id,
        model_id=stale,
    )
    with caplog.at_level(logging.WARNING):
        resolved = await resolve_effective_model_id(
            session=db_session,
            user_id=test_user.id,
            conversation_model_id=None,
        )
    # Falls through to the catalog default rather than handing the
    # stale ID to the downstream chat path.
    assert resolved == default_model().id
    # And leaves an operator breadcrumb so the user can be nudged.
    assert any(
        "TELEGRAM_STALE_USER_DEFAULT" in record.message and stale in record.message
        for record in caplog.records
    )


@pytest.mark.anyio
async def test_resolve_does_not_log_when_no_user_default(
    db_session: AsyncSession,
    test_user: User,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Falling through to catalog default for a user with no pref is silent."""
    with caplog.at_level(logging.WARNING):
        await resolve_effective_model_id(
            session=db_session,
            user_id=test_user.id,
            conversation_model_id=None,
        )
    assert not any("TELEGRAM_STALE_USER_DEFAULT" in record.message for record in caplog.records)


# Avoid unused-import warnings for fixtures referenced only by name.
_ = uuid
