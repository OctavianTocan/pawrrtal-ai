"""Event bus types for the subagent system.

Kept separate from ``app.core.event_bus.types`` because the subagent
events are an internal detail of one feature, while the chat-side
events are part of the cross-cutting event vocabulary that the
notification service and audit consumers subscribe to.  Co-locating
both here means a feature change in subagents doesn't ripple into
``event_bus.types``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.event_bus.bus import Event


@dataclass
class SubagentCompletedEvent(Event):
    """A background subagent task has finished (success, failure, or cancel).

    Published from :func:`app.core.subagents.runner._run_subagent`'s
    ``finally`` block so every terminal state surfaces exactly once.
    The ``wait_for_subagents`` tool (PR 4) subscribes to filter on
    ``handle``; the cost-ledger consumer and audit handlers can
    subscribe via ``subscribe_all`` to see every completion.

    ``status`` is one of :data:`app.subagent_models.SUBAGENT_STATUSES`'s
    terminal members.  ``result`` is populated on ``"succeeded"`` only;
    ``error`` is the human-readable failure reason for the other two
    terminal states.
    """

    subagent_id: uuid.UUID | None = None
    handle: str = ""
    conversation_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    persona_name: str = ""
    status: str = ""
    result: str | None = None
    error: str | None = None
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    source: str = "subagent"


__all__ = ["SubagentCompletedEvent"]
