"""Chat-router event-bus emission helpers.

Extracted from :mod:`app.api.chat` to keep that module's fan-out under
the sentrux god-file threshold (15). The event-bus module pair adds two
import edges; concentrating them here lets the chat router stay below
the cap while still emitting lifecycle events.
"""

from __future__ import annotations

import uuid

from app.core.event_bus import TurnStartedEvent
from app.core.event_bus.global_bus import publish_if_available


async def publish_turn_started(
    *,
    user_id: uuid.UUID | None,
    conversation_id: uuid.UUID | None,
    surface: str,
    model_id: str,
    source: str = "chat",
) -> None:
    """Fire a ``TurnStartedEvent`` if the global event bus is wired up.

    No-ops when the bus is unset (unit tests, fastapi TestClient without
    lifespan) so callers don't need to special-case bus setup.
    """
    await publish_if_available(
        TurnStartedEvent(
            user_id=user_id,
            conversation_id=conversation_id,
            surface=surface,
            model_id=model_id,
            source=source,
        )
    )
