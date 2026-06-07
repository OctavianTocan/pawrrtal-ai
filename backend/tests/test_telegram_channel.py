"""Tests for the TelegramChannel delivery layer.

Covers:
- ``TelegramChannel.surface`` — correct surface name
- ``TelegramChannel.deliver`` — debounced edit_message_text calls
- ``TelegramChannel.deliver`` — final edit always fired
- ``TelegramChannel.deliver`` — empty stream doesn't edit
- ``TelegramChannel.deliver`` — yields no bytes (side-effect only)
- ``resolve_channel("telegram")`` — registry entry
- ``handle_plain_message`` — unbound user returns string
- ``handle_plain_message`` — bound user returns TelegramTurnContext
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels import registered_surfaces, resolve_channel
from app.channels.base import ChannelMessage
from app.channels.telegram import SURFACE_TELEGRAM, TelegramChannel
from app.channels.telegram.bot import (
    _refresh_telegram_commands_best_effort,
    refresh_telegram_commands,
)
from app.channels.telegram.bot_provider_resolution import (
    resolve_provider_with_auto_clear as _resolve_provider_with_auto_clear,
)
from app.channels.telegram.handlers import (
    TelegramTurnContext,
    handle_plain_message,
    handle_stop_command,
)
from app.channels.telegram.model_command import handle_model_command
from app.channels.telegram.runtime_guards import (
    TelegramPollingLock,
    defer_command_refresh,
    should_refresh_commands,
)
from app.channels.telegram.sender import TelegramSender
from app.channels.telegram.status import (
    _format_duration,
    _format_token_count,
    _render_status_message,
    handle_status_command,
)
from app.conversations.crud import ConversationStatus
from app.providers.base import StreamEvent
from app.providers.catalog import first_catalog_model

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _stream(*events: StreamEvent) -> AsyncIterator[StreamEvent]:
    for event in events:
        yield event


def _make_channel_message(
    bot: AsyncMock,
    chat_id: int = 123,
    message_id: int = 456,
    reply_to_message_id: int | None = None,
) -> ChannelMessage:
    metadata = {
        "bot": bot,
        "chat_id": chat_id,
        "message_id": message_id,
    }
    if reply_to_message_id is not None:
        metadata["reply_to_message_id"] = reply_to_message_id
    return ChannelMessage(
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        text="hello",
        surface="telegram",
        model_id=None,
        metadata=metadata,
    )


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=777))
    return bot


@pytest.fixture(autouse=True)
def _disable_regenerate_button_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep legacy delivery assertions independent of developer env flags."""
    monkeypatch.setattr(
        "app.channels.telegram.channel.settings.telegram_regenerate_button_enabled",
        False,
    )


# ---------------------------------------------------------------------------
# TelegramChannel.surface
# ---------------------------------------------------------------------------


class TestTelegramChannelSurface:
    def test_surface_is_telegram(self) -> None:
        assert TelegramChannel.surface == SURFACE_TELEGRAM
        assert TelegramChannel().surface == "telegram"


# ---------------------------------------------------------------------------
# resolve_channel("telegram")
# ---------------------------------------------------------------------------


class TestTelegramRegistry:
    def test_resolve_returns_telegram_channel(self) -> None:
        ch = resolve_channel("telegram")
        assert isinstance(ch, TelegramChannel)

    def test_registered_surface_included(self) -> None:
        assert "telegram" in registered_surfaces()


# ---------------------------------------------------------------------------
# Bot command publishing
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_refresh_telegram_commands_sets_current_command_menu() -> None:
    bot = AsyncMock()

    await refresh_telegram_commands(bot)

    bot.set_my_commands.assert_awaited_once()
    commands = bot.set_my_commands.await_args.args[0]
    names = [command.command for command in commands]
    assert names == [
        "start",
        "new",
        "model",
        "thinking",
        "config",
        "verbose",
        "stop",
        "status",
        "whoami",
        "lcm",
        "compact",
    ]
    assert all(command.description for command in commands)


@pytest.mark.anyio
async def test_refresh_telegram_commands_best_effort_logs_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bot = AsyncMock()
    bot.set_my_commands.side_effect = RuntimeError("telegram unavailable")

    await _refresh_telegram_commands_best_effort(bot)

    bot.set_my_commands.assert_awaited_once()
    assert "TELEGRAM_COMMANDS_REFRESH_FAILED" in caplog.text


def test_telegram_polling_lock_allows_one_owner() -> None:
    """Only one process can own polling for a bot token at a time."""
    first = TelegramPollingLock(token="test-token")
    second = TelegramPollingLock(token="test-token")
    try:
        assert first.acquire() is True
        assert second.acquire() is False
    finally:
        first.release()
        second.release()


def test_telegram_command_refresh_cooldown() -> None:
    """Command refresh state survives process restarts through a temp marker."""
    token = f"test-token-{uuid.uuid4()}"

    assert should_refresh_commands(token=token, now=100.0) is True
    defer_command_refresh(token=token, seconds=60.0, now=100.0)

    assert should_refresh_commands(token=token, now=159.0) is False
    assert should_refresh_commands(token=token, now=160.0) is True


# ---------------------------------------------------------------------------
# TelegramChannel.deliver — streaming behaviour
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestTelegramChannelDeliver:
    async def test_yields_no_bytes(self) -> None:
        """deliver() must not yield any bytes — it's side-effect only."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()
        chunks = [
            chunk
            async for chunk in channel.deliver(_stream({"type": "delta", "content": "hello"}), msg)
        ]
        assert chunks == []

    async def test_empty_stream_emits_fallback_edit(self) -> None:
        """An empty stream must replace the ⏳ placeholder with a fallback notice.

        Without this, a model turn that produces zero events (rare but real —
        e.g. provider crash before the first chunk) would leave the ⏳ stuck
        in the chat forever and the user would have no signal that the turn
        ended.
        """
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=123, message_id=456)
        channel = TelegramChannel()
        async for _ in channel.deliver(_stream(), msg):
            pass
        # The placeholder is now updated progressively (render_initial first,
        # then the fallback on empty stream).  At least one call must land
        # with the fallback text — check the last call.
        assert bot.edit_message_text.call_count >= 1
        last_call = bot.edit_message_text.call_args_list[-1]
        assert last_call.kwargs["chat_id"] == 123
        assert last_call.kwargs["message_id"] == 456
        assert "agent finished without producing a reply" in last_call.kwargs["text"]

    async def test_final_reply_edited_in_placeholder(self) -> None:
        """Plain answer text is edited in-place inside the placeholder message for pure-text turns."""
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=7, message_id=99)
        channel = TelegramChannel()

        async for _ in channel.deliver(_stream({"type": "delta", "content": "hi"}), msg):
            pass

        bot.delete_message.assert_not_called()
        bot.send_message.assert_not_called()
        bot.edit_message_text.assert_any_call(
            chat_id=7, message_id=99, text="hi", reply_markup=None
        )

    async def test_transient_thinking_updates_placeholder_without_persisted_block(self) -> None:
        """Synthetic provider progress edits the placeholder and stays out of thinking blocks."""
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=7, message_id=99)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {
                "type": "thinking",
                "content": "Preparing the Codex session",
                "summary": True,
                "transient": True,
            },
            {"type": "delta", "content": "hi"},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        edit_texts = [call.kwargs["text"] for call in bot.edit_message_text.call_args_list]
        assert any("Preparing the Codex session" in text for text in edit_texts)
        assert not any("💭 <b>Thinking...</b>" in text for text in edit_texts)
        bot.edit_message_text.assert_any_call(
            chat_id=7, message_id=99, text="hi", reply_markup=None
        )

    async def test_accumulates_deltas_into_final_reply(self) -> None:
        """Multiple deltas collapse into one final Telegram reply edited in-place."""
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=1, message_id=2)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "delta", "content": "Hello"},
            {"type": "delta", "content": ", "},
            {"type": "delta", "content": "world"},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        bot.delete_message.assert_not_called()
        bot.send_message.assert_not_called()
        bot.edit_message_text.assert_any_call(
            chat_id=1, message_id=2, text="Hello, world", reply_markup=None
        )

    async def test_tool_use_edits_detailed_trace_message(self) -> None:
        """``tool_use`` edits the trace with friendly display metadata."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "delta", "content": "answer"},
            {
                "type": "tool_use",
                "name": "search_files",
                "input": {"pattern": "*", "target": "files", "path": "/data/workspace"},
                "display": {
                    "present": '🔎 Searching files for "TelegramChannel"',
                    "compact": "Search files -> TelegramChannel",
                },
            },
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        last_call = bot.edit_message_text.call_args_list[-1]
        trace_text = last_call.kwargs["text"]
        assert "🔎 Searching files for &quot;TelegramChannel&quot;" in trace_text
        assert "/data/workspace" not in trace_text
        bot.send_message.assert_awaited_once_with(chat_id=123, text="answer")

    async def test_thinking_event_renders_as_separate_italic_message(self) -> None:
        """Detailed Telegram verbosity surfaces thinking separately in italics."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "thinking", "content": "checking the workspace"},
            {"type": "delta", "content": "answer"},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        # The placeholder is edited to show the thinking content
        bot.edit_message_text.assert_any_call(
            chat_id=123,
            message_id=456,
            text="💭 <b>Thinking...</b>\n\n<i>checking the workspace</i>",
            reply_markup=None,
        )
        # The final answer is sent as a new message
        bot.send_message.assert_awaited_once_with(
            chat_id=123,
            text="answer",
        )

    async def test_block_transitions_open_new_telegram_messages(self) -> None:
        """Thinking → tools → thinking emits three separate Telegram messages (#288).

        Previously the channel had one ever-growing thinking message and
        one ever-growing tool trace, so block transitions weren't visible
        in chat. The fix tracks ``previous_block_kind`` and opens a new
        Telegram message on every transition.
        """
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=88, message_id=11)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "thinking", "content": "let me check the workspace"},
            {
                "type": "tool_use",
                "name": "read_file",
                "input": {"path": "memory/USER.md"},
            },
            {"type": "thinking", "content": "now I understand"},
            {"type": "delta", "content": "Answer."},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        # The first thinking block edits the placeholder in-place:
        bot.edit_message_text.assert_any_call(
            chat_id=88,
            message_id=11,
            text="💭 <b>Thinking...</b>\n\n<i>let me check the workspace</i>",
            reply_markup=None,
        )

        # The second thinking block and final answer call send_message:
        send_count = bot.send_message.await_count
        assert send_count == 3, f"expected exactly 3 send_message calls, got {send_count}"

        # Get all text sent in send_message calls
        sent_texts = [call.kwargs.get("text", "") for call in bot.send_message.await_args_list]

        # The second thinking message should be sent as a separate message
        thinking_sends = [text for text in sent_texts if text.startswith("💭 <b>Thinking...</b>")]
        assert len(thinking_sends) == 1
        assert "now I understand" in thinking_sends[0]
        assert "let me check the workspace" not in thinking_sends[0]

        # The final answer message should be sent
        assert "Answer." in sent_texts

    async def test_agent_terminated_replaces_placeholder(self) -> None:
        """``agent_terminated`` without text edits placeholder in-place."""
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=11, message_id=22)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {
                "type": "agent_terminated",
                "content": "Agent stopped: hit max_iterations cap of 25.",
            },
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        bot.delete_message.assert_not_called()
        bot.send_message.assert_not_called()
        # Get all text sent in edit_message_text calls
        edit_texts = [call.kwargs.get("text", "") for call in bot.edit_message_text.call_args_list]
        assert any("max_iterations" in text for text in edit_texts)

    async def test_agent_terminated_appended_after_partial_text(self) -> None:
        """If the agent produced text before termination, final reply includes both."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "delta", "content": "Partial answer."},
            {"type": "agent_terminated", "content": "Stopped: max_iterations."},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        bot.delete_message.assert_not_called()
        bot.send_message.assert_not_called()
        edit_texts = [call.kwargs.get("text", "") for call in bot.edit_message_text.call_args_list]
        assert any("Partial answer." in text for text in edit_texts)
        assert any("max_iterations" in text for text in edit_texts)

    async def test_thinking_event_renders_markdown_bold_inside_italic(self) -> None:
        """Thinking deltas with Markdown emphasis render formatted, not literal (#287)."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "thinking", "content": "weighing **bold** and *italic* options"},
            {"type": "delta", "content": "done"},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        # Find the edit call that corresponds to the thinking block
        thinking_edits = [
            call.kwargs["text"]
            for call in bot.edit_message_text.await_args_list
            if "weighing" in call.kwargs.get("text", "")
        ]
        assert len(thinking_edits) > 0
        first_edit = thinking_edits[0]
        # The literal ``**`` markers must not leak into the rendered
        # thinking message — they should be converted to Telegram's
        # ``<b>`` tag while the surrounding italic envelope is preserved.
        assert "**bold**" not in first_edit
        assert "<i>" in first_edit and "</i>" in first_edit
        assert "<b>bold</b>" in first_edit
        # The final answer is sent as a new message
        bot.send_message.assert_awaited_once_with(
            chat_id=123,
            text="done",
        )

    async def test_tool_only_turn_surfaces_fallback_reply(self) -> None:
        """Tool calls without any answer text must produce a closing message (#293).

        Previously the channel would render the tool trace into the
        placeholder and return without sending a final reply, leaving
        the user staring at tool calls and silence. The fix sends the
        empty-stream fallback so every turn ends with a visible
        closing message.
        """
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=42, message_id=99)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {
                "type": "tool_use",
                "name": "read_file",
                "input": {"path": "memory/USER.md"},
            },
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        # Placeholder is repurposed for the tool trace (not deleted, not
        # replaced with the warning).
        bot.delete_message.assert_not_called()
        # A separate fallback reply is sent so the user knows the turn
        # ended.  The exact wording lives in the channel constant.
        bot.send_message.assert_awaited_once()
        text = bot.send_message.await_args.kwargs["text"]
        assert "agent finished without producing a reply" in text

    async def test_error_event_replaces_placeholder(self) -> None:
        """A bare ``error`` event must surface the error text in-place."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "error", "content": "Gemini provider error: rate limited"},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        bot.delete_message.assert_not_called()
        bot.send_message.assert_not_called()
        edit_texts = [call.kwargs.get("text", "") for call in bot.edit_message_text.call_args_list]
        assert any("rate limited" in text for text in edit_texts)

    async def test_final_reply_uses_reply_parameters_when_available(self) -> None:
        """Telegram final replies thread under the original user message when a new message is sent."""
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=1, message_id=2, reply_to_message_id=44)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "thinking", "content": "thought"},
            {"type": "delta", "content": "answer"},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        kwargs = bot.send_message.await_args.kwargs
        assert kwargs["reply_parameters"].message_id == 44

    async def test_regenerate_button_attached_to_final_reply_when_flag_on(self) -> None:
        """When the regenerate flag is on, the closing edit carries the rgn:<uuid> markup (#368)."""
        from aiogram.types import InlineKeyboardMarkup

        from app.channels.telegram.regenerate_keyboard import REGEN_CALLBACK_PREFIX

        bot = _make_bot()
        conversation_id = uuid.uuid4()
        msg = ChannelMessage(
            user_id=uuid.uuid4(),
            conversation_id=conversation_id,
            text="hi",
            surface="telegram",
            model_id=None,
            metadata={"bot": bot, "chat_id": 1, "message_id": 2},
        )
        channel = TelegramChannel()
        with patch(
            "app.channels.telegram.channel.settings.telegram_regenerate_button_enabled", True
        ):
            async for _ in channel.deliver(_stream({"type": "delta", "content": "answer"}), msg):
                pass

        bot.delete_message.assert_not_called()
        bot.send_message.assert_not_called()
        last_edit_call = bot.edit_message_text.call_args_list[-1]
        markup = last_edit_call.kwargs.get("reply_markup")
        assert isinstance(markup, InlineKeyboardMarkup)
        # The lone button row encodes the conversation_id behind the rgn prefix
        # so the callback handler can replay the last user message.
        button = markup.inline_keyboard[0][0]
        assert button.callback_data == f"{REGEN_CALLBACK_PREFIX}{conversation_id}"

    async def test_regenerate_button_omitted_when_flag_off(self) -> None:
        """The default behaviour is unchanged — no inline keyboard is attached."""
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=1, message_id=2)
        channel = TelegramChannel()
        with patch(
            "app.channels.telegram.channel.settings.telegram_regenerate_button_enabled", False
        ):
            async for _ in channel.deliver(_stream({"type": "delta", "content": "answer"}), msg):
                pass

        bot.delete_message.assert_not_called()
        bot.send_message.assert_not_called()
        last_edit_call = bot.edit_message_text.call_args_list[-1]
        assert (
            "reply_markup" not in last_edit_call.kwargs
            or last_edit_call.kwargs["reply_markup"] is None
        )

    async def test_not_modified_error_swallowed(self) -> None:
        """TelegramBadRequest: message is not modified must not propagate."""
        from aiogram.exceptions import TelegramBadRequest

        bot = _make_bot()
        bot.edit_message_text.side_effect = TelegramBadRequest(
            method=MagicMock(),
            message="message is not modified",
        )
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        # Should not raise.
        async for _ in channel.deliver(
            _stream({"type": "tool_use", "name": "read_file", "input": {"path": "a.txt"}}), msg
        ):
            pass

    async def test_other_errors_logged_not_raised(self) -> None:
        """Network or API errors should log a warning but not crash the turn."""
        from aiogram.exceptions import TelegramNetworkError

        bot = _make_bot()
        bot.edit_message_text.side_effect = TelegramNetworkError(
            method=MagicMock(),
            message="network timeout",
        )
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        async for _ in channel.deliver(
            _stream({"type": "tool_use", "name": "read_file", "input": {"path": "a.txt"}}), msg
        ):
            pass  # Must not raise

    async def test_thinking_promoted_over_leading_delta_events(self) -> None:
        """A thinking event must override/promote over leading delta/whitespace events.

        If a model returns a leading newline or whitespace delta before it emits
        thinking events, the placeholder should NOT be deleted at the end of
        the turn. The thinking block should take precedence.
        """
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=42, message_id=99)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "delta", "content": "\n"},
            {"type": "thinking", "content": "thinking content"},
            {"type": "delta", "content": "actual answer"},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        # The placeholder message (99) should be edited with the thinking trace:
        bot.edit_message_text.assert_any_call(
            chat_id=42,
            message_id=99,
            text="💭 <b>Thinking...</b>\n\n<i>thinking content</i>",
            reply_markup=None,
        )
        # And the placeholder MUST NOT be deleted:
        bot.delete_message.assert_not_called()
        # The final answer is sent as a new message:
        bot.send_message.assert_awaited_once()
        sent_texts = [call.kwargs.get("text", "") for call in bot.send_message.await_args_list]
        assert "actual answer" in sent_texts

    async def test_thinking_concatenates_stream_without_strip_or_newlines(self) -> None:
        """Thinking deltas must be concatenated exactly as-is, preserving spaces/formatting.

        Verifies that we don't call strip() or insert newlines between streaming thinking
        tokens, so the thinking trace reads naturally as one block of text.
        """
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=42, message_id=99)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "thinking", "content": "The"},
            {"type": "thinking", "content": " user"},
            {"type": "thinking", "content": " said"},
            {"type": "thinking", "content": "\n"},
            {"type": "thinking", "content": "hello."},
            {"type": "delta", "content": "done"},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        # The thinking text should be concatenated properly with spacing intact:
        bot.edit_message_text.assert_any_call(
            chat_id=42,
            message_id=99,
            text="💭 <b>Thinking...</b>\n\n<i>The user said\nhello.</i>",
            reply_markup=None,
        )


# ---------------------------------------------------------------------------
# handle_plain_message
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestHandlePlainMessage:
    async def test_unbound_user_returns_string(self) -> None:
        """An unknown external_user_id must return the not-bound nudge string."""
        sender = TelegramSender(user_id=999, chat_id=999, username=None, full_name="Stranger")
        session = AsyncMock()
        with patch(
            "app.channels.telegram.handlers.resolve_or_autolink_telegram_user",
            new=AsyncMock(return_value=None),
        ):
            result = await handle_plain_message(sender=sender, text="hello", session=session)
        assert isinstance(result, str)
        assert "don't recognize" in result.lower() or "connect" in result.lower()

    async def test_bound_user_returns_turn_context(self) -> None:
        """A known user must get a TelegramTurnContext with correct fields."""
        pawrrtal_uid = uuid.uuid4()
        conv_id = uuid.uuid4()
        sender = TelegramSender(user_id=42, chat_id=42, username="tavi", full_name="Tavi")
        session = AsyncMock()

        # Fake conversation row with no model override.
        fake_conv = AsyncMock()
        fake_conv.id = conv_id
        fake_conv.model_id = None

        with (
            patch(
                "app.channels.telegram.handlers.resolve_or_autolink_telegram_user",
                new=AsyncMock(return_value=pawrrtal_uid),
            ),
            patch(
                "app.channels.telegram.handlers.get_or_create_telegram_conversation_full",
                new=AsyncMock(return_value=fake_conv),
            ),
            patch(
                "app.channels.telegram.handlers.resolve_effective_model_id",
                new=MagicMock(
                    side_effect=lambda *, conversation_model_id: (
                        conversation_model_id or "agent-sdk:anthropic/claude-sonnet-4-6"
                    )
                ),
            ),
        ):
            result = await handle_plain_message(sender=sender, text="what is RAG?", session=session)

        assert isinstance(result, TelegramTurnContext)
        assert result.pawrrtal_user_id == pawrrtal_uid
        assert result.conversation_id == conv_id
        assert isinstance(result.model_id, str)

    async def test_bound_user_uses_conversation_model_override(self) -> None:
        """When conversation.model_id is set it must propagate into the context."""
        pawrrtal_uid = uuid.uuid4()
        conv_id = uuid.uuid4()
        sender = TelegramSender(user_id=42, chat_id=42, username="tavi", full_name="Tavi")
        session = AsyncMock()

        fake_conv = AsyncMock()
        fake_conv.id = conv_id
        fake_conv.model_id = "anthropic/claude-opus-4-5"

        with (
            patch(
                "app.channels.telegram.handlers.resolve_or_autolink_telegram_user",
                new=AsyncMock(return_value=pawrrtal_uid),
            ),
            patch(
                "app.channels.telegram.handlers.get_or_create_telegram_conversation_full",
                new=AsyncMock(return_value=fake_conv),
            ),
            patch(
                "app.channels.telegram.handlers.resolve_effective_model_id",
                new=MagicMock(
                    side_effect=lambda *, conversation_model_id: (
                        conversation_model_id or "agent-sdk:anthropic/claude-sonnet-4-6"
                    )
                ),
            ),
        ):
            result = await handle_plain_message(sender=sender, text="hey", session=session)

        assert isinstance(result, TelegramTurnContext)
        assert result.model_id == "anthropic/claude-opus-4-5"

    async def test_bound_user_falls_back_to_resolved_model(self) -> None:
        """Without a conversation override, the resolver's fallback propagates.

        The catalog default is the last-resort fallback; whatever
        ``resolve_effective_model_id`` returns for a conversation with no
        override must propagate into the turn context.
        """
        pawrrtal_uid = uuid.uuid4()
        sender = TelegramSender(user_id=99, chat_id=99, username="t", full_name="T")
        session = AsyncMock()

        fake_conv = AsyncMock()
        fake_conv.id = uuid.uuid4()
        fake_conv.model_id = None

        with (
            patch(
                "app.channels.telegram.handlers.resolve_or_autolink_telegram_user",
                new=AsyncMock(return_value=pawrrtal_uid),
            ),
            patch(
                "app.channels.telegram.handlers.get_or_create_telegram_conversation_full",
                new=AsyncMock(return_value=fake_conv),
            ),
            patch(
                "app.channels.telegram.handlers.resolve_effective_model_id",
                new=MagicMock(return_value="agent-sdk:anthropic/claude-opus-4-5"),
            ),
        ):
            result = await handle_plain_message(sender=sender, text="hey", session=session)

        assert isinstance(result, TelegramTurnContext)
        assert result.model_id == "agent-sdk:anthropic/claude-opus-4-5"


# ---------------------------------------------------------------------------
# handle_stop_command
# ---------------------------------------------------------------------------


class TestHandleStopCommand:
    """handle_stop_command is a plain synchronous function — no anyio needed."""

    def test_stop_with_running_task(self) -> None:
        """Returns the 'stopped' message when was_running=True."""
        reply = handle_stop_command(was_running=True)
        assert "⏹" in reply or "stop" in reply.lower()

    def test_stop_with_no_running_task(self) -> None:
        """Returns the 'nothing running' message when was_running=False."""
        reply = handle_stop_command(was_running=False)
        assert "nothing" in reply.lower() or "running" in reply.lower()

    def test_stop_returns_string(self) -> None:
        """handle_stop_command always returns a plain string."""
        for flag in (True, False):
            assert isinstance(handle_stop_command(was_running=flag), str)


# ---------------------------------------------------------------------------
# handle_model_command
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestHandleModelCommand:
    async def test_missing_model_arg_returns_usage(self) -> None:
        """Calling /model with no argument returns the usage hint."""
        sender = TelegramSender(user_id=1, chat_id=1, username=None, full_name=None)
        session = AsyncMock()
        reply = await handle_model_command(sender=sender, model_arg="", session=session)
        assert "usage" in reply.lower() or "/model" in reply.lower()

    async def test_model_command_rejects_malformed_input(self) -> None:
        """/model bogus -> user-facing structural error, nothing stored.

        The parse-on-write path uses ``parse_model_id`` directly, so any
        string that doesn't match ``[host:]vendor/model`` is rejected
        before any DB lookup or update.  This is the catalog-ignorant
        gate documented in ADR 2026-05-14 §7.
        """
        sender = TelegramSender(user_id=1, chat_id=1, username=None, full_name=None)
        session = AsyncMock()
        update_mock = AsyncMock(return_value=True)
        with (
            patch(
                "app.channels.telegram.model_command.resolve_or_autolink_telegram_user",
                new=AsyncMock(return_value=uuid.uuid4()),
            ),
            patch(
                "app.channels.telegram.model_command.update_conversation_model",
                new=update_mock,
            ),
        ):
            reply = await handle_model_command(sender=sender, model_arg="bogus", session=session)
        assert isinstance(reply, str)
        assert "✅" not in reply
        assert "bogus" in reply  # the raw input must appear in the rejection
        update_mock.assert_not_called()

    async def test_unbound_user_returns_error(self) -> None:
        """An unbound sender cannot switch models."""
        sender = TelegramSender(user_id=2, chat_id=2, username=None, full_name=None)
        session = AsyncMock()
        with patch(
            "app.channels.telegram.model_command.resolve_or_autolink_telegram_user",
            new=AsyncMock(return_value=None),
        ):
            reply = await handle_model_command(
                sender=sender,
                model_arg="google/gemini-3-flash-preview",
                session=session,
            )
        assert isinstance(reply, str)
        assert "connect" in reply.lower() or "account" in reply.lower()

    async def test_model_command_rejects_unknown_catalog_model(self) -> None:
        """A structurally valid model outside the catalog is rejected before write."""
        sender = TelegramSender(user_id=22, chat_id=22, username=None, full_name=None)
        session = AsyncMock()
        update_mock = AsyncMock(return_value=True)
        with (
            patch(
                "app.channels.telegram.model_command.resolve_or_autolink_telegram_user",
                new=AsyncMock(return_value=uuid.uuid4()),
            ),
            patch(
                "app.channels.telegram.model_command.update_conversation_model",
                new=update_mock,
            ),
        ):
            reply = await handle_model_command(
                sender=sender,
                model_arg="google/not-a-real-model",
                session=session,
            )

        assert "catalog" in reply.lower()
        assert "/model" in reply  # /models was removed; /model with no args opens picker
        update_mock.assert_not_called()

    async def test_model_command_stores_canonical_form_for_well_formed_input(
        self,
    ) -> None:
        """/model anthropic/claude-sonnet-4-6 stores agent-sdk:anthropic/claude-sonnet-4-6.

        The handler runs ``parse_model_id`` and writes ``parsed.id`` (the
        fully-qualified ``host:vendor/model`` form), regardless of whether
        the user typed the host prefix.  This is the only remaining write
        path in the backend that bypasses the Pydantic boundary, so the
        canonical form is enforced explicitly here.
        """
        pawrrtal_uid = uuid.uuid4()
        conv_id = uuid.uuid4()
        sender = TelegramSender(user_id=3, chat_id=3, username="t", full_name="T")
        session = AsyncMock()

        fake_conv = AsyncMock()
        fake_conv.id = conv_id
        fake_conv.model_id = None

        update_mock = AsyncMock(return_value=True)
        with (
            patch(
                "app.channels.telegram.model_command.resolve_or_autolink_telegram_user",
                new=AsyncMock(return_value=pawrrtal_uid),
            ),
            patch(
                "app.channels.telegram.model_command.get_or_create_telegram_conversation_full",
                new=AsyncMock(return_value=fake_conv),
            ),
            patch(
                "app.channels.telegram.model_command.update_conversation_model",
                new=update_mock,
            ),
        ):
            reply = await handle_model_command(
                sender=sender,
                model_arg="anthropic/claude-sonnet-4-6",
                session=session,
            )

        canonical_id = "agent-sdk:anthropic/claude-sonnet-4-6"
        assert canonical_id in reply
        assert "✅" in reply
        # The persisted value must be the canonical fully-qualified form.
        update_mock.assert_called_once()
        assert update_mock.call_args.kwargs["model_id"] == canonical_id

    async def test_update_failure_returns_error_message(self) -> None:
        """When the DB update fails the user gets an error string, not an exception."""
        pawrrtal_uid = uuid.uuid4()
        conv_id = uuid.uuid4()
        sender = TelegramSender(user_id=4, chat_id=4, username="t", full_name="T")
        session = AsyncMock()

        fake_conv = AsyncMock()
        fake_conv.id = conv_id
        fake_conv.model_id = None

        with (
            patch(
                "app.channels.telegram.model_command.resolve_or_autolink_telegram_user",
                new=AsyncMock(return_value=pawrrtal_uid),
            ),
            patch(
                "app.channels.telegram.model_command.get_or_create_telegram_conversation_full",
                new=AsyncMock(return_value=fake_conv),
            ),
            patch(
                "app.channels.telegram.model_command.update_conversation_model",
                new=AsyncMock(return_value=False),
            ),
        ):
            reply = await handle_model_command(
                sender=sender,
                model_arg="google/gemini-3-flash-preview",
                session=session,
            )

        assert isinstance(reply, str)
        assert "couldn't" in reply.lower() or "fail" in reply.lower() or "try" in reply.lower()

    async def test_valid_model_after_clear_restores_user_choice(self) -> None:
        """User can re-set with a known /model after the auto-clear path fired.

        The auto-clear path in ``bot.py`` writes ``model_id = NULL``; this
        test exercises the *follow-up* ``/model`` call that the user issues
        next to pick a known model.  It must persist the new canonical
        form unchanged — proving the auto-clear didn't break the write path.
        """
        pawrrtal_uid = uuid.uuid4()
        conv_id = uuid.uuid4()
        sender = TelegramSender(user_id=5, chat_id=5, username="t", full_name="T")
        session = AsyncMock()

        # The auto-clear has already happened, so the stored value is NULL.
        fake_conv = AsyncMock()
        fake_conv.id = conv_id
        fake_conv.model_id = None

        update_mock = AsyncMock(return_value=True)
        with (
            patch(
                "app.channels.telegram.model_command.resolve_or_autolink_telegram_user",
                new=AsyncMock(return_value=pawrrtal_uid),
            ),
            patch(
                "app.channels.telegram.model_command.get_or_create_telegram_conversation_full",
                new=AsyncMock(return_value=fake_conv),
            ),
            patch(
                "app.channels.telegram.model_command.update_conversation_model",
                new=update_mock,
            ),
        ):
            reply = await handle_model_command(
                sender=sender,
                model_arg="agent-sdk:anthropic/claude-haiku-4-5",
                session=session,
            )

        canonical_id = "agent-sdk:anthropic/claude-haiku-4-5"
        assert canonical_id in reply
        assert "✅" in reply
        update_mock.assert_called_once()
        assert update_mock.call_args.kwargs["model_id"] == canonical_id


# ---------------------------------------------------------------------------
# Bot adapter — _resolve_provider_with_auto_clear safety net
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestResolveProviderWithAutoClear:
    """Cover the chat-turn safety net that catches unknown/malformed stored IDs.

    The handler in :mod:`app.channels.telegram.bot` wraps the
    ``resolve_llm`` call so that an unknown-but-well-formed stored model
    surfaces an immediate user-facing warning, clears the stored value,
    and still completes the current turn using the catalog default.

    These tests mock ``async_session_maker`` and ``resolve_llm`` so the
    branching is exercised without spinning up the DB or the providers.
    """

    @staticmethod
    def _make_context(model_id: str) -> TelegramTurnContext:
        return TelegramTurnContext(
            pawrrtal_user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            model_id=model_id,
            thread_id=None,
        )

    async def test_chat_turn_auto_clears_unknown_stored_model(self) -> None:
        """A well-formed-but-unknown stored ID triggers the auto-clear path.

        - ``_resolve_provider_with_auto_clear`` returns the catalog
          default's provider for *this* turn,
        - it surfaces a warning string the caller forwards to the user,
        - it calls ``update_conversation_model`` with ``model_id=None`` so
          the stored row is cleared.
        """
        context = self._make_context("agent-sdk:anthropic/claude-nonexistent")

        fake_default_provider = MagicMock(name="default_provider")
        update_mock = AsyncMock(return_value=True)
        # ``resolve_llm`` is a sync function — use MagicMock, not AsyncMock.
        resolve_mock = MagicMock(side_effect=[fake_default_provider])

        # ``async_session_maker`` is used as an async context manager.
        fake_session = AsyncMock()
        fake_session_maker = MagicMock()
        fake_session_maker.return_value.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "app.channels.telegram.bot_provider_resolution.resolve_llm",
                new=resolve_mock,
            ),
            patch(
                "app.channels.telegram.bot_provider_resolution.update_conversation_model",
                new=update_mock,
            ),
            patch(
                "app.channels.telegram.bot_provider_resolution.async_session_maker",
                new=fake_session_maker,
            ),
        ):
            provider, warning = await _resolve_provider_with_auto_clear(context)

        # Warning was produced and mentions the bad ID + the fallback.
        assert warning is not None
        assert "agent-sdk:anthropic/claude-nonexistent" in warning
        assert first_catalog_model().id in warning

        # Stored model_id was cleared to NULL.
        update_mock.assert_awaited_once()
        assert update_mock.await_args is not None
        assert update_mock.await_args.kwargs["model_id"] is None
        assert update_mock.await_args.kwargs["conversation_id"] == context.conversation_id

        # resolve_llm was called *once* — only for the catalog fallback.
        # (For the unknown path ``require_known()`` raises first, so
        # ``resolve_llm`` is only invoked for the fallback.)
        assert resolve_mock.call_count == 1
        fallback_call = resolve_mock.call_args
        assert fallback_call.args[0] == first_catalog_model().id
        assert provider is fake_default_provider

    async def test_following_turn_uses_catalog_default_after_clear(self) -> None:
        """After the auto-clear, a turn with ``model_id=None`` resolves cleanly.

        ``handle_plain_message`` reads ``conversation.model_id`` and falls
        back to ``first_catalog_model().id`` when it is ``NULL``.  Here we
        simulate that follow-up turn: the resolved context carries the
        first catalog entry directly, and the helper neither warns nor clears.
        """
        context = self._make_context(first_catalog_model().id)

        fake_default_provider = MagicMock(name="default_provider")
        update_mock = AsyncMock(return_value=True)
        resolve_mock = MagicMock(side_effect=[fake_default_provider])

        with (
            patch(
                "app.channels.telegram.bot_provider_resolution.resolve_llm",
                new=resolve_mock,
            ),
            patch(
                "app.channels.telegram.bot_provider_resolution.update_conversation_model",
                new=update_mock,
            ),
        ):
            provider, warning = await _resolve_provider_with_auto_clear(context)

        # Clean path: no warning, no clear.
        assert warning is None
        update_mock.assert_not_awaited()

        # resolve_llm was called exactly once with the stored canonical ID.
        assert resolve_mock.call_count == 1
        assert resolve_mock.call_args.args[0] == first_catalog_model().id
        assert provider is fake_default_provider


# ---------------------------------------------------------------------------
# handle_status_command + formatter helpers
# ---------------------------------------------------------------------------


class TestStatusFormatters:
    def test_format_duration_buckets(self) -> None:
        assert _format_duration(0) == "0s"
        assert _format_duration(45) == "45s"
        assert _format_duration(125) == "2m 5s"
        assert _format_duration(4 * 3600 + 12 * 60) == "4h 12m"
        assert _format_duration(3 * 86_400 + 3600) == "3d 1h"

    def test_format_duration_clamps_negative(self) -> None:
        assert _format_duration(-1) == "0s"

    def test_format_token_count(self) -> None:
        assert _format_token_count(0) == "0"
        assert _format_token_count(18_420) == "18,420"
        assert _format_token_count(-5) == "0"


class TestRenderStatusMessage:
    def _status(self) -> ConversationStatus:
        from datetime import UTC
        from datetime import datetime as _dt

        return ConversationStatus(
            conversation_id=uuid.uuid4(),
            model_id=first_catalog_model().id,
            verbose_level=1,
            reasoning_effort=None,
            started_at=_dt(2026, 5, 17, 18, 0, tzinfo=UTC),
            message_count=14,
            user_message_count=7,
            assistant_message_count=7,
            total_input_tokens=18_420,
            total_output_tokens=6_108,
            total_cost_usd=0.0,
        )

    def test_renders_known_model_without_warning(self) -> None:
        from datetime import UTC
        from datetime import datetime as _dt

        rendered = _render_status_message(
            bot_uptime_seconds=4 * 3600 + 12 * 60,
            status=self._status(),
            run_active=False,
            thread_id=None,
            now=_dt(2026, 5, 17, 20, 3, tzinfo=UTC),
        )
        assert "4h 12m" in rendered
        assert "18,420 in / 6,108 out" in rendered
        assert "idle" in rendered
        assert "⚠️" not in rendered
        assert "Topic thread" not in rendered

    def test_tokens_line_says_na_when_messages_exist_without_usage(self) -> None:
        """When cost_ledger has no rows for a conversation but ChatMessages do.

        This happens whenever a provider that doesn't emit ``usage`` events
        is the only one talking on a conversation (e.g. Gemini today). The
        token line must NOT render as "0 in / 0 out" since that implies a
        measurement of zero rather than the absence of measurement.
        """
        from datetime import UTC
        from datetime import datetime as _dt

        status = ConversationStatus(
            conversation_id=uuid.uuid4(),
            model_id=first_catalog_model().id,
            verbose_level=1,
            reasoning_effort=None,
            started_at=_dt(2026, 5, 17, 18, 0, tzinfo=UTC),
            message_count=48,
            user_message_count=24,
            assistant_message_count=24,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=0.0,
        )
        rendered = _render_status_message(
            bot_uptime_seconds=60,
            status=status,
            run_active=False,
            thread_id=None,
            now=_dt(2026, 5, 17, 20, 0, tzinfo=UTC),
        )
        assert "n/a (provider did not report usage)" in rendered
        assert "0 in / 0 out" not in rendered

    def test_tokens_line_stays_zero_for_empty_conversation(self) -> None:
        """An empty conversation (no messages yet) renders "0 in / 0 out".

        Distinct from the "n/a" case above: here there's genuinely nothing
        to measure, so the zero is honest.
        """
        from datetime import UTC
        from datetime import datetime as _dt

        status = ConversationStatus(
            conversation_id=uuid.uuid4(),
            model_id=first_catalog_model().id,
            verbose_level=1,
            reasoning_effort=None,
            started_at=_dt(2026, 5, 17, 18, 0, tzinfo=UTC),
            message_count=0,
            user_message_count=0,
            assistant_message_count=0,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=0.0,
        )
        rendered = _render_status_message(
            bot_uptime_seconds=60,
            status=status,
            run_active=False,
            thread_id=None,
            now=_dt(2026, 5, 17, 18, 1, tzinfo=UTC),
        )
        assert "0 in / 0 out" in rendered

    def test_renders_unknown_model_with_warning(self) -> None:
        from datetime import UTC
        from datetime import datetime as _dt

        status = ConversationStatus(
            conversation_id=uuid.uuid4(),
            model_id="agent-sdk:anthropic/claude-removed-from-catalog",
            verbose_level=None,
            reasoning_effort=None,
            started_at=_dt(2026, 5, 17, 19, 0, tzinfo=UTC),
            message_count=2,
            user_message_count=1,
            assistant_message_count=1,
            total_input_tokens=100,
            total_output_tokens=50,
            total_cost_usd=0.0,
        )
        rendered = _render_status_message(
            bot_uptime_seconds=60,
            status=status,
            run_active=True,
            thread_id=None,
            now=_dt(2026, 5, 17, 19, 1, tzinfo=UTC),
        )
        assert "⚠️" in rendered
        assert "running" in rendered
        # Verbose level falls back to the configured Telegram default when None.
        from app.infrastructure.config import settings

        assert f"Verbose: {settings.telegram_verbose_default}" in rendered

    def test_handles_tz_naive_started_at_from_db(self) -> None:
        """Regression: ``Conversation.created_at`` is tz-naive in the DB.

        Before normalization the renderer raised ``TypeError: can't subtract
        offset-naive and offset-aware datetimes`` against any real prod row.
        """
        from datetime import UTC
        from datetime import datetime as _dt

        status = ConversationStatus(
            conversation_id=uuid.uuid4(),
            model_id=first_catalog_model().id,
            verbose_level=1,
            reasoning_effort=None,
            started_at=_dt(2026, 5, 17, 18, 0),  # tz-naive, matches DB
            message_count=1,
            user_message_count=1,
            assistant_message_count=0,
            total_input_tokens=10,
            total_output_tokens=5,
            total_cost_usd=0.0,
        )
        rendered = _render_status_message(
            bot_uptime_seconds=60,
            status=status,
            run_active=False,
            thread_id=None,
            now=_dt(2026, 5, 17, 20, 12, tzinfo=UTC),
        )
        assert "Started: 2h 12m ago" in rendered

    def test_topic_thread_line_appears_when_set(self) -> None:
        from datetime import UTC
        from datetime import datetime as _dt

        rendered = _render_status_message(
            bot_uptime_seconds=10,
            status=self._status(),
            run_active=False,
            thread_id=42,
            now=_dt(2026, 5, 17, 20, 0, tzinfo=UTC),
        )
        assert "Topic thread" in rendered
        assert "42" in rendered


@pytest.mark.anyio
class TestHandleStatusCommand:
    async def test_unbound_user_returns_connect_nudge(self) -> None:
        sender = TelegramSender(user_id=1, chat_id=1, username=None, full_name=None)
        session = AsyncMock()
        with patch(
            "app.channels.telegram.status.get_user_id_for_external",
            new=AsyncMock(return_value=None),
        ):
            reply = await handle_status_command(
                sender=sender,
                session=session,
                bot_uptime_seconds=0.0,
                is_chat_run_active=lambda _: False,
            )
        assert "connect" in reply.lower()

    async def test_bound_user_renders_status_with_run_state(self) -> None:
        pawrrtal_uid = uuid.uuid4()
        conv_id = uuid.uuid4()
        sender = TelegramSender(user_id=9, chat_id=9, username="t", full_name="T")
        session = AsyncMock()

        fake_conv = MagicMock()
        fake_conv.id = conv_id

        from datetime import UTC
        from datetime import datetime as _dt

        fake_status = ConversationStatus(
            conversation_id=conv_id,
            model_id=first_catalog_model().id,
            verbose_level=2,
            reasoning_effort=None,
            started_at=_dt(2026, 5, 17, 18, 0, tzinfo=UTC),
            message_count=3,
            user_message_count=2,
            assistant_message_count=1,
            total_input_tokens=900,
            total_output_tokens=200,
            total_cost_usd=0.0,
        )

        with (
            patch(
                "app.channels.telegram.status.get_user_id_for_external",
                new=AsyncMock(return_value=pawrrtal_uid),
            ),
            patch(
                "app.channels.telegram.status.get_or_create_telegram_conversation_full",
                new=AsyncMock(return_value=fake_conv),
            ),
            patch(
                # Phase 2: ``get_conversation_status`` returns the status DTO directly.
                "app.channels.telegram.status.get_conversation_status",
                new=AsyncMock(return_value=fake_status),
            ),
        ):
            reply = await handle_status_command(
                sender=sender,
                session=session,
                bot_uptime_seconds=125.0,
                is_chat_run_active=lambda chat_id: chat_id == 9,
            )

        assert "2m 5s" in reply
        assert "running" in reply
        assert "Verbose: 2 (detailed)" in reply
        assert "900 in / 200 out" in reply
