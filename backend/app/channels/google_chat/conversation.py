"""Persistent per-surface conversation lookup for the Google Chat channel.

Lives in the package (not ``app.channels.crud``, which is at the 500-line
file budget). Each row is tagged ``origin_channel="google_chat"`` and scoped
to the Chat space/thread that produced it, so bound users keep separate
history across rooms and threads.
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


def google_chat_conversation_key(*, space_name: str, thread_name: str | None) -> str:
    """Return the channel-local key for a Google Chat space/thread surface."""
    return f"{space_name}|{thread_name or 'top-level'}"


async def get_or_create_google_chat_conversation(
    *,
    user_id: uuid.UUID,
    channel_thread_key: str,
    session: AsyncSession,
) -> Conversation:
    """Return the persistent Google Chat conversation for one user + surface.

    Returns the full ORM row so the ingress can read the per-conversation
    ``model_id`` override in one round-trip.

    Args:
        user_id: Pawrrtal user who owns the conversation.
        channel_thread_key: Google Chat space/thread resource key.
        session: Async database session.

    Returns:
        The resolved or newly created ``Conversation`` ORM row.
    """
    stmt = (
        select(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.origin_channel == GOOGLE_CHAT_ORIGIN_CHANNEL,
            Conversation.channel_thread_key == channel_thread_key,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    return await _insert_new_conversation(
        user_id=user_id,
        channel_thread_key=channel_thread_key,
        session=session,
    )


async def start_new_google_chat_conversation(
    *,
    user_id: uuid.UUID,
    channel_thread_key: str,
    session: AsyncSession,
) -> Conversation:
    """Create and return a fresh Google Chat conversation for one surface.

    Backs the ``/new`` command: a brand-new row has the most-recent
    ``updated_at``, so :func:`get_or_create_google_chat_conversation`
    returns it on the next turn in the same Chat space/thread, without
    touching other spaces or threads.
    """
    return await _insert_new_conversation(
        user_id=user_id,
        channel_thread_key=channel_thread_key,
        session=session,
    )


async def _insert_new_conversation(
    *,
    user_id: uuid.UUID,
    channel_thread_key: str,
    session: AsyncSession,
) -> Conversation:
    """Insert, commit, and return a fresh Google Chat conversation row."""
    conversation = Conversation(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Google Chat",
        origin_channel=GOOGLE_CHAT_ORIGIN_CHANNEL,
        channel_thread_key=channel_thread_key,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation
