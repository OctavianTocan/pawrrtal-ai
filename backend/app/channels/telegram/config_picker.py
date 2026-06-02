"""Framework-free helpers for the Telegram ``/config`` panel.

The panel exposes workspace-scoped switches that a Telegram user
should be able to change without opening the web Settings page.  It
does not own aiogram IO; :mod:`config_picker_runtime` performs the
actual message and callback handling.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from html import escape
from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.crud import get_user_id_for_external
from app.infrastructure.keys import load_workspace_env
from app.workspace.crud import get_default_workspace

PROVIDER = "telegram"
CONFIG_CALLBACK_PREFIX = "cfg:"
_CALLBACK_PARTS = 3  # cfg:t:<toggle>

_NOT_BOUND_MESSAGE = "Connect your account first before changing Telegram config."
_NO_WORKSPACE_MESSAGE = "No default workspace is available for this Telegram account."
_STALE_MESSAGE = "That config panel is out of date. Open /config again."

_ACTIVE_RECALL_KEY = "ACTIVE_RECALL_ENABLED"
_SEARCH_WORKSPACE_KEY = "ACTIVE_RECALL_SEARCH_WORKSPACE"


class ConfigToggle(StrEnum):
    """Config switches currently exposed through Telegram."""

    ACTIVE_RECALL = "ar"
    SEARCH_WORKSPACE = "ws"


_TOGGLE_KEY: dict[ConfigToggle, str] = {
    ConfigToggle.ACTIVE_RECALL: _ACTIVE_RECALL_KEY,
    ConfigToggle.SEARCH_WORKSPACE: _SEARCH_WORKSPACE_KEY,
}

_TOGGLE_LABEL: dict[ConfigToggle, str] = {
    ConfigToggle.ACTIVE_RECALL: "Active Recall",
    ConfigToggle.SEARCH_WORKSPACE: "Search Workspace",
}

_TOGGLE_DEFAULT: dict[ConfigToggle, bool] = {
    ConfigToggle.ACTIVE_RECALL: True,
    ConfigToggle.SEARCH_WORKSPACE: False,
}


class TelegramSenderLike(Protocol):
    """Subset of ``TelegramSender`` used by the config picker."""

    @property
    def user_id(self) -> int:
        """Telegram numeric user id."""
        ...


@dataclass(frozen=True)
class ConfigButton:
    """One inline-keyboard button for the config panel."""

    text: str
    callback_data: str


@dataclass(frozen=True)
class ConfigPickerState:
    """Resolved workspace config for one Telegram user."""

    user_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str
    workspace_root: Path
    active_recall_enabled: bool
    search_workspace_enabled: bool


@dataclass(frozen=True)
class ConfigCallback:
    """Parsed callback emitted by the config panel."""

    toggle: ConfigToggle


async def get_config_picker_state(
    *,
    sender: TelegramSenderLike,
    session: AsyncSession,
) -> ConfigPickerState | None:
    """Resolve the bound Paw user, default workspace, and current toggle state."""
    pawrrtal_user_id = await get_user_id_for_external(
        provider=PROVIDER,
        external_user_id=str(sender.user_id),
        session=session,
    )
    if pawrrtal_user_id is None:
        return None

    workspace = await get_default_workspace(pawrrtal_user_id, session)
    if workspace is None:
        return None

    root = Path(workspace.path)
    env = load_workspace_env(root)
    return ConfigPickerState(
        user_id=pawrrtal_user_id,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        workspace_root=root,
        active_recall_enabled=_env_bool(
            env.get(_ACTIVE_RECALL_KEY),
            default=_TOGGLE_DEFAULT[ConfigToggle.ACTIVE_RECALL],
        ),
        search_workspace_enabled=_env_bool(
            env.get(_SEARCH_WORKSPACE_KEY),
            default=_TOGGLE_DEFAULT[ConfigToggle.SEARCH_WORKSPACE],
        ),
    )


def build_config_keyboard(state: ConfigPickerState) -> list[list[ConfigButton]]:
    """Build the single-screen config keyboard."""
    return [
        [_button(ConfigToggle.ACTIVE_RECALL, value=state.active_recall_enabled)],
        [_button(ConfigToggle.SEARCH_WORKSPACE, value=state.search_workspace_enabled)],
    ]


def format_config_text(state: ConfigPickerState) -> str:
    """Render the config panel body in Telegram HTML."""
    active = _status_label(state.active_recall_enabled)
    search = _status_label(state.search_workspace_enabled)
    workspace = escape(state.workspace_name)
    return (
        "⚙️ <b>Config</b>\n\n"
        f"Workspace: <b>{workspace}</b>\n"
        f"Active Recall: <b>{active}</b>\n"
        f"Search Workspace: <b>{search}</b>"
    )


def parse_config_callback_data(data: str | None) -> ConfigCallback | None:
    """Parse a ``cfg:t:<toggle>`` callback payload."""
    if data is None or not data.startswith(CONFIG_CALLBACK_PREFIX):
        return None
    parts = data.split(":")
    if len(parts) != _CALLBACK_PARTS or parts[1] != "t":
        return None
    try:
        toggle = ConfigToggle(parts[2])
    except ValueError:
        return None
    return ConfigCallback(toggle=toggle)


def env_key_for_toggle(toggle: ConfigToggle) -> str:
    """Return the workspace env key controlled by ``toggle``."""
    return _TOGGLE_KEY[toggle]


def current_value_for_toggle(state: ConfigPickerState, toggle: ConfigToggle) -> bool:
    """Return the current value for ``toggle`` from ``state``."""
    if toggle == ConfigToggle.ACTIVE_RECALL:
        return state.active_recall_enabled
    return state.search_workspace_enabled


def config_not_bound_message() -> str:
    """Return the message for unbound Telegram senders."""
    return _NOT_BOUND_MESSAGE


def config_no_workspace_message() -> str:
    """Return the message for bound users without a default workspace."""
    return _NO_WORKSPACE_MESSAGE


def config_stale_message() -> str:
    """Return the stale-callback message."""
    return _STALE_MESSAGE


def toggle_label(toggle: ConfigToggle) -> str:
    """Return the human label for ``toggle``."""
    return _TOGGLE_LABEL[toggle]


def _button(toggle: ConfigToggle, *, value: bool) -> ConfigButton:
    text = f"{_TOGGLE_LABEL[toggle]}: {_status_label(value)}"
    return ConfigButton(text=text, callback_data=f"{CONFIG_CALLBACK_PREFIX}t:{toggle.value}")


def _status_label(value: bool) -> str:
    return "On" if value else "Off"


def _env_bool(value: str | None, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.lower() in {"true", "1", "yes", "on"}
