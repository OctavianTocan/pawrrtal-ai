"""Unit tests for :mod:`app.channels.telegram.dispatch` per-event helpers.

Focus: the ``handle_thinking`` state machine after the #345 / #351 / #353
fixes. xAI streams per-token (one logical block, ``block_index=0`` for
every event); Gemini and Claude stream per-block (incrementing
``block_index``). The dispatch layer must:

* concatenate same-block deltas with **no** separator so xAI tokens
  retain their inter-token spaces (#345),
* insert a paragraph break between distinct blocks so Gemini's
  per-``Part`` thinking emissions read as separate thoughts (#351,
  #353),
* fall back to plain concatenation when the provider omits
  ``block_index`` so older stream functions and tests stay green.

These tests target the exact state-machine transition so the failure
message is sharper than a multi-message channel snapshot would be —
the L1 layer the test plan in issue #352 calls for.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.channels.telegram.dispatch import handle_thinking


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=42))
    return bot


@pytest.mark.anyio
async def test_handle_thinking_preserves_token_spacing() -> None:
    """xAI per-token deltas (constant ``block_index``) concatenate verbatim.

    The previous implementation stripped each chunk and joined with
    ``\\n``, producing newline-per-token output for xAI's grok-4.3
    reasoning (#345). The current state machine appends every chunk
    untouched when the block_index doesn't change.
    """
    bot = _make_bot()
    thinking_text = ""
    thinking_message_id: int | None = None
    previous_block_index: int | None = None

    tokens = ["Let", " me", " think", " about", " this", "."]
    for token in tokens:
        thinking_text, thinking_message_id, previous_block_index = await handle_thinking(
            event={"type": "thinking", "content": token, "block_index": 0},
            bot=bot,
            chat_id=1,
            thinking_text=thinking_text,
            thinking_message_id=thinking_message_id,
            previous_thinking_block_index=previous_block_index,
            reply_to_message_id=None,
            message_thread_id=None,
        )

    assert thinking_text == "Let me think about this."
    assert previous_block_index == 0
    # No paragraph break should ever land inside a same-block stream.
    assert "\n\n" not in thinking_text


@pytest.mark.anyio
async def test_handle_thinking_separates_blocks() -> None:
    """Gemini per-Part deltas (incrementing ``block_index``) get a paragraph break.

    The dispatch layer inserts the separator between blocks so the
    rendered italic message reads as distinct thoughts rather than
    a single run-on stream (#351, #353).
    """
    bot = _make_bot()
    thinking_text = ""
    thinking_message_id: int | None = None
    previous_block_index: int | None = None

    # Two distinct Gemini ``Part(thought=True)`` emissions arrive as
    # two ``thinking`` events with different ``block_index`` values.
    blocks = [
        ("Plan A: walk through the failing tests.", 0),
        ("Plan B: bisect to the regressing commit.", 1),
    ]
    for text, block_index in blocks:
        thinking_text, thinking_message_id, previous_block_index = await handle_thinking(
            event={"type": "thinking", "content": text, "block_index": block_index},
            bot=bot,
            chat_id=1,
            thinking_text=thinking_text,
            thinking_message_id=thinking_message_id,
            previous_thinking_block_index=previous_block_index,
            reply_to_message_id=None,
            message_thread_id=None,
        )

    assert "\n\n" in thinking_text
    assert thinking_text.startswith("Plan A:")
    assert thinking_text.endswith("regressing commit.")
    assert previous_block_index == 1


@pytest.mark.anyio
async def test_handle_thinking_without_block_index_concatenates_verbatim() -> None:
    """Events that omit ``block_index`` fall back to plain concatenation.

    Older provider stream functions that pre-date #353 still validate
    against ``LLMThinkingDeltaEvent`` because ``block_index`` is
    ``NotRequired``. Their dispatch path must not start inserting
    spurious paragraph breaks just because the field went away.
    """
    bot = _make_bot()
    thinking_text = ""
    thinking_message_id: int | None = None
    previous_block_index: int | None = None

    for chunk in ["alpha", " beta", " gamma"]:
        thinking_text, thinking_message_id, previous_block_index = await handle_thinking(
            event={"type": "thinking", "content": chunk},
            bot=bot,
            chat_id=1,
            thinking_text=thinking_text,
            thinking_message_id=thinking_message_id,
            previous_thinking_block_index=previous_block_index,
            reply_to_message_id=None,
            message_thread_id=None,
        )

    assert thinking_text == "alpha beta gamma"
    # No block_index means "treat as same block" — no separator inserted.
    assert "\n\n" not in thinking_text
    # The baseline stays unset because nothing on the wire claimed an index.
    assert previous_block_index is None


@pytest.mark.anyio
async def test_handle_thinking_empty_chunk_preserves_block_index_baseline() -> None:
    """Empty thinking events don't shift the baseline used for separator decisions.

    A provider that emits an empty thinking delta — possible when a
    chunk's only ``Part`` carried no text — should leave ``thinking_text``
    untouched. The next real chunk must still know whether the previous
    block index was set.
    """
    bot = _make_bot()
    thinking_text, _, baseline = await handle_thinking(
        event={"type": "thinking", "content": "first.", "block_index": 0},
        bot=bot,
        chat_id=1,
        thinking_text="",
        thinking_message_id=None,
        previous_thinking_block_index=None,
        reply_to_message_id=None,
        message_thread_id=None,
    )
    assert baseline == 0

    # Empty content arriving on the same block: state is unchanged.
    thinking_text2, _, baseline2 = await handle_thinking(
        event={"type": "thinking", "content": "", "block_index": 0},
        bot=bot,
        chat_id=1,
        thinking_text=thinking_text,
        thinking_message_id=42,
        previous_thinking_block_index=baseline,
        reply_to_message_id=None,
        message_thread_id=None,
    )
    assert thinking_text2 == thinking_text
    assert baseline2 == 0
