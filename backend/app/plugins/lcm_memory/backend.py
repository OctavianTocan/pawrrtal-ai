"""LCM conversation memory backend."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.infrastructure.config import settings
from app.lcm import assemble_context, ingest_message, schedule_lcm_compaction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class LCMConversationMemoryBackend:
    """Conversation memory backend backed by LCM context items."""

    async def load_history(
        self,
        session: AsyncSession,
        *,
        conversation_id: uuid.UUID,
        history_window: int,
    ) -> list[dict[str, str]] | None:
        """Return LCM history; LCM uses its configured fresh-tail count."""
        if not settings.lcm_enabled:
            return None
        return await assemble_context(
            session,
            conversation_id=conversation_id,
            fresh_tail_count=settings.lcm_fresh_tail_count,
        )

    async def ingest_messages(
        self,
        session: AsyncSession,
        *,
        conversation_id: uuid.UUID,
        user_message_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
    ) -> None:
        """Record turn messages in LCM context items."""
        if not settings.lcm_enabled:
            return
        await ingest_message(
            session,
            conversation_id=conversation_id,
            message_id=user_message_id,
        )
        await ingest_message(
            session,
            conversation_id=conversation_id,
            message_id=assistant_message_id,
        )

    def schedule_compaction(
        self,
        *,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        model_id: str,
    ) -> None:
        """Schedule LCM compaction for a completed turn."""
        if not settings.lcm_enabled:
            return
        schedule_lcm_compaction(
            conversation_id=conversation_id,
            user_id=user_id,
            model_id=model_id,
        )


def create_memory_backend() -> LCMConversationMemoryBackend:
    """Create the bundled LCM memory backend."""
    return LCMConversationMemoryBackend()
