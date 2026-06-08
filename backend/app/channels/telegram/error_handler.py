"""Dispatcher-level error replies for Telegram updates."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Dispatcher
    from aiogram.types import ErrorEvent, Message, ReplyParameters

logger = logging.getLogger(__name__)

_HANDLER_ERROR_MESSAGE = (
    "Pawrrtal hit an internal error while handling that message. The error has been logged."
)


def register_telegram_error_handler(dispatcher: Dispatcher) -> None:
    """Register the fallback reply for uncaught Telegram handler errors."""
    from aiogram import F  # noqa: PLC0415

    @dispatcher.error(F.update.message.as_("message"))
    async def _on_telegram_error(event: ErrorEvent, message: Message) -> None:
        await answer_telegram_handler_error(event=event, message=message)


async def answer_telegram_handler_error(*, event: ErrorEvent, message: Message) -> None:
    """Log an uncaught handler exception and notify the originating chat."""
    exception = event.exception
    logger.error(
        "TELEGRAM_HANDLER_FAILED chat_id=%s message_id=%s",
        _chat_id(message),
        getattr(message, "message_id", None),
        exc_info=(type(exception), exception, exception.__traceback__),
    )
    await _send_error_reply(message)


async def _send_error_reply(message: Message) -> None:
    try:
        await message.answer(
            _HANDLER_ERROR_MESSAGE,
            reply_parameters=_reply_parameters(getattr(message, "message_id", None)),
        )
    except Exception:
        logger.warning(
            "TELEGRAM_HANDLER_ERROR_REPLY_FAILED chat_id=%s message_id=%s",
            _chat_id(message),
            getattr(message, "message_id", None),
            exc_info=True,
        )


def _reply_parameters(message_id: object) -> ReplyParameters | None:
    if not isinstance(message_id, int) or message_id <= 0:
        return None
    from aiogram.types import ReplyParameters  # noqa: PLC0415

    return ReplyParameters(message_id=message_id)


def _chat_id(message: Message) -> object:
    chat = getattr(message, "chat", None)
    return getattr(chat, "id", None)
