"""Persistent per-user conversation for the Google Chat channel.

Lives in the package (not ``app.channels.crud``, which is at the 500-line
file budget) and mirrors the legacy Telegram DM lookup: one conversation
per user, tagged ``origin_channel="google_chat"``, so message history
survives across app restarts.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation

# ``origin_channel`` tag for Google Chat conversations — mirrors the inline
# ``"telegram"`` tag the Telegram conversation helper uses.
GOOGLE_CHAT_ORIGIN_CHANNEL = "google_chat"


async def get_or_create_google_chat_conversation(
    *,
    user_id: uuid.UUID,
    session: AsyncSession,
) -> Conversation:
    """Return the persistent Google Chat conversation for *user_id*.

    Single-user dogfood scope: one conversation per user, so message
    history survives across app restarts — the same persistence guarantee
    the Telegram DM lookup gives. Returns the full ORM row so the ingress
    can read the per-conversation ``model_id`` override in one round-trip.

    Args:
        user_id: Pawrrtal user who owns the conversation.
        session: Async database session.

    Returns:
        The resolved or newly created ``Conversation`` ORM row.
    """
    stmt = (
        select(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.origin_channel == GOOGLE_CHAT_ORIGIN_CHANNEL,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    conversation = Conversation(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Google Chat",
        origin_channel=GOOGLE_CHAT_ORIGIN_CHANNEL,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation
