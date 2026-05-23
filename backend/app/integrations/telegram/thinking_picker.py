"""Per-model reasoning-effort picker for the Telegram channel.

Shape mirrors :mod:`app.integrations.telegram.model_picker` — pure
formatter + button builder + callback parser. The aiogram glue lives in
:mod:`app.integrations.telegram.thinking_picker_runtime` so this module
stays framework-free and unit-testable.

Single-screen picker: the levels that show up are exactly those the
current model's catalog entry lists in ``supports_reasoning``. A model
with an empty tuple gets a no-keyboard reply explaining the model
doesn't honour the knob. A "Clear override" button lets the user fall
back to the provider's default.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from html import escape
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.providers.catalog import (
    CATALOG_ETAG,
    MODEL_CATALOG,
    ModelEntry,
    default_model,
    find,
)
from app.core.providers.model_id import InvalidModelId, parse_model_id
from app.crud.channel import (
    get_or_create_telegram_conversation_full,
    get_user_id_for_external,
)

PROVIDER = "telegram"
THINKING_CALLBACK_PREFIX = "thk:"
_CATALOG_TOKEN = CATALOG_ETAG[:8]
_CALLBACK_SELECT_PARTS = 4  # thk:s:<token>:<effort>
_CALLBACK_CLEAR_PARTS = 3  # thk:c:<token>

_NOT_BOUND_MESSAGE = "Connect your account first before changing reasoning level."
_STALE_MESSAGE = "That thinking picker is out of date. Open /thinking again."
_UNSUPPORTED_MESSAGE = (
    "🧠 Thinking\n\n"
    "The current model (<b>{model_name}</b>) doesn't accept reasoning levels — "
    "the knob would be ignored by its provider.\n\n"
    "Switch to a model that supports reasoning via /model first."
)
_PICKER_HEADER = (
    "🧠 Thinking\n\n"
    "Pick a reasoning level for <b>{model_name}</b>.\n"
    "Current: <b>{current_label}</b>"
)
_CURRENT_LABEL_DEFAULT = "default (provider-picked)"
_CLEAR_BUTTON_TEXT = "Clear override (use provider default)"


class TelegramSenderLike(Protocol):
    """Subset of ``TelegramSender`` used by the picker."""

    @property
    def user_id(self) -> int:
        """Telegram numeric user id."""
        ...

    @property
    def thread_id(self) -> int | None:
        """Telegram topic thread id, or ``None`` outside a topic."""
        ...


@dataclass(frozen=True)
class ThinkingButton:
    """One inline-keyboard button for the thinking picker."""

    text: str
    callback_data: str


@dataclass(frozen=True)
class ThinkingPickerState:
    """Resolved catalog state for one Telegram conversation.

    Carries ``conversation_id`` + ``user_id`` so callback handlers can
    persist a new override without a second user/conversation lookup
    round-trip — the picker has already paid the cost to resolve both
    once. ``user_id`` is the Pawrrtal user UUID (not the Telegram one),
    forwarded to ``update_conversation_reasoning_effort`` as the
    ownership gate.
    """

    model_entry: ModelEntry
    current_effort: str | None
    conversation_id: uuid.UUID
    user_id: uuid.UUID


@dataclass(frozen=True)
class ThinkingCallback:
    """Parsed callback payload for the thinking picker."""

    action: str
    effort: str | None = None
    catalog_token: str | None = None


async def get_thinking_picker_state(
    *,
    sender: TelegramSenderLike,
    session: AsyncSession,
) -> ThinkingPickerState | None:
    """Resolve the current model + stored reasoning effort.

    Returns ``None`` when the Telegram sender isn't bound to a user.
    Returns a state with ``model_entry=None``? — no: when the model
    isn't in the catalog (could happen after a catalog change) we
    still return a state so the caller can surface a clean
    "unsupported" reply.  The catalog default is used as the
    fallback so the picker is never empty for a brand-new
    conversation that hasn't picked a model yet.
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

    model_id = conversation.model_id or default_model().id
    entry = _resolve_entry(model_id) or default_model()
    return ThinkingPickerState(
        model_entry=entry,
        current_effort=conversation.reasoning_effort,
        conversation_id=conversation.id,
        user_id=pawrrtal_user_id,
    )


def build_thinking_keyboard(state: ThinkingPickerState) -> list[list[ThinkingButton]]:
    """Build the single-screen keyboard for the picker.

    One button per level the model honours, in catalog order. A
    trailing "Clear override" button is included only when a
    per-conversation override is currently set — so the picker stays
    minimal for users who haven't customised anything yet.
    """
    rows: list[list[ThinkingButton]] = [
        [
            ThinkingButton(
                text=_level_button_label(level, current=state.current_effort),
                callback_data=_select_callback(level),
            )
        ]
        for level in state.model_entry.supports_reasoning
    ]
    if state.current_effort is not None:
        rows.append([ThinkingButton(text=_CLEAR_BUTTON_TEXT, callback_data=_clear_callback())])
    return rows


def format_picker_text(state: ThinkingPickerState) -> str:
    """Render the picker header in Telegram HTML."""
    current_label = state.current_effort or _CURRENT_LABEL_DEFAULT
    return _PICKER_HEADER.format(
        model_name=escape(state.model_entry.short_name),
        current_label=escape(current_label),
    )


def format_unsupported_text(state: ThinkingPickerState) -> str:
    """Render the "model doesn't support reasoning" reply."""
    return _UNSUPPORTED_MESSAGE.format(model_name=escape(state.model_entry.short_name))


def model_supports_reasoning(state: ThinkingPickerState) -> bool:
    """Return whether the resolved model exposes any reasoning levels."""
    return bool(state.model_entry.supports_reasoning)


def parse_thinking_callback_data(data: str | None) -> ThinkingCallback | None:
    """Parse Telegram callback data emitted by this picker."""
    if data is None or not data.startswith(THINKING_CALLBACK_PREFIX):
        return None
    parts = data.split(":")
    if len(parts) == _CALLBACK_SELECT_PARTS and parts[1] == "s":
        return ThinkingCallback(action="select", catalog_token=parts[2], effort=parts[3])
    if len(parts) == _CALLBACK_CLEAR_PARTS and parts[1] == "c":
        return ThinkingCallback(action="clear", catalog_token=parts[2])
    return None


def resolve_select(
    callback: ThinkingCallback,
    *,
    entry: ModelEntry,
) -> str | None:
    """Validate a parsed select callback against the catalog snapshot.

    Returns the effort string when the catalog token is current and
    the effort is one the model actually supports, otherwise ``None``.
    The catalog-token check protects against a stale picker still
    showing levels that the new catalog has dropped.
    """
    if callback.catalog_token != _CATALOG_TOKEN:
        return None
    if callback.action != "select" or callback.effort is None:
        return None
    if callback.effort not in entry.supports_reasoning:
        return None
    return callback.effort


def picker_not_bound_message() -> str:
    """Return the not-bound message for picker entry points."""
    return _NOT_BOUND_MESSAGE


def picker_stale_message() -> str:
    """Return the stale-picker callback message."""
    return _STALE_MESSAGE


def catalog_token() -> str:
    """Expose the picker's catalog token for tests."""
    return _CATALOG_TOKEN


def _resolve_entry(model_id: str) -> ModelEntry | None:
    """Look up a catalog entry by canonical wire ID."""
    try:
        parsed = parse_model_id(model_id)
    except InvalidModelId:
        return None
    return find(parsed)


def _level_button_label(level: str, *, current: str | None) -> str:
    """Render a level button — marks the currently-selected level."""
    prefix = "✓ " if level == current else ""
    return f"{prefix}{level}"


def _select_callback(effort: str) -> str:
    return f"thk:s:{_CATALOG_TOKEN}:{effort}"


def _clear_callback() -> str:
    return f"thk:c:{_CATALOG_TOKEN}"


__all__ = [
    "MODEL_CATALOG",  # re-exported so runtime imports stay one-stop
    "THINKING_CALLBACK_PREFIX",
    "TelegramSenderLike",
    "ThinkingButton",
    "ThinkingCallback",
    "ThinkingPickerState",
    "build_thinking_keyboard",
    "catalog_token",
    "format_picker_text",
    "format_unsupported_text",
    "get_thinking_picker_state",
    "model_supports_reasoning",
    "parse_thinking_callback_data",
    "picker_not_bound_message",
    "picker_stale_message",
    "resolve_select",
]
