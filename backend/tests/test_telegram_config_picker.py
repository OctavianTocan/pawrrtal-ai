"""Tests for the Telegram ``/config`` picker and runtime glue."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.telegram.config_picker import (
    CONFIG_CALLBACK_PREFIX,
    ConfigPickerState,
    ConfigToggle,
    build_config_keyboard,
    current_value_for_toggle,
    env_key_for_toggle,
    format_config_text,
    get_config_picker_state,
    parse_config_callback_data,
)
from app.channels.telegram.config_picker_runtime import handle_config_picker_callback
from app.channels.telegram.sender import TelegramSender

_USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
_WORKSPACE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000bb")


def _state(
    *,
    active_recall: bool = True,
    search_workspace: bool = False,
    root: Path = Path("/tmp/workspace"),
) -> ConfigPickerState:
    return ConfigPickerState(
        user_id=_USER_ID,
        workspace_id=_WORKSPACE_ID,
        workspace_name="Main",
        workspace_root=root,
        active_recall_enabled=active_recall,
        search_workspace_enabled=search_workspace,
    )


def _make_callback(*, data: str) -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.answer = AsyncMock()
    callback.from_user = SimpleNamespace(id=42, username="t", full_name="T")
    message = MagicMock()
    message.chat = SimpleNamespace(id=42)
    message.message_thread_id = None
    message.edit_text = AsyncMock()
    callback.message = message
    return callback


def test_keyboard_exposes_active_recall_and_workspace_search() -> None:
    buttons = [row[0] for row in build_config_keyboard(_state())]
    texts = [button.text for button in buttons]
    assert texts == ["Active Recall: On", "Search Workspace: Off"]
    parsed = [parse_config_callback_data(button.callback_data) for button in buttons]
    assert {item.toggle for item in parsed if item is not None} == set(ConfigToggle)


def test_callback_data_fits_telegram_limit() -> None:
    for row in build_config_keyboard(_state()):
        for button in row:
            assert len(button.callback_data.encode("utf-8")) <= 64


def test_parse_callback_rejects_stale_or_sibling_payloads() -> None:
    assert parse_config_callback_data(None) is None
    assert parse_config_callback_data("mdl:something") is None
    assert parse_config_callback_data("cfg:x:ar") is None
    assert parse_config_callback_data("cfg:t:not-a-toggle") is None


def test_format_config_text_escapes_workspace_name() -> None:
    state = ConfigPickerState(
        user_id=_USER_ID,
        workspace_id=_WORKSPACE_ID,
        workspace_name="Main <script>",
        workspace_root=Path("/tmp/workspace"),
        active_recall_enabled=True,
        search_workspace_enabled=True,
    )
    text = format_config_text(state)
    assert "Main &lt;script&gt;" in text
    assert "Active Recall: <b>On</b>" in text
    assert "Search Workspace: <b>On</b>" in text


@pytest.mark.anyio
async def test_get_config_picker_state_reads_workspace_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = TelegramSender(user_id=42, chat_id=42, username=None, full_name=None)
    workspace = SimpleNamespace(id=_WORKSPACE_ID, name="Main", path=str(tmp_path))
    monkeypatch.setattr(
        "app.channels.telegram.config_picker.get_user_id_for_external",
        AsyncMock(return_value=_USER_ID),
    )
    monkeypatch.setattr(
        "app.channels.telegram.config_picker.get_default_workspace",
        AsyncMock(return_value=workspace),
    )
    monkeypatch.setattr(
        "app.channels.telegram.config_picker.load_workspace_env",
        lambda _root: {
            "ACTIVE_RECALL_ENABLED": "false",
            "ACTIVE_RECALL_SEARCH_WORKSPACE": "true",
        },
    )

    state = await get_config_picker_state(sender=sender, session=AsyncMock())

    assert state is not None
    assert state.active_recall_enabled is False
    assert state.search_workspace_enabled is True


def test_toggle_key_and_value_helpers() -> None:
    state = _state(active_recall=False, search_workspace=True)
    assert env_key_for_toggle(ConfigToggle.ACTIVE_RECALL) == "ACTIVE_RECALL_ENABLED"
    assert env_key_for_toggle(ConfigToggle.SEARCH_WORKSPACE) == "ACTIVE_RECALL_SEARCH_WORKSPACE"
    assert current_value_for_toggle(state, ConfigToggle.ACTIVE_RECALL) is False
    assert current_value_for_toggle(state, ConfigToggle.SEARCH_WORKSPACE) is True


@pytest.mark.anyio
async def test_runtime_persists_toggle_and_repaints(tmp_path: Path) -> None:
    before = _state(active_recall=True, search_workspace=False, root=tmp_path)
    after = _state(active_recall=False, search_workspace=False, root=tmp_path)
    callback = _make_callback(data=f"{CONFIG_CALLBACK_PREFIX}t:ar")
    saved: list[dict[str, str]] = []

    with (
        patch(
            "app.channels.telegram.config_picker_runtime.get_config_picker_state",
            new=AsyncMock(side_effect=[before, after]),
        ),
        patch(
            "app.channels.telegram.config_picker_runtime.load_workspace_env",
            return_value={"UNCHANGED": "yes"},
        ),
        patch(
            "app.channels.telegram.config_picker_runtime.save_workspace_env",
            side_effect=lambda _root, env: saved.append(dict(env)),
        ),
    ):
        await handle_config_picker_callback(callback=callback)

    assert saved == [{"UNCHANGED": "yes", "ACTIVE_RECALL_ENABLED": "false"}]
    callback.message.edit_text.assert_awaited_once()
    assert "Active Recall: <b>Off</b>" in callback.message.edit_text.await_args.args[0]
    callback.answer.assert_awaited_once_with("Active Recall: Off")
