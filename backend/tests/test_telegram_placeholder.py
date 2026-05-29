"""Tests for the content-preview-in-placeholder state machine.

Verifies that:
- On stream open, placeholder is updated to render_initial() content.
- On first text delta (pure-text turn), placeholder transitions to render_working().
- Preview is truncated to PREVIEW_MAX_CHARS + ellipsis.
- HTML special chars in delta are escaped in the preview.
- The spurious "🚀 Starting …" banner (formerly rendered on every first event
  regardless of context) does NOT fire.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.channels.base import ChannelMessage
from app.channels.telegram import TelegramChannel
from app.channels.telegram.progress import PREVIEW_MAX_CHARS
from app.providers.base import StreamEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _stream(*events: StreamEvent) -> AsyncIterator[StreamEvent]:
    for event in events:
        yield event


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=777))
    return bot


def _make_channel_message(bot: AsyncMock, model_id: str = "test-model") -> ChannelMessage:
    return ChannelMessage(
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        text="hello",
        surface="telegram",
        model_id=model_id,
        metadata={
            "bot": bot,
            "chat_id": 123,
            "message_id": 456,
        },
    )


# ---------------------------------------------------------------------------
# Content-preview-in-placeholder tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestContentPreviewPlaceholder:
    async def test_initial_state_sent_on_stream_open(self) -> None:
        """Placeholder is updated to render_initial() before any event."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        async for _ in channel.deliver(_stream({"type": "delta", "content": "Hello!"}), msg):
            pass

        # At least the first edit_message_text call should contain the initial text.
        all_texts = [c.kwargs.get("text", "") for c in bot.edit_message_text.call_args_list]
        assert any("Processing" in t or "🤔" in t for t in all_texts), (
            f"Expected initial progress state in edit calls, got: {all_texts}"
        )

    async def test_no_spurious_starting_banner_on_first_event(self) -> None:
        """The placeholder must NOT flash a "🚀 Starting …" banner.

        The original implementation flashed this on every first event,
        with an empty model name and a zero tool count — surfacing a
        confusing half-message ("🚀 Starting ") to the user every turn.
        That state was removed; this test guards against regressions.
        """
        bot = _make_bot()
        msg = _make_channel_message(bot, model_id="claude-sonnet")
        channel = TelegramChannel()

        async for _ in channel.deliver(_stream({"type": "delta", "content": "hi"}), msg):
            pass

        all_texts = [c.kwargs.get("text", "") for c in bot.edit_message_text.call_args_list]
        assert all("Starting" not in t and "🚀" not in t for t in all_texts), (
            f"Unexpected STARTING-state edit found: {all_texts}"
        )

    async def test_working_state_contains_preview_text(self) -> None:
        """First text delta transitions to WORKING with a preview of the content."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        async for _ in channel.deliver(
            _stream({"type": "delta", "content": "Here is a detailed answer."}), msg
        ):
            pass

        all_texts = [c.kwargs.get("text", "") for c in bot.edit_message_text.call_args_list]
        # At least one edit should contain "Working" or the robot emoji
        assert any("Working" in t or "🤖" in t for t in all_texts), (
            f"Expected WORKING state in edit calls, got: {all_texts}"
        )

    async def test_preview_truncated_at_limit(self) -> None:
        """A very long delta is truncated to PREVIEW_MAX_CHARS in the preview."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        long_content = "x" * (PREVIEW_MAX_CHARS + 200)
        async for _ in channel.deliver(_stream({"type": "delta", "content": long_content}), msg):
            pass

        all_texts = [c.kwargs.get("text", "") for c in bot.edit_message_text.call_args_list]
        working_texts = [t for t in all_texts if "🤖" in t or "Working" in t]
        if working_texts:
            working_html = working_texts[0]
            # The full long string must not appear verbatim in the rendered text
            assert "x" * (PREVIEW_MAX_CHARS + 1) not in working_html
            assert "…" in working_html

    async def test_html_special_chars_in_preview_are_escaped(self) -> None:
        """HTML special chars in delta content are escaped in the preview."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        async for _ in channel.deliver(
            _stream({"type": "delta", "content": "<script>alert(1)</script>"}), msg
        ):
            pass

        all_texts = [c.kwargs.get("text", "") for c in bot.edit_message_text.call_args_list]
        # The raw script tag must never appear in any edit
        assert all("<script>" not in t for t in all_texts), (
            f"Unescaped <script> found in edit calls: {all_texts}"
        )
