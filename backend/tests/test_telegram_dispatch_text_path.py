"""Unit tests for the legacy text-path same-block extend behaviour (#346).

When ``telegram_use_draft_streaming=False`` (the legacy edit-message
streaming path), ``dispatch_text_delta`` must EXTEND the open
interleaved text message on subsequent same-block deltas instead of
short-circuiting on ``previous_block_kind == "text"``. The previous
implementation returned ``rendered=False`` on every same-block delta
after the first chunk landed, which the channel layer treated as
"don't append" — so any text following a thinking or tools block
rendered only its first chunk.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.channels.telegram.dispatch import dispatch_text_delta


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=99))
    return bot


@pytest.mark.anyio
async def test_dispatch_text_delta_extends_interleaved_text_on_same_block() -> None:
    """A second delta with ``previous_block_kind="text"`` appends to the buffer.

    Reproduces the #346 regression: after a tools or thinking block,
    the first text delta opens an interleaved message, and every
    subsequent delta in the same text block must extend that message.
    The bug was a short-circuit that returned ``rendered=False`` on
    ``"text"`` and never appended chunks 2..N.
    """
    bot = _make_bot()

    # First delta after a tools block — opens the interleaved message.
    (
        text_buffer,
        text_message_id,
        chars_since_edit,
        last_edit_at,
        rendered,
    ) = await dispatch_text_delta(
        chunk="Hello",
        previous_block_kind="tools",
        bot=bot,
        chat_id=1,
        text_buffer="",
        text_message_id=None,
        chars_since_edit=0,
        last_edit_at=0.0,
        reply_to_message_id=None,
        message_thread_id=None,
    )
    assert rendered is True
    assert text_buffer == "Hello"
    assert text_message_id == 99

    # Second delta — same block. Must EXTEND the buffer, not short-circuit.
    text_buffer, _, _, _, rendered = await dispatch_text_delta(
        chunk=" world",
        previous_block_kind="text",
        bot=bot,
        chat_id=1,
        text_buffer=text_buffer,
        text_message_id=text_message_id,
        chars_since_edit=chars_since_edit,
        last_edit_at=last_edit_at,
        reply_to_message_id=None,
        message_thread_id=None,
    )
    assert rendered is True
    assert text_buffer == "Hello world"


@pytest.mark.anyio
async def test_dispatch_text_delta_pure_text_turn_still_short_circuits() -> None:
    """``previous_block_kind=None`` (pure-text turn) still returns rendered=False.

    Pure-text turns continue to accumulate into ``answer_text`` and
    only flush via the closing reply — we must not start opening
    interleaved messages for them.
    """
    bot = _make_bot()
    text_buffer, text_message_id, _, _, rendered = await dispatch_text_delta(
        chunk="Hello",
        previous_block_kind=None,
        bot=bot,
        chat_id=1,
        text_buffer="",
        text_message_id=None,
        chars_since_edit=0,
        last_edit_at=0.0,
        reply_to_message_id=None,
        message_thread_id=None,
    )
    assert rendered is False
    assert text_buffer == ""
    assert text_message_id is None
    bot.send_message.assert_not_called()
