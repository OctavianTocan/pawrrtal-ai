"""Async pub/sub event bus + concrete event vocabulary.

Decouples event sources (chat router emits ``TurnStartedEvent``,
webhook receiver emits ``WebhookEvent``, scheduler emits
``ScheduledEvent``) from handlers (``AgentHandler`` runs a Claude
turn for webhook/scheduled events; future ``NotificationService``
delivers ``AgentResponseEvent`` to Telegram).

The bus is import-cycle-safe because it lives under
``app.infrastructure.event_bus`` and only imports from ``app.providers``
indirectly through the handler modules — the bus itself has zero
domain knowledge.

Process model
-------------
Single asyncio queue, one consumer task running inside the FastAPI
lifespan.  Concurrent dispatch — every handler subscribed to a
matching event runs in parallel via ``asyncio.gather``, and a
crash in one handler never affects siblings (errors are caught
+ logged, never re-raised).

This matches CCT's design but adapted to our typed event vocabulary;
see ``.claude/rules/architecture/no-tools-in-providers.md`` for why
the bus + agent handler split lives outside ``providers/``.
"""

from app.infrastructure.event_bus.bus import Event, EventBus, EventHandler
from app.infrastructure.event_bus.global_bus import publish_if_available
from app.infrastructure.event_bus.handlers import AgentHandler, NotificationService
from app.infrastructure.event_bus.types import (
    AgentResponseEvent,
    ScheduledEvent,
    TurnCompletedEvent,
    TurnStartedEvent,
    WebhookEvent,
)

__all__ = [
    "AgentHandler",
    "AgentResponseEvent",
    "Event",
    "EventBus",
    "EventHandler",
    "NotificationService",
    "ScheduledEvent",
    "TurnCompletedEvent",
    "TurnStartedEvent",
    "WebhookEvent",
    "publish_if_available",
]
