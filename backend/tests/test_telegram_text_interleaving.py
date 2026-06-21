"""Tests for chronological text-block interleaving on Telegram (#306, #307).

When the Anthropic stream alternates between thinking, tools, and final
text (``tool → thinking → tool → text → thinking → text``), the
Telegram channel must render each text segment in its chronological
position — not bundle all text into one trailing message.

The legacy behaviour (single text message at the end) is preserved
for pure-text turns where no thinking/tool block ever fires, since
that's the common case the existing UX is tuned for.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.channels.base import ChannelMessage
from app.channels.telegram import TelegramChannel
from app.providers.base import StreamEvent

pytestmark = pytest.mark.anyio


async def _stream(*events: StreamEvent) -> AsyncIterator[StreamEvent]:
    for event in events:
        yield event


def _make_channel_message(
    bot: AsyncMock, *, chat_id: int = 1, message_id: int = 2
) -> ChannelMessage:
    return ChannelMessage(
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        text="hello",
        surface="telegram",
        model_id=None,
        metadata={"bot": bot, "chat_id": chat_id, "message_id": message_id},
    )


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=777))
    return bot


@pytest.fixture(autouse=True)
def _disable_regenerate_button_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep legacy interleaving assertions independent of developer env flags."""
    monkeypatch.setattr(
        "app.channels.telegram.channel.settings.telegram_regenerate_button_enabled",
        False,
    )


async def test_text_after_thinking_renders_as_new_message() -> None:
    """thinking → text renders thinking via edit (placeholder) and text via send."""
    bot = _make_bot()
    msg = _make_channel_message(bot)
    channel = TelegramChannel()

    events: list[StreamEvent] = [
        {"type": "thinking", "content": "let me check"},
        {"type": "delta", "content": "the answer"},
    ]
    async for _ in channel.deliver(_stream(*events), msg):
        pass

    # Thinking edits the placeholder message (edit_message_text, not send_message).
    # After PR #14 (Claude Cage stream styling) the thinking block opens with
    # the ``✻ `` TUI marker; markdown italics still wrap inner emphasis via
    # ``<i>…</i>`` but the chunk itself isn't italicised end-to-end.
    edits = [call.kwargs.get("text", "") for call in bot.edit_message_text.await_args_list]
    assert any("✻ let me check" in s for s in edits)

    # The text delta opens a new interleaved message via send_message.
    sends = [call.kwargs.get("text", "") for call in bot.send_message.await_args_list]
    assert any(s == "the answer" for s in sends)


async def test_text_after_tools_renders_as_new_message() -> None:
    """tools → text opens a separate text message (#306 acceptance criterion)."""
    bot = _make_bot()
    msg = _make_channel_message(bot)
    channel = TelegramChannel()

    events: list[StreamEvent] = [
        {
            "type": "tool_use",
            "name": "search_files",
            "input": {"path": "/tmp"},
        },
        {"type": "delta", "content": "Done."},
    ]
    async for _ in channel.deliver(_stream(*events), msg):
        pass

    sends = [call.kwargs.get("text", "") for call in bot.send_message.await_args_list]
    # The text segment must arrive as its own send (not as a final
    # bundled answer at the end).
    assert any(s == "Done." for s in sends)


async def test_interleaved_text_segments_render_separately() -> None:
    """tool → text → tool → text: two text segments are two distinct Telegram messages."""
    bot = _make_bot()
    msg = _make_channel_message(bot)
    channel = TelegramChannel()

    events: list[StreamEvent] = [
        {"type": "tool_use", "name": "first_tool", "input": {}},
        {"type": "delta", "content": "First answer."},
        {"type": "tool_use", "name": "second_tool", "input": {}},
        {"type": "delta", "content": "Second answer."},
    ]
    async for _ in channel.deliver(_stream(*events), msg):
        pass

    sends = [call.kwargs.get("text", "") for call in bot.send_message.await_args_list]
    assert any(s == "First answer." for s in sends)
    assert any(s == "Second answer." for s in sends)


async def test_pure_text_turn_keeps_legacy_single_message_behavior() -> None:
    """No thinking/tool blocks → text still arrives as one final message edited in-place."""
    bot = _make_bot()
    msg = _make_channel_message(bot, chat_id=42, message_id=99)
    channel = TelegramChannel()

    events: list[StreamEvent] = [
        {"type": "delta", "content": "Hello, "},
        {"type": "delta", "content": "world"},
    ]
    async for _ in channel.deliver(_stream(*events), msg):
        pass

    # No new message sent or placeholder deleted; edited in-place instead.
    bot.delete_message.assert_not_called()
    bot.send_message.assert_not_called()
    bot.edit_message_text.assert_any_call(
        chat_id=42,
        message_id=99,
        text="Hello, world",
        reply_markup=None,
    )
