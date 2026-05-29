"""Process-global :class:`EventBus` accessor.

The bus lives on ``app.state.event_bus`` (set in the FastAPI lifespan)
but the chat router's streaming generator runs in a fresh task that
doesn't carry the request context.  Rather than thread the bus
through every helper, we cache it on a module-level singleton at
lifespan startup.

Why a module global instead of a contextvar:
* The bus is genuinely process-wide — there's exactly one per FastAPI
  app instance.
* Async tasks spawned via ``asyncio.create_task`` don't inherit
  contextvars by default; threading would require explicit propagation
  at every spawn.
* Tests can call :func:`set_event_bus` with a ``None`` to short-circuit
  emission entirely, keeping unit tests provider-bus-independent.
"""

from __future__ import annotations

import logging

from app.infrastructure.event_bus.bus import Event, EventBus

logger = logging.getLogger(__name__)

_bus: EventBus | None = None


def set_event_bus(bus: EventBus | None) -> None:
    """Register the process-wide bus.  Idempotent.

    Called once from the FastAPI lifespan.  Tests use this to inject
    a fresh bus per case (or ``None`` to disable emission).
    """
    global _bus  # noqa: PLW0603 — module-level singleton is the design (process-wide bus, async-task-safe)
    _bus = bus


def get_event_bus() -> EventBus | None:
    """Return the registered bus, or ``None`` when unset."""
    return _bus


async def publish_if_available(event: Event) -> None:
    """Fire-and-forget publish that no-ops when the bus is unset.

    Use this from request handlers / streaming generators that can
    run in test environments without a bus.  Errors are caught +
    logged so an event-bus failure never breaks the chat path.
    """
    bus = _bus
    if bus is None:
        return
    try:
        await bus.publish(event)
    except Exception:
        logger.exception("EVENTBUS_PUBLISH_FAILED event_type=%s", event.event_type)
