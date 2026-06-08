"""Inline-keyboard helpers for the per-turn ``Regenerate`` button.

After every assistant reply the Telegram channel attaches a small
inline keyboard with a single ``🔄 Regenerate`` button. Tapping the
button hands the conversation back to the turn pipeline with the
same user input that produced the (now stale) answer, so the user
can ask the model to try again without retyping the prompt.

The framework-free shape mirrors :mod:`thinking_picker` and
:mod:`verbose_picker` — pure dataclasses + callback parsing here,
aiogram glue in :mod:`regenerate_runtime`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram.types import InlineKeyboardMarkup

REGEN_CALLBACK_PREFIX = "rgn:"
_REGEN_BUTTON_TEXT = "🔄 Regenerate"
_CALLBACK_PARTS = 2  # rgn:<conversation_id>


@dataclass(frozen=True)
class RegenerateButton:
    """One inline-keyboard button for the regenerate row."""

    text: str
    callback_data: str


@dataclass(frozen=True)
class RegenerateCallback:
    """Parsed callback payload for the regenerate button.

    ``conversation_id`` is the only payload the button carries — the
    runtime resolves the latest user message in that conversation
    from the database, so we don't need to encode the message text
    or assistant message id in callback_data (Telegram caps callback
    data at 64 bytes).
    """

    conversation_id: uuid.UUID


def regenerate_button_for(conversation_id: uuid.UUID) -> RegenerateButton:
    """Build the lone inline button rendered under each assistant reply.

    Args:
        conversation_id: The conversation the reply belongs to. The
            callback uses this to find the most recent user message
            and re-run the turn pipeline against it.

    Returns:
        A single :class:`RegenerateButton` ready to drop into a
        Telegram ``InlineKeyboardMarkup`` row.
    """
    return RegenerateButton(
        text=_REGEN_BUTTON_TEXT,
        callback_data=f"{REGEN_CALLBACK_PREFIX}{conversation_id}",
    )


def parse_regenerate_callback_data(data: str | None) -> RegenerateCallback | None:
    """Parse a ``rgn:<uuid>`` payload back into a :class:`RegenerateCallback`.

    Returns ``None`` for any malformed payload (wrong prefix, missing
    UUID, unparseable UUID) so callers can surface a stale-callback
    notice without an exception.
    """
    if data is None or not data.startswith(REGEN_CALLBACK_PREFIX):
        return None
    parts = data.split(":", maxsplit=1)
    if len(parts) != _CALLBACK_PARTS:
        return None
    raw_uuid = parts[1]
    try:
        conversation_id = uuid.UUID(raw_uuid)
    except ValueError:
        return None
    return RegenerateCallback(conversation_id=conversation_id)


def regenerate_markup_for(conversation_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Build the aiogram ``InlineKeyboardMarkup`` for the regenerate row.

    Importing aiogram inside the function keeps the framework-free
    surface (``regenerate_button_for``, ``parse_regenerate_callback_data``)
    importable in test contexts that don't ship aiogram.
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup  # noqa: PLC0415

    button = regenerate_button_for(conversation_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button.text, callback_data=button.callback_data)]
        ]
    )


__all__ = [
    "REGEN_CALLBACK_PREFIX",
    "RegenerateButton",
    "RegenerateCallback",
    "parse_regenerate_callback_data",
    "regenerate_button_for",
    "regenerate_markup_for",
]
