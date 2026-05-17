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
from app.core.providers.base import StreamEvent
from app.core.providers.catalog import default_model
from app.integrations.telegram.bot import (
    _refresh_telegram_commands_best_effort,
    refresh_telegram_commands,
)
from app.integrations.telegram.bot_provider_resolution import (
    resolve_provider_with_auto_clear as _resolve_provider_with_auto_clear,
)
from app.integrations.telegram.handlers import (
    TelegramSender,
    TelegramTurnContext,
    handle_model_command,
    handle_plain_message,
    handle_stop_command,
)

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
    assert names == ["start", "new", "model", "models", "verbose", "stop"]
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
        bot.edit_message_text.assert_called_once()
        call = bot.edit_message_text.call_args
        assert call.kwargs["chat_id"] == 123
        assert call.kwargs["message_id"] == 456
        assert "agent finished without producing any text" in call.kwargs["text"]

    async def test_final_reply_sent_as_separate_message(self) -> None:
        """Plain answer text is sent as a final reply, not streamed into the trace."""
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=7, message_id=99)
        channel = TelegramChannel()

        async for _ in channel.deliver(_stream({"type": "delta", "content": "hi"}), msg):
            pass

        bot.delete_message.assert_awaited_once_with(chat_id=7, message_id=99)
        bot.send_message.assert_awaited_once_with(chat_id=7, text="hi")
        bot.edit_message_text.assert_not_called()

    async def test_accumulates_deltas_into_final_reply(self) -> None:
        """Multiple deltas collapse into one final Telegram reply."""
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

        bot.delete_message.assert_awaited_once_with(chat_id=1, message_id=2)
        bot.send_message.assert_awaited_once_with(chat_id=1, text="Hello, world")

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

        first_send = bot.send_message.await_args_list[0].kwargs
        assert first_send["text"] == "<i>checking the workspace</i>"
        final_send = bot.send_message.await_args_list[-1].kwargs
        assert final_send["text"] == "answer"

    async def test_agent_terminated_replaces_placeholder(self) -> None:
        """``agent_terminated`` without text must send a final warning reply."""
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

        bot.delete_message.assert_awaited_once_with(chat_id=11, message_id=22)
        bot.send_message.assert_awaited_once()
        text = bot.send_message.await_args.kwargs["text"]
        assert "max_iterations" in text
        assert bot.send_message.await_args.kwargs["chat_id"] == 11

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

        last_text = bot.send_message.await_args.kwargs["text"]
        assert "Partial answer." in last_text
        assert "max_iterations" in last_text

    async def test_error_event_replaces_placeholder(self) -> None:
        """A bare ``error`` event must surface the error text as final reply."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "error", "content": "Gemini provider error: rate limited"},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        bot.delete_message.assert_awaited_once()
        assert "rate limited" in bot.send_message.await_args.kwargs["text"]

    async def test_final_reply_uses_reply_parameters_when_available(self) -> None:
        """Telegram final replies thread under the original user message."""
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=1, message_id=2, reply_to_message_id=44)
        channel = TelegramChannel()

        async for _ in channel.deliver(_stream({"type": "delta", "content": "answer"}), msg):
            pass

        kwargs = bot.send_message.await_args.kwargs
        assert kwargs["reply_parameters"].message_id == 44

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
            "app.integrations.telegram.handlers.get_user_id_for_external",
            new=AsyncMock(return_value=None),
        ):
            result = await handle_plain_message(sender=sender, text="hello", session=session)
        assert isinstance(result, str)
        assert "don't recognize" in result.lower() or "connect" in result.lower()

    async def test_bound_user_returns_turn_context(self) -> None:
        """A known user must get a TelegramTurnContext with correct fields."""
        nexus_uid = uuid.uuid4()
        conv_id = uuid.uuid4()
        sender = TelegramSender(user_id=42, chat_id=42, username="tavi", full_name="Tavi")
        session = AsyncMock()

        # Fake conversation row with no model override.
        fake_conv = AsyncMock()
        fake_conv.id = conv_id
        fake_conv.model_id = None

        with (
            patch(
                "app.integrations.telegram.handlers.get_user_id_for_external",
                new=AsyncMock(return_value=nexus_uid),
            ),
            patch(
                "app.integrations.telegram.handlers.get_or_create_telegram_conversation_full",
                new=AsyncMock(return_value=fake_conv),
            ),
        ):
            result = await handle_plain_message(sender=sender, text="what is RAG?", session=session)

        assert isinstance(result, TelegramTurnContext)
        assert result.nexus_user_id == nexus_uid
        assert result.conversation_id == conv_id
        assert isinstance(result.model_id, str)

    async def test_bound_user_uses_conversation_model_override(self) -> None:
        """When conversation.model_id is set it must propagate into the context."""
        nexus_uid = uuid.uuid4()
        conv_id = uuid.uuid4()
        sender = TelegramSender(user_id=42, chat_id=42, username="tavi", full_name="Tavi")
        session = AsyncMock()

        fake_conv = AsyncMock()
        fake_conv.id = conv_id
        fake_conv.model_id = "anthropic/claude-opus-4-5"

        with (
            patch(
                "app.integrations.telegram.handlers.get_user_id_for_external",
                new=AsyncMock(return_value=nexus_uid),
            ),
            patch(
                "app.integrations.telegram.handlers.get_or_create_telegram_conversation_full",
                new=AsyncMock(return_value=fake_conv),
            ),
        ):
            result = await handle_plain_message(sender=sender, text="hey", session=session)

        assert isinstance(result, TelegramTurnContext)
        assert result.model_id == "anthropic/claude-opus-4-5"


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
                "app.integrations.telegram.handlers.get_user_id_for_external",
                new=AsyncMock(return_value=uuid.uuid4()),
            ),
            patch(
                "app.integrations.telegram.handlers.update_conversation_model",
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
            "app.integrations.telegram.handlers.get_user_id_for_external",
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
        with patch(
            "app.integrations.telegram.handlers.update_conversation_model",
            new=update_mock,
        ):
            reply = await handle_model_command(
                sender=sender,
                model_arg="google/not-a-real-model",
                session=session,
            )

        assert "catalog" in reply.lower()
        assert "/models" in reply
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
        nexus_uid = uuid.uuid4()
        conv_id = uuid.uuid4()
        sender = TelegramSender(user_id=3, chat_id=3, username="t", full_name="T")
        session = AsyncMock()

        fake_conv = AsyncMock()
        fake_conv.id = conv_id
        fake_conv.model_id = None

        update_mock = AsyncMock(return_value=True)
        with (
            patch(
                "app.integrations.telegram.handlers.get_user_id_for_external",
                new=AsyncMock(return_value=nexus_uid),
            ),
            patch(
                "app.integrations.telegram.handlers.get_or_create_telegram_conversation_full",
                new=AsyncMock(return_value=fake_conv),
            ),
            patch(
                "app.integrations.telegram.handlers.update_conversation_model",
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
        nexus_uid = uuid.uuid4()
        conv_id = uuid.uuid4()
        sender = TelegramSender(user_id=4, chat_id=4, username="t", full_name="T")
        session = AsyncMock()

        fake_conv = AsyncMock()
        fake_conv.id = conv_id
        fake_conv.model_id = None

        with (
            patch(
                "app.integrations.telegram.handlers.get_user_id_for_external",
                new=AsyncMock(return_value=nexus_uid),
            ),
            patch(
                "app.integrations.telegram.handlers.get_or_create_telegram_conversation_full",
                new=AsyncMock(return_value=fake_conv),
            ),
            patch(
                "app.integrations.telegram.handlers.update_conversation_model",
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
        nexus_uid = uuid.uuid4()
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
                "app.integrations.telegram.handlers.get_user_id_for_external",
                new=AsyncMock(return_value=nexus_uid),
            ),
            patch(
                "app.integrations.telegram.handlers.get_or_create_telegram_conversation_full",
                new=AsyncMock(return_value=fake_conv),
            ),
            patch(
                "app.integrations.telegram.handlers.update_conversation_model",
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

    The handler in :mod:`app.integrations.telegram.bot` wraps the
    ``resolve_llm`` call so that an unknown-but-well-formed stored model
    surfaces an immediate user-facing warning, clears the stored value,
    and still completes the current turn using the catalog default.

    These tests mock ``async_session_maker`` and ``resolve_llm`` so the
    branching is exercised without spinning up the DB or the providers.
    """

    @staticmethod
    def _make_context(model_id: str) -> TelegramTurnContext:
        return TelegramTurnContext(
            nexus_user_id=uuid.uuid4(),
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
                "app.integrations.telegram.bot_provider_resolution.resolve_llm",
                new=resolve_mock,
            ),
            patch(
                "app.integrations.telegram.bot_provider_resolution.update_conversation_model",
                new=update_mock,
            ),
            patch(
                "app.integrations.telegram.bot_provider_resolution.async_session_maker",
                new=fake_session_maker,
            ),
        ):
            provider, warning = await _resolve_provider_with_auto_clear(context)

        # Warning was produced and mentions the bad ID + the default.
        assert warning is not None
        assert "agent-sdk:anthropic/claude-nonexistent" in warning
        assert default_model().id in warning

        # Stored model_id was cleared to NULL.
        update_mock.assert_awaited_once()
        assert update_mock.await_args.kwargs["model_id"] is None
        assert update_mock.await_args.kwargs["conversation_id"] == context.conversation_id

        # resolve_llm was called *once* — only for the catalog default fallback.
        # (For the unknown path ``require_known()`` raises first, so
        # ``resolve_llm`` is only invoked for the fallback.)
        assert resolve_mock.call_count == 1
        fallback_call = resolve_mock.call_args
        assert fallback_call.args[0] == default_model().id
        assert provider is fake_default_provider

    async def test_following_turn_uses_catalog_default_after_clear(self) -> None:
        """After the auto-clear, a turn with ``model_id=None`` resolves cleanly.

        ``handle_plain_message`` reads ``conversation.model_id`` and falls
        back to ``default_model().id`` when it is ``NULL``.  Here we
        simulate that follow-up turn: the resolved context carries the
        catalog default directly, and the helper neither warns nor clears.
        """
        context = self._make_context(default_model().id)

        fake_default_provider = MagicMock(name="default_provider")
        update_mock = AsyncMock(return_value=True)
        resolve_mock = MagicMock(side_effect=[fake_default_provider])

        with (
            patch(
                "app.integrations.telegram.bot_provider_resolution.resolve_llm",
                new=resolve_mock,
            ),
            patch(
                "app.integrations.telegram.bot_provider_resolution.update_conversation_model",
                new=update_mock,
            ),
        ):
            provider, warning = await _resolve_provider_with_auto_clear(context)

        # Clean path: no warning, no clear.
        assert warning is None
        update_mock.assert_not_awaited()

        # resolve_llm was called exactly once with the stored canonical ID.
        assert resolve_mock.call_count == 1
        assert resolve_mock.call_args.args[0] == default_model().id
        assert provider is fake_default_provider
