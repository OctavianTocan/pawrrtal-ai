"""Telegram subscriber for :class:`DreamingCompletedEvent` (#341).

Posts a brief "🌙 Pawrrtal dreamed" notice in the user's DM whenever
a dreaming pass lands in the ``completed`` state and produced at
least one new memory. Failed jobs are deliberately silent — the
user shouldn't be paged when a background pass errors; the runner
already records the failure on the row's ``error_text`` column for
the operator to inspect.

The handler is registered from the FastAPI lifespan alongside
:class:`NotificationService`. It looks up the user's Telegram
binding via the existing ``channel_bindings`` table; users without
a Telegram binding get no notification, by design — they'll see
the consolidated memories on their next session through the
existing ``memory_query`` tool.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.event_bus import DreamingCompletedEvent, Event
from app.db import async_session_maker
from app.models import ChannelBinding

if TYPE_CHECKING:
    from app.core.event_bus import EventBus

logger = logging.getLogger(__name__)

_TELEGRAM_PROVIDER = "telegram"
_NOTICE_TEMPLATE = (
    "🌙 Pawrrtal dreamed about your recent conversation.\n{memories_line}{summary_line}"
)


class DreamingNotificationService:
    """Bus subscriber that posts a Telegram notice on completed dreaming passes.

    Held by the FastAPI app state (alongside ``NotificationService``)
    so the lifespan can pass the live aiogram ``Bot`` at construction
    time without the dreaming runner taking a Telegram dependency.
    """

    def __init__(self, *, telegram_bot: Any | None) -> None:
        self._bot = telegram_bot

    def register(self, bus: EventBus) -> None:
        """Attach the dreaming-completion handler to the bus."""
        bus.subscribe(DreamingCompletedEvent, self.handle_completion)

    async def handle_completion(self, event: Event) -> None:
        """Post the dreaming notice to the user's Telegram DM if one exists."""
        if not isinstance(event, DreamingCompletedEvent):
            return
        if self._bot is None or event.user_id is None:
            return
        if event.status != "completed":
            return
        # Don't page on no-op runs — substring dedupe sometimes
        # filters every candidate out and the user wouldn't notice
        # a difference anyway.
        if event.memories_written == 0:
            return

        external_id = await _lookup_telegram_external_user_id(event.user_id)
        if external_id is None:
            return

        notice = _format_notice(event)
        try:
            await self._bot.send_message(chat_id=int(external_id), text=notice)
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            logger.warning(
                "DREAMING_NOTIFY_FAILED user_id=%s job_id=%s error=%s",
                event.user_id,
                event.job_id,
                exc,
            )


async def _lookup_telegram_external_user_id(user_id: object) -> str | None:
    """Read the user's Telegram external_user_id from ``channel_bindings``.

    For DMs, the external_user_id equals the chat_id — Telegram
    treats a 1:1 conversation's chat_id as the user's numeric id.
    Groups have their own chat_id which the dreaming notifier
    deliberately doesn't post into (the dreaming pass is
    user-scoped, not chat-scoped).
    """
    async with async_session_maker() as session:
        stmt = (
            select(ChannelBinding.external_user_id)
            .where(ChannelBinding.user_id == user_id)
            .where(ChannelBinding.provider == _TELEGRAM_PROVIDER)
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


def _format_notice(event: DreamingCompletedEvent) -> str:
    """Render the body of the Telegram notice from the event payload."""
    if event.memories_written == 1:
        memories_line = "Captured one new memory."
    else:
        memories_line = f"Captured {event.memories_written} new memories."
    # Summary is optional — only inline it when the model produced
    # something. Keeps the notice compact when the prompt focused
    # on memory extraction only.
    summary_line = ""
    if event.session_summary:
        summary_line = f"\n\n{event.session_summary}"
    return _NOTICE_TEMPLATE.format(
        memories_line=memories_line,
        summary_line=summary_line,
    )


__all__ = [
    "DreamingNotificationService",
]
