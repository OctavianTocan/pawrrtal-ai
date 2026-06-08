"""Google Chat channel — progressive streaming delivery (channel + delivery).

Stream events → progressive ``update_message`` patches, verbose-gated
(tools/thinking), with error and empty-turn fallbacks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.channels.base import ChannelMessage
from app.channels.google_chat import delivery as delivery_module
from app.channels.google_chat.channel import (
    INITIAL_PLACEHOLDER_TEXT,
    SURFACE_GOOGLE_CHAT,
    GoogleChatChannel,
)
from app.channels.google_chat.delivery import StreamingDelivery
from app.providers.base import StreamEvent
from tests.channels.google_chat.helpers import SPACE, THREAD

pytestmark = pytest.mark.anyio


async def _stream(events: list[StreamEvent]) -> AsyncIterator[StreamEvent]:
    for event in events:
        yield event


def _channel_message(message_name: str | None = "spaces/AAAA/messages/MMMM") -> ChannelMessage:
    return {
        "user_id": uuid4(),
        "conversation_id": uuid4(),
        "text": "hi",
        "surface": SURFACE_GOOGLE_CHAT,
        "model_id": "google-ai:google/gemini-3-flash-preview",
        "metadata": {"space_name": SPACE, "thread_name": THREAD, "message_name": message_name},
    }


def _patched_text(patch_mock: AsyncMock) -> str:
    """Return the ``text`` kwarg of the single ``update_message`` patch call."""
    call = patch_mock.await_args
    assert call is not None
    return str(call.kwargs["text"])


async def test_deliver_patches_placeholder_with_final_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery_module, "update_message", patch_mock)

    events: list[StreamEvent] = [
        {"type": "delta", "content": "Hello "},
        {"type": "delta", "content": "world"},
    ]
    async for _ in GoogleChatChannel().deliver(_stream(events), _channel_message()):
        pass

    patch_mock.assert_awaited()
    # ``_patched_text`` reads the LAST patch — the final render is the full answer.
    assert _patched_text(patch_mock) == "Hello world"


async def test_deliver_surfaces_error_with_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery_module, "update_message", patch_mock)

    events: list[StreamEvent] = [{"type": "error", "content": "boom"}]
    async for _ in GoogleChatChannel().deliver(_stream(events), _channel_message()):
        pass

    assert _patched_text(patch_mock).startswith("❌ ")


async def test_deliver_uses_fallback_for_empty_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery_module, "update_message", patch_mock)

    async for _ in GoogleChatChannel().deliver(_stream([]), _channel_message()):
        pass

    assert "without producing a reply" in _patched_text(patch_mock)


async def test_deliver_skips_patch_without_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery_module, "update_message", patch_mock)

    events: list[StreamEvent] = [{"type": "delta", "content": "ignored"}]
    async for _ in GoogleChatChannel().deliver(
        _stream(events), _channel_message(message_name=None)
    ):
        pass

    patch_mock.assert_not_awaited()


def test_initial_placeholder_text_is_nonempty() -> None:
    assert INITIAL_PLACEHOLDER_TEXT.strip()


async def _feed(delivery: StreamingDelivery, events: list[StreamEvent]) -> None:
    """Drive events through a delivery whose patch call is a no-op."""
    for event in events:
        await delivery.on_event(event)


async def test_streaming_shows_tools_at_verbose_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery_module, "update_message", AsyncMock(return_value=True))
    delivery = StreamingDelivery(message_name="spaces/A/messages/M", verbose_level=1)
    await _feed(
        delivery,
        [
            {"type": "tool_use", "tool_use_id": "t1", "name": "web_search"},
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok", "is_error": False},
            {"type": "delta", "content": "the answer"},
        ],
    )
    out = delivery.render(streaming=False)
    assert "web_search" in out
    assert "the answer" in out


async def test_streaming_hides_tools_at_verbose_0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery_module, "update_message", AsyncMock(return_value=True))
    delivery = StreamingDelivery(message_name="spaces/A/messages/M", verbose_level=0)
    await _feed(
        delivery,
        [
            {"type": "tool_use", "tool_use_id": "t1", "name": "web_search"},
            {"type": "delta", "content": "the answer"},
        ],
    )
    out = delivery.render(streaming=False)
    assert "web_search" not in out
    assert out == "the answer"


async def test_streaming_shows_thinking_only_at_verbose_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery_module, "update_message", AsyncMock(return_value=True))
    events: list[StreamEvent] = [
        {"type": "thinking", "content": "let me think", "block_index": 0},
        {"type": "delta", "content": "answer"},
    ]
    quiet = StreamingDelivery(message_name="spaces/A/messages/M", verbose_level=1)
    await _feed(quiet, events)
    assert "let me think" not in quiet.render(streaming=False)

    loud = StreamingDelivery(message_name="spaces/A/messages/M", verbose_level=2)
    await _feed(loud, events)
    loud_out = loud.render(streaming=False)
    assert "let me think" in loud_out
    assert "answer" in loud_out


async def test_streaming_marks_failed_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery_module, "update_message", AsyncMock(return_value=True))
    delivery = StreamingDelivery(message_name="spaces/A/messages/M", verbose_level=1)
    await _feed(
        delivery,
        [
            {"type": "tool_use", "tool_use_id": "t1", "name": "broken_tool"},
            {"type": "tool_result", "tool_use_id": "t1", "content": "nope", "is_error": True},
            {"type": "delta", "content": "recovered"},
        ],
    )
    out = delivery.render(streaming=False)
    assert "broken_tool" in out
    assert "⚠️" in out
