"""Tests for the regenerate-keyboard helpers (#368)."""

from __future__ import annotations

import uuid

from app.integrations.telegram.regenerate_keyboard import (
    REGEN_CALLBACK_PREFIX,
    parse_regenerate_callback_data,
    regenerate_button_for,
)


def test_regenerate_button_carries_conversation_uuid() -> None:
    """The button payload encodes the conversation id behind the standard prefix."""
    conversation_id = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")
    button = regenerate_button_for(conversation_id)
    assert button.text == "🔄 Regenerate"
    assert button.callback_data == f"{REGEN_CALLBACK_PREFIX}{conversation_id}"


def test_regenerate_callback_data_fits_telegram_64_byte_cap() -> None:
    """A UUID-payload callback stays under Telegram's 64-byte callback_data cap.

    ``rgn:`` (4) + UUID stringified (36) = 40 bytes — well under 64.
    """
    button = regenerate_button_for(uuid.uuid4())
    assert len(button.callback_data.encode("utf-8")) <= 64


def test_parse_regenerate_callback_round_trips_uuid() -> None:
    """Parsing the emitted payload yields the original UUID back."""
    conversation_id = uuid.uuid4()
    button = regenerate_button_for(conversation_id)
    parsed = parse_regenerate_callback_data(button.callback_data)
    assert parsed is not None
    assert parsed.conversation_id == conversation_id


def test_parse_rejects_other_picker_callbacks() -> None:
    """Callbacks from sibling pickers must resolve to ``None``.

    Each picker owns a distinct prefix (``mdl:``, ``thk:``, ``vbs:``,
    ``rgn:``) so the dispatcher can fan out by prefix. Anything that
    doesn't start with the regen prefix must be rejected so it
    doesn't get routed to the regen handler by mistake.
    """
    assert parse_regenerate_callback_data(None) is None
    assert parse_regenerate_callback_data("mdl:p") is None
    assert parse_regenerate_callback_data("vbs:c") is None
    assert parse_regenerate_callback_data("thk:c:deadbeef") is None


def test_parse_rejects_malformed_uuid() -> None:
    """A non-UUID tail resolves to ``None`` so stale buttons get a clean stale-message reply."""
    assert parse_regenerate_callback_data("rgn:not-a-uuid") is None
    assert parse_regenerate_callback_data("rgn:") is None
    # Wrong length / shape still rejected
    assert parse_regenerate_callback_data("rgn:1234") is None
