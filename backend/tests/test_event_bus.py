"""Tests for ``app.infrastructure.event_bus.bus.EventBus``.

Covers the pub/sub contract: typed dispatch, global subscribers,
concurrent dispatch (no head-of-line blocking), and error isolation
(a crashing handler doesn't poison siblings or the consumer task).
"""

from __future__ import annotations

import asyncio

import pytest

from app.infrastructure.event_bus import (
    AgentResponseEvent,
    Event,
    EventBus,
    TurnStartedEvent,
)

pytestmark = pytest.mark.anyio


_DRAIN_POLL_INTERVAL_S = 0.01
_DRAIN_DEFAULT_TIMEOUT_S = 0.5


async def _drain(bus: EventBus) -> None:
    """Spin briefly so the consumer task picks up published events."""
    deadline = asyncio.get_event_loop().time() + _DRAIN_DEFAULT_TIMEOUT_S
    while bus._queue.qsize() > 0:
        if asyncio.get_event_loop().time() > deadline:
            break
        await asyncio.sleep(_DRAIN_POLL_INTERVAL_S)
    # Give handlers a final tick to finish.
    await asyncio.sleep(_DRAIN_POLL_INTERVAL_S)


class TestPubSub:
    async def test_subscriber_receives_published_event(self) -> None:
        bus = EventBus()
        await bus.start()
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe(TurnStartedEvent, handler)
        await bus.publish(TurnStartedEvent(surface="web"))
        await _drain(bus)
        await bus.stop()

        assert len(received) == 1
        assert isinstance(received[0], TurnStartedEvent)
        assert received[0].surface == "web"

    async def test_unsubscribed_event_type_skips_handler(self) -> None:
        bus = EventBus()
        await bus.start()
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe(TurnStartedEvent, handler)
        # Different event type — handler must not fire.
        await bus.publish(AgentResponseEvent(text="hello"))
        await _drain(bus)
        await bus.stop()
        assert received == []

    async def test_subscribe_all_receives_every_event(self) -> None:
        bus = EventBus()
        await bus.start()
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe_all(handler)
        await bus.publish(TurnStartedEvent(surface="web"))
        await bus.publish(AgentResponseEvent(text="x"))
        await _drain(bus)
        await bus.stop()
        assert len(received) == 2


class TestErrorIsolation:
    async def test_handler_crash_does_not_break_siblings(self) -> None:
        bus = EventBus()
        await bus.start()
        received: list[Event] = []

        async def crashing(_event: Event) -> None:
            raise RuntimeError("boom")

        async def good(event: Event) -> None:
            received.append(event)

        bus.subscribe(TurnStartedEvent, crashing)
        bus.subscribe(TurnStartedEvent, good)
        await bus.publish(TurnStartedEvent(surface="telegram"))
        await _drain(bus)
        await bus.stop()
        # Sibling fired despite the crashing handler.
        assert len(received) == 1

    async def test_handler_crash_does_not_kill_consumer(self) -> None:
        """A crashing handler must not stop the bus from processing the next event."""
        bus = EventBus()
        await bus.start()
        received: list[Event] = []

        async def crashing(_event: Event) -> None:
            raise RuntimeError("boom")

        async def good(event: Event) -> None:
            received.append(event)

        bus.subscribe(TurnStartedEvent, crashing)
        bus.subscribe(AgentResponseEvent, good)

        await bus.publish(TurnStartedEvent(surface="web"))
        await _drain(bus)
        await bus.publish(AgentResponseEvent(text="still alive"))
        await _drain(bus)
        await bus.stop()

        assert len(received) == 1
        assert isinstance(received[0], AgentResponseEvent)


class TestLifecycle:
    async def test_start_is_idempotent(self) -> None:
        bus = EventBus()
        await bus.start()
        await bus.start()  # second call must be a no-op
        await bus.stop()

    async def test_stop_is_idempotent(self) -> None:
        bus = EventBus()
        await bus.start()
        await bus.stop()
        await bus.stop()  # second call must be a no-op
