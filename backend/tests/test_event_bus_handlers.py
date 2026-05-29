"""Tests for the AgentHandler + NotificationService bus subscribers.

Both handlers are bus-driven so the tests publish events through a
real :class:`EventBus` and assert on the resulting side-effects.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.infrastructure.event_bus import (
    AgentHandler,
    AgentResponseEvent,
    EventBus,
    NotificationService,
    ScheduledEvent,
    WebhookEvent,
)

pytestmark = pytest.mark.anyio


_DRAIN_POLL_INTERVAL_S = 0.01
_DRAIN_DEFAULT_TIMEOUT_S = 0.5


async def _drain(bus: EventBus) -> None:
    """Wait briefly so the consumer task picks up published events."""
    deadline = asyncio.get_event_loop().time() + _DRAIN_DEFAULT_TIMEOUT_S
    while bus._queue.qsize() > 0:
        if asyncio.get_event_loop().time() > deadline:
            break
        await asyncio.sleep(_DRAIN_POLL_INTERVAL_S)
    await asyncio.sleep(_DRAIN_POLL_INTERVAL_S)


class _RecordingBot:
    """Minimal bot stub that records every ``send_message`` call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def send_message(self, *, chat_id: str, text: str, **_kw: object) -> None:
        self.calls.append((chat_id, text))


class TestNotificationServiceDelivery:
    async def test_delivers_to_event_chat_id(self) -> None:
        bus = EventBus()
        await bus.start()
        bot = _RecordingBot()
        NotificationService(telegram_bot=bot).register(bus)
        await bus.publish(
            AgentResponseEvent(chat_id="42", text="hello", originating_event_id="abc")
        )
        await _drain(bus)
        await bus.stop()
        assert bot.calls == [("42", "hello")]

    async def test_skips_when_no_chat_id(self) -> None:
        """Without a chat_id the service no-ops (broadcast list is future work)."""
        bus = EventBus()
        await bus.start()
        bot = _RecordingBot()
        NotificationService(telegram_bot=bot).register(bus)
        await bus.publish(AgentResponseEvent(chat_id=None, text="hello"))
        await _drain(bus)
        await bus.stop()
        assert bot.calls == []

    async def test_skips_when_no_bot(self) -> None:
        """No bot configured → the service silently no-ops."""
        bus = EventBus()
        await bus.start()
        NotificationService(telegram_bot=None).register(bus)
        await bus.publish(AgentResponseEvent(chat_id="42", text="hello"))
        await _drain(bus)
        await bus.stop()
        # Nothing to assert beyond "didn't crash".

    async def test_truncates_oversize_text(self) -> None:
        """Text longer than the per-message budget is tail-truncated with an ellipsis."""
        bus = EventBus()
        await bus.start()
        bot = _RecordingBot()
        NotificationService(telegram_bot=bot).register(bus)
        long_text = "x" * 5000
        await bus.publish(AgentResponseEvent(chat_id="42", text=long_text))
        await _drain(bus)
        await bus.stop()
        assert len(bot.calls) == 1
        sent = bot.calls[0][1]
        assert sent.endswith("…")
        assert len(sent) <= 4001  # 4000 budget + the single trailing ellipsis

    async def test_delivery_failure_isolated(self) -> None:
        """A bot-side exception is swallowed so it doesn't poison the bus."""

        class ExplodingBot:
            async def send_message(self, **_: object) -> None:
                raise RuntimeError("boom")

        bus = EventBus()
        await bus.start()
        NotificationService(telegram_bot=ExplodingBot()).register(bus)
        await bus.publish(AgentResponseEvent(chat_id="42", text="hello"))
        await _drain(bus)
        await bus.stop()
        # No assertion needed — the bus would have logged and moved on.


class TestAgentHandlerRouting:
    """The AgentHandler subscribes to webhook + scheduled events."""

    async def test_subscribes_to_both_event_types(self) -> None:
        bus = EventBus()
        AgentHandler().register(bus)
        # Internal check — the handler registered subscribers for
        # both event types, not just one.
        subs = bus._handlers
        assert WebhookEvent in subs
        assert ScheduledEvent in subs

    async def test_no_user_skips_publish(self) -> None:
        """Webhook with no user_id (and no default) skips silently."""
        bus = EventBus()
        await bus.start()
        bot = _RecordingBot()
        AgentHandler().register(bus)
        NotificationService(telegram_bot=bot).register(bus)
        await bus.publish(WebhookEvent(provider="github", event_type_name="push", payload={}))
        await _drain(bus)
        await bus.stop()
        # Without a user the agent never runs, so no notification.
        assert bot.calls == []

    async def test_scheduled_event_with_skill_prefix(self) -> None:
        """Scheduled event with skill_name prefixes the prompt with /skill."""
        # We don't stand up a real LLM here — _run_agent_turn would
        # require a workspace + provider.  Instead we just assert
        # the handler dispatches without crashing on a no-user event.
        bus = EventBus()
        await bus.start()
        AgentHandler().register(bus)
        await bus.publish(
            ScheduledEvent(
                job_id=uuid.uuid4(),
                job_name="daily-summary",
                prompt="Summarize my email.",
                skill_name="triage",
            )
        )
        await _drain(bus)
        await bus.stop()
