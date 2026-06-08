"""Tests for Telegram dispatcher-level error replies."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Protocol, cast
from unittest.mock import AsyncMock

import pytest

from app.channels.telegram.error_handler import register_telegram_error_handler

if TYPE_CHECKING:
    from aiogram import Dispatcher


class _ErrorHandler(Protocol):
    async def __call__(self, event: object, message: object) -> None: ...


class _ErrorDecorator(Protocol):
    def __call__(self, handler: _ErrorHandler) -> _ErrorHandler: ...


class _FakeErrorObserver:
    """Captures the function registered through ``dispatcher.error(...)``."""

    def __init__(self) -> None:
        self.handler: _ErrorHandler | None = None

    def __call__(self, *_filters: object) -> _ErrorDecorator:
        def _decorate(handler: _ErrorHandler) -> _ErrorHandler:
            self.handler = handler
            return handler

        return _decorate


class _FakeDispatcher:
    def __init__(self) -> None:
        self.error = _FakeErrorObserver()


@pytest.mark.anyio
async def test_telegram_error_handler_replies_without_leaking_exception() -> None:
    """Unhandled Telegram handler exceptions should not fail silently."""
    dispatcher = _FakeDispatcher()
    register_telegram_error_handler(cast("Dispatcher", dispatcher))
    message = SimpleNamespace(message_id=123, answer=AsyncMock())
    event = SimpleNamespace(exception=RuntimeError("password auth failed"))

    assert dispatcher.error.handler is not None
    await dispatcher.error.handler(event, message)

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "internal error" in text
    assert "password auth failed" not in text
    reply_parameters = message.answer.await_args.kwargs["reply_parameters"]
    assert reply_parameters.message_id == 123
