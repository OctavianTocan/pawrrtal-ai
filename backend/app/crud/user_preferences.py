"""CRUD helpers for :class:`UserPreferences`.

The row is created on demand the first time a preference is written.
Reads tolerate a missing row by returning ``None`` so reads stay
cheap for the common "user hasn't customised anything" case.

Owns the read/write surface for ``default_model_id`` — the per-user
default model used as a fallback when a conversation doesn't carry
its own explicit ``Conversation.model_id`` override.

Signature convention: ``session`` first positional, then the owning
identity (``user_id``), then the domain argument — see
``.claude/rules/clean-code/python-parameter-order.md``.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserPreferences

# Seed value used when the row is created on demand for a user who's
# only setting their default model. Column is NOT NULL in the
# existing schema; matches the implicit frontend appearance default.
_DEFAULT_FONT_SIZE = 14


async def get_user_default_model_id(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> str | None:
    """Return the user's persisted default model ID, or ``None``.

    ``None`` means "no row" OR "row exists but column is NULL" — both
    map to "fall back to the catalog default" at the call site, so
    callers don't need to distinguish.
    """
    row = await session.get(UserPreferences, user_id)
    if row is None:
        return None
    return row.default_model_id


async def set_user_default_model_id(
    session: AsyncSession,
    user_id: uuid.UUID,
    model_id: str | None,
) -> None:
    """Persist the user's default model ID, creating the row if absent.

    Pass ``model_id=None`` to clear the override so the next
    resolution falls back to ``catalog.default_model()``.
    """
    row = await session.get(UserPreferences, user_id)
    if row is None:
        row = UserPreferences(
            user_id=user_id,
            font_size=_DEFAULT_FONT_SIZE,
            default_model_id=model_id,
        )
        session.add(row)
    else:
        row.default_model_id = model_id
    await session.commit()
