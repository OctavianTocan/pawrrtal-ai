"""Per-conversation verbose-level picker for the Telegram channel.

Shape mirrors :mod:`app.integrations.telegram.thinking_picker` — pure
formatter + button builder + callback parser. The aiogram glue lives
in :mod:`app.integrations.telegram.verbose_picker_runtime` so this
module stays framework-free and unit-testable.

Three rungs total: ``quiet (0)``, ``normal (1)``, ``detailed (2)``.
A trailing "Use default" button appears only when an override is
currently set, so the picker stays minimal for users who haven't
customised anything yet. The semantics of each level are documented
in :func:`app.core.chat_aggregator.should_emit_event`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from html import escape
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.channel import (
    get_or_create_telegram_conversation_full,
    get_user_id_for_external,
)

PROVIDER = "telegram"
VERBOSE_CALLBACK_PREFIX = "vbs:"
_CALLBACK_SELECT_PARTS = 3  # vbs:s:<level>
_CALLBACK_CLEAR_PARTS = 2  # vbs:c

# ``_VERBOSE_LEVELS`` is the authoritative ordered list of rungs the
# picker exposes. Mirrors :data:`app.integrations.telegram.status._VERBOSE_LABELS`
# in coverage — kept independent here so the picker module stays free
# of any cross-imports from the status / handlers surface.
VERBOSE_LEVELS: tuple[int, ...] = (0, 1, 2)
_VERBOSE_LABELS: dict[int, str] = {
    0: "quiet",
    1: "normal",
    2: "detailed",
}

_NOT_BOUND_MESSAGE = "Connect your account first before changing verbose level."
_STALE_MESSAGE = "That verbose picker is out of date. Open /verbose again."
_PICKER_HEADER = (
    "🔊 Verbose level\n\n"
    "Pick what the assistant streams back to chat.\n"
    "Current: <b>{current_label}</b>"
)
_DEFAULT_BUTTON_TEXT = "Use default (clear override)"
_CURRENT_LABEL_DEFAULT_TEMPLATE = "default ({default_label})"


class TelegramSenderLike(Protocol):
    """Subset of ``TelegramSender`` used by the picker."""

    user_id: int
    thread_id: int | None


@dataclass(frozen=True)
class VerboseButton:
    """One inline-keyboard button for the verbose picker."""

    text: str
    callback_data: str


@dataclass(frozen=True)
class VerbosePickerState:
    """Resolved verbose state for one Telegram conversation.

    Carries ``conversation_id`` + ``user_id`` so callback handlers can
    persist the new override without a second user/conversation lookup —
    the picker has already paid the cost to resolve both once.
    ``default_level`` is the gateway-global default (read from
    ``settings.telegram_verbose_default``) so the "Use default" copy
    shows what clearing the override falls back to.
    """

    current_level: int | None
    default_level: int
    conversation_id: uuid.UUID
    user_id: uuid.UUID


@dataclass(frozen=True)
class VerboseCallback:
    """Parsed callback payload for the verbose picker."""

    action: str
    level: int | None = None


async def get_verbose_picker_state(
    *,
    sender: TelegramSenderLike,
    session: AsyncSession,
    default_level: int,
) -> VerbosePickerState | None:
    """Resolve the per-conversation verbose level and identity for ``sender``.

    Returns ``None`` when the Telegram sender isn't bound to a Pawrrtal
    user yet (the caller should reply with the not-bound message).
    """
    pawrrtal_user_id = await get_user_id_for_external(
        provider=PROVIDER,
        external_user_id=str(sender.user_id),
        session=session,
    )
    if pawrrtal_user_id is None:
        return None

    conversation = await get_or_create_telegram_conversation_full(
        user_id=pawrrtal_user_id,
        session=session,
        thread_id=sender.thread_id,
    )
    return VerbosePickerState(
        current_level=conversation.verbose_level,
        default_level=default_level,
        conversation_id=conversation.id,
        user_id=pawrrtal_user_id,
    )


def build_verbose_keyboard(state: VerbosePickerState) -> list[list[VerboseButton]]:
    """Build the keyboard rows for the picker.

    One button per rung, in ladder order. The trailing "Use default"
    button only appears when the row currently holds an override, so a
    fresh conversation sees three buttons and a customised one sees
    four.
    """
    rows: list[list[VerboseButton]] = [
        [
            VerboseButton(
                text=_level_button_label(level, current=state.current_level),
                callback_data=_select_callback(level),
            )
        ]
        for level in VERBOSE_LEVELS
    ]
    if state.current_level is not None:
        rows.append([VerboseButton(text=_DEFAULT_BUTTON_TEXT, callback_data=_clear_callback())])
    return rows


def format_picker_text(state: VerbosePickerState) -> str:
    """Render the picker header in Telegram HTML."""
    if state.current_level is None:
        current_label = _CURRENT_LABEL_DEFAULT_TEMPLATE.format(
            default_label=_VERBOSE_LABELS.get(state.default_level, str(state.default_level))
        )
    else:
        current_label = (
            f"{state.current_level} ({_VERBOSE_LABELS.get(state.current_level, 'unknown')})"
        )
    return _PICKER_HEADER.format(current_label=escape(current_label))


def parse_verbose_callback_data(data: str | None) -> VerboseCallback | None:
    """Parse Telegram callback data emitted by this picker."""
    if data is None or not data.startswith(VERBOSE_CALLBACK_PREFIX):
        return None
    parts = data.split(":")
    if len(parts) == _CALLBACK_SELECT_PARTS and parts[1] == "s":
        try:
            level = int(parts[2])
        except ValueError:
            return None
        if level not in _VERBOSE_LABELS:
            return None
        return VerboseCallback(action="select", level=level)
    if len(parts) == _CALLBACK_CLEAR_PARTS and parts[1] == "c":
        return VerboseCallback(action="clear")
    return None


def picker_not_bound_message() -> str:
    """Return the not-bound message for picker entry points."""
    return _NOT_BOUND_MESSAGE


def picker_stale_message() -> str:
    """Return the stale-picker callback message."""
    return _STALE_MESSAGE


def verbose_label(level: int) -> str:
    """Return the human-readable label for ``level`` (``"quiet"`` / ``"normal"`` / ``"detailed"``)."""
    return _VERBOSE_LABELS.get(level, "unknown")


def _level_button_label(level: int, *, current: int | None) -> str:
    """Render a level button — marks the currently-selected level."""
    prefix = "✓ " if level == current else ""
    return f"{prefix}{level} ({_VERBOSE_LABELS[level]})"


def _select_callback(level: int) -> str:
    return f"vbs:s:{level}"


def _clear_callback() -> str:
    return "vbs:c"


__all__ = [
    "VERBOSE_CALLBACK_PREFIX",
    "VERBOSE_LEVELS",
    "TelegramSenderLike",
    "VerboseButton",
    "VerboseCallback",
    "VerbosePickerState",
    "build_verbose_keyboard",
    "format_picker_text",
    "get_verbose_picker_state",
    "parse_verbose_callback_data",
    "picker_not_bound_message",
    "picker_stale_message",
    "verbose_label",
]
