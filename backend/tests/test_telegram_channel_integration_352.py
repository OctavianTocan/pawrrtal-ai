"""Channel-integration tests for ``TelegramChannel.deliver`` (#352 L2).

L1 (in ``test_telegram_dispatch.py``) pins the per-event state machine
in :mod:`_telegram_dispatch`. L2 pins the whole-loop orchestration in
``TelegramChannel.deliver`` — the layer where individual handlers
are correct but the sequence can still drop output (#346 was exactly
this class of bug).

Each test drives a scripted ``StreamEvent`` sequence through
``deliver`` and inspects the recording :class:`FakeBot` to assert the
final visible answer. Literal ``assert calls == [...]`` over a
snapshot library — clearer diffs in review, no update-mode confusion.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.channels.base import ChannelMessage
from app.channels.telegram import TelegramChannel
from app.providers.base import StreamEvent


class FakeBot:
    """Records every method call so tests can assert message sequence.

    Mirrors the FakeBot shape suggested in #352 L2. Each call appends
    a ``{"method": ..., **kwargs}`` dict to ``self.calls`` so the
    test can pin the exact wire interaction.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._next_message_id = 1000

    async def send_message(self, **kwargs: Any) -> Any:
        """Record a send_message call."""
        self._next_message_id += 1
        self.calls.append({"method": "send_message", **kwargs})
        return _FakeSentMessage(message_id=self._next_message_id)

    async def edit_message_text(self, **kwargs: Any) -> Any:
        """Record an edit_message_text call."""
        self.calls.append({"method": "edit_message_text", **kwargs})
        return None

    async def delete_message(self, **kwargs: Any) -> None:
        """Record a delete_message call."""
        self.calls.append({"method": "delete_message", **kwargs})

    async def __call__(self, method: Any) -> Any:
        """Aiogram dispatches ``SendMessageDraft`` via ``bot(...)`` — record it."""
        self.calls.append({"method": "draft_send", "request": type(method).__name__})
        return None


class _FakeSentMessage:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


async def _stream(*events: StreamEvent) -> AsyncIterator[StreamEvent]:
    for event in events:
        yield event


def _channel_message(bot: FakeBot) -> ChannelMessage:
    return ChannelMessage(
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        text="hello",
        surface="telegram",
        model_id=None,
        metadata={
            "bot": bot,
            "chat_id": 123,
            "message_id": 456,
        },
    )


async def _drain(channel: TelegramChannel, events: tuple[StreamEvent, ...], bot: FakeBot) -> None:
    """Run ``deliver`` and exhaust any bytes it yields (side-effect only)."""
    async for _ in channel.deliver(_stream(*events), _channel_message(bot)):
        pass


def _final_visible_text(calls: list[dict[str, Any]]) -> str:
    """Return the text on the last send_message OR edit_message_text call.

    That's the message the user actually sees as the assistant's
    final reply. If neither was called, returns an empty string.
    """
    for call in reversed(calls):
        if call["method"] == "send_message":
            return str(call.get("text", ""))
        if call["method"] == "edit_message_text":
            return str(call.get("text", ""))
    return ""


@pytest.mark.xfail(reason="Requires dispatch fixes from #371/#377 to pass")
@pytest.mark.anyio
async def test_thinking_then_multi_delta_answer_renders_full_text() -> None:
    """``thinking → delta → delta → delta`` must surface the full concatenated answer.

    This is the regression #346 hit: when text followed a thinking
    block, only the first delta rendered because the legacy text
    path short-circuited on ``previous_block_kind == "text"``.
    """
    bot = FakeBot()
    channel = TelegramChannel()
    events = (
        StreamEvent(type="thinking", content="checking..."),
        StreamEvent(type="delta", content="Hel"),
        StreamEvent(type="delta", content="lo"),
        StreamEvent(type="delta", content=", world!"),
    )

    await _drain(channel, events, bot)

    visible = _final_visible_text(bot.calls)
    assert "Hello, world!" in visible, f"Final visible text dropped chunks; got: {visible!r}"


@pytest.mark.xfail(reason="Requires dispatch fixes from #371/#377 to pass")
@pytest.mark.anyio
async def test_tool_use_then_multi_delta_answer_renders_full_text() -> None:
    """Same as above but with a ``tool_use → tool_result`` block first.

    Tool turns hit the same dispatch state machine as thinking
    turns; the same regression class applies.
    """
    bot = FakeBot()
    channel = TelegramChannel()
    events = (
        StreamEvent(type="tool_use", name="search", input={"q": "x"}, tool_use_id="t1"),
        StreamEvent(type="tool_result", content="ok", tool_use_id="t1"),
        StreamEvent(type="delta", content="Hel"),
        StreamEvent(type="delta", content="lo"),
        StreamEvent(type="delta", content="!"),
    )

    await _drain(channel, events, bot)

    visible = _final_visible_text(bot.calls)
    assert "Hello!" in visible, (
        f"Final visible text dropped chunks after tool block; got: {visible!r}"
    )


@pytest.mark.xfail(reason="Requires dispatch fixes from #371/#377 to pass")
@pytest.mark.anyio
async def test_error_event_surfaces_to_user() -> None:
    """A provider ``error`` event must reach the user, not get swallowed.

    Reproduces the #350 symptom from the issue plan: the OpenCode Go
    auth-failure path used to surface as a text-delta the legacy text
    path then dropped. With #371's StreamEvent error path + #377's
    legacy text fix, the error event survives.
    """
    bot = FakeBot()
    channel = TelegramChannel()
    events = (
        StreamEvent(
            type="error",
            content="OpenCode API key not configured. Set OPENCODE_API_KEY.",
        ),
    )

    await _drain(channel, events, bot)

    visible = _final_visible_text(bot.calls)
    assert "OpenCode API key not configured" in visible, (
        f"Error event was swallowed; visible text: {visible!r}"
    )
    # The ❌ glyph prefix is the established Telegram convention for
    # error events (`_ERROR_PREFIX` in ``telegram.py``). Confirm the
    # path that decorates it ran.
    assert "❌" in visible, f"Error event surfaced without the error glyph; visible: {visible!r}"
