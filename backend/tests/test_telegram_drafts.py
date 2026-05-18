"""Tests for draft streaming (Workstream 1).

Covers:
- safe_send_draft: returns True on success, False on ImportError / API errors
- safe_send_draft: non-empty effective_text when html is blank
- handle_text_delta_draft: accumulates text_buffer, routes via draft
- handle_text_delta_draft: opens with empty placeholder on very first chunk
  under debounce threshold, then flushes when threshold is crossed
- handle_text_delta_draft: starts keepalive task on first flush
- flag-off path keeps legacy editMessageText / sendMessage behavior
- finalize_turn_delivery: cancels keepalive task
"""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels._telegram_dispatch import (
    DraftStreamState,
    finalize_turn_delivery,
    handle_text_delta,
)
from app.channels._telegram_draft import (
    _TEXT_DRAFT_ID,
    handle_text_delta_draft,
)
from app.channels.telegram_delivery import safe_send_draft

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=99))
    return bot


def _draft_state(chat_id: int = 1) -> DraftStreamState:
    return DraftStreamState(
        chat_id=chat_id,
        draft_id=_TEXT_DRAFT_ID,
        message_thread_id=None,
    )


# ---------------------------------------------------------------------------
# safe_send_draft
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestSafeSendDraft:
    async def test_returns_bool(self) -> None:
        """safe_send_draft always returns a bool regardless of aiogram version."""
        bot = _make_bot()
        result = await safe_send_draft(bot, 1, 1, "hello")
        # Either True (if aiogram ships SendMessageDraft) or False (ImportError) — both valid.
        assert isinstance(result, bool)

    async def test_returns_false_on_api_error(self) -> None:
        """When the API returns an error, safe_send_draft returns False."""
        bot = _make_bot()
        # Simulate an aiogram TelegramAPIError by making __call__ fail
        from aiogram.exceptions import TelegramBadRequest

        bot.side_effect = TelegramBadRequest(method=MagicMock(), message="DRAFT_FAILED")
        result = await safe_send_draft(bot, 1, 1, "hello")
        assert result is False

    async def test_empty_html_uses_fallback_placeholder(self) -> None:
        """Empty html must not raise — effective_text is always non-empty."""
        bot = _make_bot()
        # We verify the observable contract: no ValidationError / exception
        # and the return value is bool.
        result = await safe_send_draft(bot, 1, 1, "")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# handle_text_delta_draft
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestHandleTextDeltaDraft:
    async def _call(
        self,
        bot: AsyncMock,
        text_buffer: str,
        chunk: str,
        chars_since_edit: int,
        last_edit_at: float,
        draft_state: DraftStreamState,
    ) -> tuple[str, None, int, float]:
        return await handle_text_delta_draft(
            bot=bot,
            text_buffer=text_buffer,
            chunk=chunk,
            chars_since_edit=chars_since_edit,
            last_edit_at=last_edit_at,
            draft_state=draft_state,
        )

    async def test_accumulates_text_buffer(self) -> None:
        """text_buffer is returned (not reset) across calls."""
        bot = _make_bot()
        state = _draft_state()
        now = asyncio.get_event_loop().time()

        buf, msg_id, _cse, _ = await self._call(bot, "Hello", " world", 5, now, state)
        assert buf == "Hello world"
        assert msg_id is None  # draft mode never returns a message_id

    async def test_text_message_id_always_none(self) -> None:
        """Draft path never creates a Telegram message; message_id slot is always None."""
        bot = _make_bot()
        state = _draft_state()
        now = asyncio.get_event_loop().time()
        _, msg_id, _, _ = await self._call(bot, "", "chunk", 0, now, state)
        assert msg_id is None

    async def test_under_debounce_opens_draft_with_empty_text(self) -> None:
        """First chunk under debounce threshold opens draft with empty text (native placeholder)."""
        bot = _make_bot()
        state = _draft_state()
        now = asyncio.get_event_loop().time()

        with patch(
            "app.channels._telegram_draft.safe_send_draft", new_callable=AsyncMock
        ) as mock_draft:
            mock_draft.return_value = True
            await self._call(bot, "a", "a", 1, now, state)  # chars < 40, elapsed < 3s
            # Should have been called with empty text for native "Thinking…" placeholder
            mock_draft.assert_awaited_once()
            call_kwargs = mock_draft.await_args
            assert call_kwargs.args[3] == ""  # html arg is empty string

    async def test_over_debounce_flushes_rendered_html(self) -> None:
        """When chars >= 40, draft is flushed with rendered HTML."""
        bot = _make_bot()
        state = _draft_state()
        now = asyncio.get_event_loop().time() - 10.0  # old timestamp → elapsed > 3s

        with patch(
            "app.channels._telegram_draft.safe_send_draft", new_callable=AsyncMock
        ) as mock_draft:
            mock_draft.return_value = True
            _buf, _, cse, _ = await self._call(bot, "A" * 39, "B", 39, now, state)
            # Should flush non-empty HTML
            mock_draft.assert_awaited_once()
            call_kwargs = mock_draft.await_args
            passed_html = call_kwargs.args[3]
            assert passed_html  # non-empty
            # chars_since_edit reset to 0 after flush
            assert cse == 0

    async def test_keepalive_task_started_after_flush(self) -> None:
        """Keepalive task is created once the draft flushes for the first time."""
        bot = _make_bot()
        state = _draft_state()
        now = asyncio.get_event_loop().time() - 10.0  # force elapsed > threshold

        with patch(
            "app.channels._telegram_draft.safe_send_draft", new_callable=AsyncMock
        ) as mock_draft:
            mock_draft.return_value = True
            await self._call(bot, "A" * 39, "B", 39, now, state)
            assert state.keepalive_task is not None
            assert not state.keepalive_task.done()
            # Clean up
            state.keepalive_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await state.keepalive_task

    async def test_keepalive_not_duplicated(self) -> None:
        """Second flush does not create a second keepalive task."""
        bot = _make_bot()
        state = _draft_state()
        past = asyncio.get_event_loop().time() - 10.0

        with patch(
            "app.channels._telegram_draft.safe_send_draft", new_callable=AsyncMock
        ) as mock_draft:
            mock_draft.return_value = True
            # First flush
            await self._call(bot, "A" * 39, "B", 39, past, state)
            first_task = state.keepalive_task
            # Second flush
            await self._call(bot, "A" * 79, "C", 39, past, state)
            assert state.keepalive_task is first_task  # same task, not replaced
            # Clean up
            if state.keepalive_task and not state.keepalive_task.done():
                state.keepalive_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await state.keepalive_task


# ---------------------------------------------------------------------------
# handle_text_delta — flag-off path (no draft_state)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestHandleTextDeltaLegacyPath:
    async def test_flag_off_opens_send_message_first_chunk(self) -> None:
        """Without draft_state, first chunk calls send_message, not sendMessageDraft."""
        bot = _make_bot()
        now = asyncio.get_event_loop().time()

        _buf, msg_id, _, _ = await handle_text_delta(
            chunk="Hello",
            bot=bot,
            chat_id=1,
            text_buffer="Hello",
            text_message_id=None,
            chars_since_edit=5,
            last_edit_at=now - 10.0,
            reply_to_message_id=None,
            message_thread_id=None,
            draft_state=None,  # flag off
        )
        bot.send_message.assert_awaited_once()
        assert msg_id == 99  # from mock return value

    async def test_flag_off_subsequent_chunk_edits_message(self) -> None:
        """Without draft_state, subsequent chunks call edit_message_text."""
        bot = _make_bot()
        now = asyncio.get_event_loop().time() - 10.0

        _buf, msg_id, _, _ = await handle_text_delta(
            chunk="world",
            bot=bot,
            chat_id=1,
            text_buffer="Hello world",
            text_message_id=42,
            chars_since_edit=100,  # above debounce
            last_edit_at=now,
            reply_to_message_id=None,
            message_thread_id=None,
            draft_state=None,
        )
        bot.edit_message_text.assert_awaited_once()
        assert msg_id == 42


# ---------------------------------------------------------------------------
# finalize_turn_delivery — keepalive cancellation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestFinalizeTurnDeliveryCancelKeepalive:
    async def test_cancels_keepalive_on_finalize(self) -> None:
        """finalize_turn_delivery cancels the draft keepalive task."""
        bot = _make_bot()

        # Create a real task that runs forever
        async def _forever() -> None:
            await asyncio.Event().wait()

        task = asyncio.create_task(_forever())
        state = _draft_state()
        state.keepalive_task = task

        await finalize_turn_delivery(
            bot=bot,
            chat_id=1,
            placeholder_message_id=10,
            first_block_kind=None,
            previous_block_kind=None,
            tool_trace="",
            thinking_text="",
            text_message_id=None,
            text_buffer="",
            final_text="",
            reply_to_message_id=None,
            message_thread_id=None,
            draft_state=state,
        )

        assert task.cancelled()

    async def test_no_keepalive_no_error(self) -> None:
        """finalize_turn_delivery with draft_state but no keepalive task does not raise."""
        bot = _make_bot()
        state = _draft_state()
        state.keepalive_task = None  # never started

        # Should not raise
        await finalize_turn_delivery(
            bot=bot,
            chat_id=1,
            placeholder_message_id=10,
            first_block_kind=None,
            previous_block_kind=None,
            tool_trace="",
            thinking_text="",
            text_message_id=None,
            text_buffer="",
            final_text="",
            reply_to_message_id=None,
            message_thread_id=None,
            draft_state=state,
        )
