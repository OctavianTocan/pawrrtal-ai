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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels import registered_surfaces, resolve_channel
from app.channels.base import ChannelMessage
from app.channels.telegram import SURFACE_TELEGRAM, TelegramChannel
from app.core.providers.base import StreamEvent
from app.core.providers.catalog import default_model
from app.crud.conversation import ConversationStatus
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
from app.integrations.telegram.status import (
    _format_duration,
    _format_token_count,
    _render_status_message,
    handle_status_command,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _stream(*events: StreamEvent) -> AsyncIterator[StreamEvent]:
    for event in events:
        yield event


def _make_channel_message(
    bot: AsyncMock, chat_id: int = 123, message_id: int = 456
) -> ChannelMessage:
    return ChannelMessage(
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        text="hello",
        surface="telegram",
        model_id=None,
        metadata={
            "bot": bot,
            "chat_id": chat_id,
            "message_id": message_id,
        },
    )


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
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
    assert names == ["start", "new", "model", "verbose", "stop", "status"]
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

    async def test_final_edit_always_sent(self) -> None:
        """Even a single small delta below the debounce threshold gets a final edit."""
        bot = _make_bot()
        msg = _make_channel_message(bot, chat_id=7, message_id=99)
        channel = TelegramChannel()

        async for _ in channel.deliver(_stream({"type": "delta", "content": "hi"}), msg):
            pass

        bot.edit_message_text.assert_called_once_with(
            chat_id=7,
            message_id=99,
            text="hi",
        )

    async def test_accumulates_deltas(self) -> None:
        """Multiple deltas below the debounce threshold collapse into one final edit."""
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

        # The final edit must contain the full accumulated text.
        calls = bot.edit_message_text.call_args_list
        last_call = calls[-1]
        assert last_call.kwargs["text"] == "Hello, world"

    async def test_tool_use_injects_inline_glyph(self) -> None:
        """``tool_use`` injects an inline glyph when verbose filtering lets it through."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "delta", "content": "answer"},
            {"type": "tool_use", "name": "search", "input": {}},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        last_call = bot.edit_message_text.call_args_list[-1]
        # PR 07: tool_use surfaces a one-line glyph + tool name so the
        # user can see what the agent is doing in real time.
        assert last_call.kwargs["text"].startswith("answer")
        assert "search" in last_call.kwargs["text"]

    async def test_thinking_event_renders_when_verbose_filter_allows_it(self) -> None:
        """Detailed Telegram verbosity surfaces thinking chunks inline."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "thinking", "content": "checking the workspace"},
            {"type": "delta", "content": "answer"},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        last_text = bot.edit_message_text.call_args_list[-1].kwargs["text"]
        assert "Thinking:" in last_text
        assert "checking the workspace" in last_text
        assert "answer" in last_text

    async def test_agent_terminated_replaces_placeholder(self) -> None:
        """``agent_terminated`` without any text must show the warning to the user."""
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

        bot.edit_message_text.assert_called_once()
        text = bot.edit_message_text.call_args.kwargs["text"]
        # The ⚠️ prefix is markdown-converted to HTML, so we check for the
        # human-readable copy and the chat_id/message_id routing.
        assert "max_iterations" in text
        assert bot.edit_message_text.call_args.kwargs["chat_id"] == 11
        assert bot.edit_message_text.call_args.kwargs["message_id"] == 22

    async def test_agent_terminated_appended_after_partial_text(self) -> None:
        """If the agent produced some text before termination, both are shown."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "delta", "content": "Partial answer."},
            {"type": "agent_terminated", "content": "Stopped: max_iterations."},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        last_text = bot.edit_message_text.call_args_list[-1].kwargs["text"]
        assert "Partial answer." in last_text
        assert "max_iterations" in last_text

    async def test_error_event_replaces_placeholder(self) -> None:
        """A bare ``error`` event must surface the error text in the chat."""
        bot = _make_bot()
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        events: list[StreamEvent] = [
            {"type": "error", "content": "Gemini provider error: rate limited"},
        ]
        async for _ in channel.deliver(_stream(*events), msg):
            pass

        bot.edit_message_text.assert_called_once()
        assert "rate limited" in bot.edit_message_text.call_args.kwargs["text"]

    async def test_not_modified_error_swallowed(self) -> None:
        """TelegramBadRequest: message is not modified must not propagate."""
        bot = _make_bot()
        bot.edit_message_text.side_effect = Exception("TelegramBadRequest: message is not modified")
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        # Should not raise.
        async for _ in channel.deliver(_stream({"type": "delta", "content": "x"}), msg):
            pass

    async def test_other_errors_logged_not_raised(self) -> None:
        """Network or API errors should log a warning but not crash the turn."""
        bot = _make_bot()
        bot.edit_message_text.side_effect = Exception("network timeout")
        msg = _make_channel_message(bot)
        channel = TelegramChannel()

        async for _ in channel.deliver(_stream({"type": "delta", "content": "x"}), msg):
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
            model_id=default_model().id,
            verbose_level=1,
            started_at=_dt(2026, 5, 17, 18, 0, tzinfo=UTC),
            message_count=14,
            user_message_count=7,
            assistant_message_count=7,
            total_input_tokens=18_420,
            total_output_tokens=6_108,
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
            model_id=default_model().id,
            verbose_level=1,
            started_at=_dt(2026, 5, 17, 18, 0, tzinfo=UTC),
            message_count=48,
            user_message_count=24,
            assistant_message_count=24,
            total_input_tokens=0,
            total_output_tokens=0,
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
            model_id=default_model().id,
            verbose_level=1,
            started_at=_dt(2026, 5, 17, 18, 0, tzinfo=UTC),
            message_count=0,
            user_message_count=0,
            assistant_message_count=0,
            total_input_tokens=0,
            total_output_tokens=0,
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
            started_at=_dt(2026, 5, 17, 19, 0, tzinfo=UTC),
            message_count=2,
            user_message_count=1,
            assistant_message_count=1,
            total_input_tokens=100,
            total_output_tokens=50,
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
        # Verbose level falls back to settings default (1 = normal) when None.
        assert "Verbose: 1" in rendered

    def test_handles_tz_naive_started_at_from_db(self) -> None:
        """Regression: ``Conversation.created_at`` is tz-naive in the DB.

        Before normalization the renderer raised ``TypeError: can't subtract
        offset-naive and offset-aware datetimes`` against any real prod row.
        """
        from datetime import UTC
        from datetime import datetime as _dt

        status = ConversationStatus(
            conversation_id=uuid.uuid4(),
            model_id=default_model().id,
            verbose_level=1,
            started_at=_dt(2026, 5, 17, 18, 0),  # tz-naive, matches DB
            message_count=1,
            user_message_count=1,
            assistant_message_count=0,
            total_input_tokens=10,
            total_output_tokens=5,
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
            "app.integrations.telegram.status.get_user_id_for_external",
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
        nexus_uid = uuid.uuid4()
        conv_id = uuid.uuid4()
        sender = TelegramSender(user_id=9, chat_id=9, username="t", full_name="T")
        session = AsyncMock()

        fake_conv = MagicMock()
        fake_conv.id = conv_id

        from datetime import UTC
        from datetime import datetime as _dt

        fake_status = ConversationStatus(
            conversation_id=conv_id,
            model_id=default_model().id,
            verbose_level=2,
            started_at=_dt(2026, 5, 17, 18, 0, tzinfo=UTC),
            message_count=3,
            user_message_count=2,
            assistant_message_count=1,
            total_input_tokens=900,
            total_output_tokens=200,
        )

        with (
            patch(
                "app.integrations.telegram.status.get_user_id_for_external",
                new=AsyncMock(return_value=nexus_uid),
            ),
            patch(
                "app.integrations.telegram.status.get_or_create_telegram_conversation_full",
                new=AsyncMock(return_value=fake_conv),
            ),
            patch(
                "app.integrations.telegram.status.get_conversation_status",
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
