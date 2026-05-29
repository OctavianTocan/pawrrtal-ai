"""Shared resolution helpers for Telegram model selection.

Every Telegram surface that needs to know "which model is this
conversation using right now" walks the same fallback chain:

1. ``Conversation.model_id`` (per-conversation override set via the
   picker, ``/model``, or the chat router).
2. ``UserPreferences.default_model_id`` (user's pinned default,
   written by ``/model ... default`` or the picker's "Set as
   default" button).
3. :func:`catalog.default_model` (system-wide fallback).

Centralising the chain in one helper avoids the drift that surfaces
when ``/thinking``, ``/compact``, ``/status``, and the chat path
each open-code the resolution differently — a known footgun before
this module existed.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.providers.catalog import default_model, find
from app.core.providers.model_id import InvalidModelId, parse_model_id
from app.crud.user_preferences import get_user_default_model_id

logger = logging.getLogger(__name__)


async def resolve_effective_model_id(
    *,
    session: AsyncSession,
    user_id: uuid.UUID,
    conversation_model_id: str | None,
) -> str:
    """Resolve the effective canonical model_id for a Telegram user.

    Order: conversation override → user default → catalog default.

    A user-default that's no longer in the catalog (e.g. catalog
    rotation removed it) is treated as stale: we log
    ``TELEGRAM_STALE_USER_DEFAULT`` and fall through to the catalog
    default rather than handing a dead ID to the downstream chat path.
    Operators reading the log can then prompt the user to re-pin.
    """
    if conversation_model_id:
        return conversation_model_id

    user_default = await get_user_default_model_id(
        session=session,
        user_id=user_id,
    )
    if user_default and _is_in_catalog(user_default):
        return user_default

    if user_default:
        logger.warning(
            "TELEGRAM_STALE_USER_DEFAULT user_id=%s stale_model_id=%s",
            user_id,
            user_default,
        )

    return default_model().id


def _is_in_catalog(model_id: str) -> bool:
    """Return whether ``model_id`` is structurally valid + catalog-known."""
    try:
        parsed = parse_model_id(model_id)
    except InvalidModelId:
        return False
    return find(parsed) is not None
