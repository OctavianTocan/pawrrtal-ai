"""Async event bus with typed subscriptions.

Ported from CCT's ``src/events/bus.py`` and tightened to:

* Run under the FastAPI lifespan (``start()`` in lifespan setup,
  ``stop()`` in teardown).
* Dispatch handlers concurrently via ``asyncio.gather`` so one slow
  subscriber doesn't queue-stall the others.
* Isolate handler failures — ``return_exceptions=True`` + structured
  log so a crashed subscriber never poisons sibling subscribers or
  the main queue loop.

The bus is provider-neutral and handler-neutral; concrete event
classes live in :mod:`app.infrastructure.event_bus.types`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TypeVar

logger = logging.getLogger(__name__)

# How long the queue-pop polls before checking the running flag.
# 1.0s is enough to keep shutdown latency low without burning CPU.
_QUEUE_POLL_INTERVAL_SECONDS = 1.0


@dataclass
class Event:
    """Base class for every bus event.

    Concrete events extend this with their own typed fields.  The
    base carries metadata every handler can rely on:

    * ``id`` — uuid4, generated at construction; useful for
      correlating downstream effects back to the originating event.
    * ``timestamp`` — UTC datetime at construction.
    * ``source`` — short string the producer fills in (``"chat"``,
      ``"webhook"``, ``"scheduler"``, …) for log lines and metrics.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "unknown"

    @property
    def event_type(self) -> str:
        """Class name — handy in log lines that handle multiple types."""
        return type(self).__name__


_E = TypeVar("_E", bound=Event)
EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    """Single-consumer async pub/sub.

    Lifecycle:
    1. ``EventBus()`` — construct (no background task yet).
    2. ``await bus.start()`` — spawn the consumer task; idempotent.
    3. ``await bus.publish(event)`` — fire-and-forget enqueue.
    4. ``await bus.stop()`` — cancel the consumer + drain.

    Subscribe with :meth:`subscribe` (per-type) or :meth:`subscribe_all`
    (every event regardless of type).  Type-based dispatch uses
    ``isinstance`` so subscribers to a base class also receive
    derived events.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[EventHandler]] = {}
        self._global_handlers: list[EventHandler] = []
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running: bool = False
        self._processor_task: asyncio.Task[None] | None = None

    def subscribe(self, event_type: type[_E], handler: EventHandler) -> None:
        """Register ``handler`` for one event type.

        ``handler`` MUST be an async callable; the bus awaits it on
        every dispatch.  Subscribers to a base class also receive
        derived events (``isinstance`` check at dispatch time).
        """
        bucket = self._handlers.setdefault(event_type, [])
        bucket.append(handler)
        logger.debug(
            "EVENTBUS_SUBSCRIBE event_type=%s handler=%s",
            event_type.__name__,
            getattr(handler, "__qualname__", repr(handler)),
        )

    def subscribe_all(self, handler: EventHandler) -> None:
        """Register a handler that receives every event.

        Useful for cross-cutting concerns (audit, metrics) that
        shouldn't enumerate every event type by hand.
        """
        self._global_handlers.append(handler)

    async def publish(self, event: Event) -> None:
        """Enqueue ``event`` for dispatch.

        Returns immediately; subscriber execution is async + happens
        on the consumer task.  Callers that need to wait for the
        dispatch to complete should use a different pattern (the bus
        is intentionally fire-and-forget).
        """
        logger.info(
            "EVENTBUS_PUBLISH event_type=%s event_id=%s source=%s",
            event.event_type,
            event.id,
            event.source,
        )
        await self._queue.put(event)

    async def start(self) -> None:
        """Spawn the consumer task. Idempotent."""
        if self._running:
            return
        self._running = True
        self._processor_task = asyncio.create_task(
            self._process_events(), name="event-bus-consumer"
        )
        logger.info("EVENTBUS_START")

    async def stop(self) -> None:
        """Cancel the consumer + wait for graceful shutdown. Idempotent."""
        if not self._running:
            return
        self._running = False
        if self._processor_task is not None:
            self._processor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._processor_task
        logger.info("EVENTBUS_STOP")

    async def _process_events(self) -> None:
        """Consumer task — pop one event at a time and dispatch."""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._queue.get(), timeout=_QUEUE_POLL_INTERVAL_SECONDS
                )
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            await self._dispatch(event)

    async def _dispatch(self, event: Event) -> None:
        """Run every matching handler concurrently with error isolation."""
        handlers: list[EventHandler] = list(self._global_handlers)
        for event_type, type_handlers in self._handlers.items():
            if isinstance(event, event_type):
                handlers.extend(type_handlers)
        if not handlers:
            logger.debug(
                "EVENTBUS_NO_HANDLERS event_type=%s event_id=%s",
                event.event_type,
                event.id,
            )
            return
        results = await asyncio.gather(
            *(self._safe_call(handler, event) for handler in handlers),
            return_exceptions=True,
        )
        for handler, result in zip(handlers, results, strict=True):
            if isinstance(result, BaseException):
                logger.error(
                    "EVENTBUS_HANDLER_FAILED event_type=%s event_id=%s handler=%s error=%s",
                    event.event_type,
                    event.id,
                    getattr(handler, "__qualname__", repr(handler)),
                    result,
                )

    @staticmethod
    async def _safe_call(handler: EventHandler, event: Event) -> None:
        """Wrap a handler so an exception surfaces in ``gather``'s results."""
        await handler(event)
