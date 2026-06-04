"""Tests for the aiogram glue in :mod:`model_picker_runtime`.

These exercise the orchestration that wires the picker keyboards to
the CRUD layer — the seam where a regression silently breaks the
per-conversation model switch a picker selection triggers.

Aiogram's ``CallbackQuery`` / ``Message`` are mocked with ``AsyncMock``
to avoid the framework dependency; the runtime treats them purely as
duck-typed objects with ``data``, ``from_user``, ``message``,
``answer``, and ``edit_text`` attributes.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.telegram.model_picker import ModelCallback
from app.channels.telegram.model_picker_runtime import (
    _handle_model_select,
    handle_model_picker_callback,
)
from app.providers.catalog import MODEL_CATALOG


def _make_callback(*, data: str, with_message: bool = True) -> MagicMock:
    """Build a minimal ``CallbackQuery`` mock used across these tests."""
    callback = MagicMock()
    callback.data = data
    callback.answer = AsyncMock()
    callback.from_user = SimpleNamespace(id=42, username="t", full_name="T")
    if with_message:
        message = MagicMock()
        message.chat = SimpleNamespace(id=42)
        message.message_thread_id = None
        message.edit_text = AsyncMock()
        callback.message = message
    else:
        callback.message = None
    return callback


@pytest.mark.anyio
class TestHandleModelSelect:
    """`_handle_model_select` persists the switch and edits the message."""

    async def test_select_edits_message_and_answers(self) -> None:
        """Happy path: the switch reply is rendered and the callback answered."""
        entry = MODEL_CATALOG[0]
        select_callback_data = f"mdl:s:{_catalog_token()}:0"
        callback = _make_callback(data=select_callback_data)
        with patch(
            "app.channels.telegram.model_picker_runtime.handle_model_command",
            new=AsyncMock(return_value="Model switched ✅"),
        ):
            await _handle_model_select(callback=callback, parsed=_select_callback_for_entry(0))
        # The success message is edited in place, with no follow-up keyboard.
        callback.message.edit_text.assert_awaited_once_with("Model switched ✅")
        callback.answer.assert_awaited_once()
        answer_text = callback.answer.await_args.args[0]
        assert entry.short_name in answer_text

    async def test_stale_catalog_token_surfaces_stale_alert(self) -> None:
        """A stale catalog token must reject before touching the CRUD layer."""
        callback = _make_callback(data="mdl:s:deadbeef:0")
        handle_mock = AsyncMock(return_value="Model switched ✅")
        with patch(
            "app.channels.telegram.model_picker_runtime.handle_model_command",
            new=handle_mock,
        ):
            await handle_model_picker_callback(callback=callback)
        handle_mock.assert_not_called()
        callback.answer.assert_awaited_once()
        assert callback.answer.await_args.kwargs.get("show_alert") is True


def _catalog_token() -> str:
    """Return the current catalog token used by select callbacks."""
    from app.providers.catalog import CATALOG_ETAG

    return CATALOG_ETAG[:8]


def _select_callback_for_entry(index: int) -> ModelCallback:
    """Build the ModelCallback object that the runtime would receive."""
    return ModelCallback(action="select", index=index, catalog_token=_catalog_token())


# Suppress the unused-import warning (kept for future use).
_ = uuid
