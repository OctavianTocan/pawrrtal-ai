"""Telegram delivery subscriber for agent response events."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from fastapi import FastAPI

from app.infrastructure.event_bus.bus import Event
from app.infrastructure.event_bus.types import AgentResponseEvent

logger = logging.getLogger(__name__)

_TELEGRAM_MESSAGE_CHARS = 4000


class TelegramNotificationService:
    """Bus subscriber that delivers agent responses to Telegram chats."""

    def __init__(self, *, telegram_bot: Any | None) -> None:
        self._bot = telegram_bot

    def register(self, bus: Any) -> None:
        """Attach the delivery handler to the bus."""
        bus.subscribe(AgentResponseEvent, self.handle_response)

    async def handle_response(self, event: Event) -> None:
        """Deliver the response text to the configured Telegram chat."""
        if not isinstance(event, AgentResponseEvent):
            return
        if self._bot is None:
            logger.debug(
                "TELEGRAM_NOTIFICATION_NO_BOT originating_event_id=%s",
                event.originating_event_id,
            )
            return

        text = (event.text or "").strip()
        if not text:
            return
        text = _fit_telegram_message(text)

        for chat_id in self._resolve_target_chats(event):
            try:
                await self._bot.send_message(chat_id=chat_id, text=text)
            except Exception:
                logger.exception(
                    "TELEGRAM_NOTIFICATION_DELIVERY_FAILED chat_id=%s originating_event_id=%s",
                    chat_id,
                    event.originating_event_id,
                )

    def _resolve_target_chats(self, event: AgentResponseEvent) -> Iterable[str]:
        """Pick the Telegram chats for this response."""
        if event.chat_id:
            yield event.chat_id


async def register_telegram_notifications(app: FastAPI, service: Any | None) -> None:
    """Register Telegram notification delivery after the channel service starts."""
    event_bus = getattr(app.state, "event_bus", None)
    if event_bus is None:
        return
    bot = getattr(service, "bot", None)
    TelegramNotificationService(telegram_bot=bot).register(event_bus)


def _fit_telegram_message(text: str) -> str:
    """Return one Telegram-safe message body."""
    if len(text) <= _TELEGRAM_MESSAGE_CHARS:
        return text
    if _TELEGRAM_MESSAGE_CHARS <= 1:
        return text[:_TELEGRAM_MESSAGE_CHARS]
    return text[: _TELEGRAM_MESSAGE_CHARS - 1] + "…"
