"""Tests for the aiogram glue in :mod:`model_picker_runtime`.

These exercise the orchestration that wires the picker keyboards to
the CRUD layer — the seam where a regression silently makes the
"Set as default" button stop working, or makes the inert
"Already your default" button alert as a stale picker.

Aiogram's ``CallbackQuery`` / ``Message`` are mocked with ``AsyncMock``
to avoid the framework dependency; the runtime treats them purely as
duck-typed objects with ``data``, ``from_user``, ``message``,
``answer``, ``edit_text``, and ``edit_reply_markup`` attributes.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.providers.catalog import MODEL_CATALOG
from app.integrations.telegram.model_picker import (
    ModelPickerState,
    build_set_default_keyboard,
)
from app.integrations.telegram.model_picker_runtime import (
    _handle_model_select,
    _handle_set_default,
    handle_model_picker_callback,
)


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
        message.edit_reply_markup = AsyncMock()
        callback.message = message
    else:
        callback.message = None
    return callback


@pytest.mark.anyio
class TestMdlNoopShortCircuit:
    """`mdl:noop` is the inert callback on the post-default badge."""

    async def test_mdl_noop_answers_without_alert(self) -> None:
        """A second tap on the inert badge must answer silently."""
        callback = _make_callback(data="mdl:noop")
        await handle_model_picker_callback(callback=callback)
        callback.answer.assert_awaited_once_with()
        # No edits should happen — the badge stays put.
        callback.message.edit_text.assert_not_called()
        callback.message.edit_reply_markup.assert_not_called()


@pytest.mark.anyio
class TestHandleSetDefault:
    """`_handle_set_default` persists the default and swaps the keyboard."""

    async def test_success_replaces_keyboard_with_inert_badge(self) -> None:
        """Happy path: user bound, model in catalog, button swap fires."""
        entry = MODEL_CATALOG[0]
        rows = build_set_default_keyboard(model_id=entry.id)
        assert rows is not None
        callback = _make_callback(data=rows[0][0].callback_data)
        with patch(
            "app.integrations.telegram.model_picker_runtime.set_user_default_model_from_callback",
            new=AsyncMock(return_value=True),
        ):
            await handle_model_picker_callback(callback=callback)
        callback.message.edit_reply_markup.assert_awaited_once()
        # The replacement keyboard's first button must be the inert badge.
        kwargs = callback.message.edit_reply_markup.await_args.kwargs
        inline_keyboard = kwargs["reply_markup"].inline_keyboard
        assert inline_keyboard[0][0].callback_data == "mdl:noop"
        callback.answer.assert_awaited_once()
        answer_text = callback.answer.await_args.args[0]
        assert entry.short_name in answer_text

    async def test_unbound_user_surfaces_not_bound_alert(self) -> None:
        """When the seam returns False the runtime alerts not-bound."""
        entry = MODEL_CATALOG[0]
        rows = build_set_default_keyboard(model_id=entry.id)
        assert rows is not None
        callback = _make_callback(data=rows[0][0].callback_data)
        with patch(
            "app.integrations.telegram.model_picker_runtime.set_user_default_model_from_callback",
            new=AsyncMock(return_value=False),
        ):
            await handle_model_picker_callback(callback=callback)
        callback.answer.assert_awaited_once()
        # The not-bound alert must be a show_alert call so the user sees it.
        kwargs = callback.answer.await_args.kwargs
        assert kwargs.get("show_alert") is True
        callback.message.edit_reply_markup.assert_not_called()

    async def test_stale_catalog_token_surfaces_stale_alert(self) -> None:
        """A stale catalog token must reject before touching the DB."""
        # Hand-craft a stale token payload — catalog index 0 with bad token.
        callback = _make_callback(data="mdl:d:deadbeef:0")
        set_default_mock = AsyncMock(return_value=True)
        with patch(
            "app.integrations.telegram.model_picker_runtime.set_user_default_model_from_callback",
            new=set_default_mock,
        ):
            await handle_model_picker_callback(callback=callback)
        set_default_mock.assert_not_called()
        callback.answer.assert_awaited_once()
        assert callback.answer.await_args.kwargs.get("show_alert") is True


@pytest.mark.anyio
class TestHandleModelSelectButtonBranching:
    """`_handle_model_select` conditionally surfaces the "Set as default" button."""

    async def test_button_omitted_when_selection_already_default(self) -> None:
        """If the picked model is already the user's default, no extra button."""
        entry = MODEL_CATALOG[0]
        # Build the select-action callback that the picker would emit.
        select_callback_data = f"mdl:s:{_catalog_token()}:0"
        callback = _make_callback(data=select_callback_data)
        # Pre-set state: user_default matches the entry the user just picked.
        state = ModelPickerState(
            current_model_id=entry.id,
            user_default_model_id=entry.id,
        )
        with (
            patch(
                "app.integrations.telegram.model_picker_runtime.handle_model_command",
                new=AsyncMock(return_value="Model switched ✅"),
            ),
            patch(
                "app.integrations.telegram.model_picker_runtime.get_model_picker_state",
                new=AsyncMock(return_value=state),
            ),
        ):
            await _handle_model_select(callback=callback, parsed=_select_callback_for_entry(0))
        # edit_text must be called WITHOUT reply_markup.
        callback.message.edit_text.assert_awaited_once()
        kwargs = callback.message.edit_text.await_args.kwargs
        assert "reply_markup" not in kwargs or kwargs.get("reply_markup") is None

    async def test_button_present_when_selection_is_new_default(self) -> None:
        """If the picked model differs from the user default, surface the button."""
        entry = MODEL_CATALOG[0]
        select_callback_data = f"mdl:s:{_catalog_token()}:0"
        callback = _make_callback(data=select_callback_data)
        # User has a *different* model as their default.
        state = ModelPickerState(
            current_model_id=entry.id,
            user_default_model_id=MODEL_CATALOG[1].id,
        )
        with (
            patch(
                "app.integrations.telegram.model_picker_runtime.handle_model_command",
                new=AsyncMock(return_value="Model switched ✅"),
            ),
            patch(
                "app.integrations.telegram.model_picker_runtime.get_model_picker_state",
                new=AsyncMock(return_value=state),
            ),
        ):
            await _handle_model_select(callback=callback, parsed=_select_callback_for_entry(0))
        callback.message.edit_text.assert_awaited_once()
        kwargs = callback.message.edit_text.await_args.kwargs
        # The reply_markup must contain a "Set as my default" star button.
        keyboard = kwargs["reply_markup"]
        assert keyboard is not None
        inline_keyboard = keyboard.inline_keyboard
        button = inline_keyboard[0][0]
        assert "⭐" in button.text
        assert button.callback_data.startswith("mdl:d:")


def _catalog_token() -> str:
    """Return the current catalog token used by select/set_default callbacks."""
    from app.core.providers.catalog import CATALOG_ETAG

    return CATALOG_ETAG[:8]


def _select_callback_for_entry(index: int):
    """Build the ModelCallback object that the runtime would receive."""
    from app.integrations.telegram.model_picker import ModelCallback

    return ModelCallback(action="select", index=index, catalog_token=_catalog_token())


# Suppress the unused-import warnings (kept for future use).
_ = (uuid, _handle_set_default)
