"""Concrete event types the bus dispatches.

Vocabulary mirrors CCT's so the AgentHandler ports cleanly:

* :class:`TurnStartedEvent` / :class:`TurnCompletedEvent` — emitted by
  the chat router (web) and Telegram turn_stream around every agent
  turn.  Subscribers can use these for metrics, audit, side-effects.
* :class:`WebhookEvent` — emitted by the webhook receiver (PR 11).
  Subscribed by :class:`AgentHandler` which translates into an
  agent turn.
* :class:`ScheduledEvent` — emitted by the scheduler (PR 12).  Same
  AgentHandler subscribes.
* :class:`AgentResponseEvent` — emitted by AgentHandler with the
  response text.  Subscribed by the notification service that
  delivers to Telegram / web.

Every concrete event extends :class:`Event`, so cross-cutting
``subscribe_all`` consumers (audit, metrics) see everything without
enumerating types.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.event_bus.bus import Event


@dataclass
class TurnStartedEvent(Event):
    """One agent turn has begun.

    Emitted by the chat router (web) and the Telegram turn_stream
    just before the provider stream starts.  Subscribers can use this
    for "agent is busy" indicators, per-user concurrency tracking,
    etc.
    """

    user_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    surface: str = "unknown"
    model_id: str | None = None
    source: str = "chat"


@dataclass
class TurnCompletedEvent(Event):
    """One agent turn has finished (successfully or not).

    Emitted from the same code path's ``finally`` block so a
    cancelled / errored turn still surfaces.  ``status`` is one of
    ``"complete"``, ``"failed"``, ``"cancelled"``.
    """

    user_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    surface: str = "unknown"
    model_id: str | None = None
    status: str = "complete"
    duration_ms: float | None = None
    # PR (latency metrics): wall-clock elapsed from turn start to the
    # first user-visible event.  ``None`` when the turn produced no
    # event (provider error before any token).  Surfaced so subscribers
    # — metrics rollups, slow-request alerts — can compute provider
    # responsiveness without re-deriving it from span exports.
    ttft_ms: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    source: str = "chat"


@dataclass
class WebhookEvent(Event):
    """One inbound webhook delivery (already deduped + signature-verified).

    The webhook receiver (PR 11) writes the row to ``webhook_events``
    + publishes this event.  AgentHandler subscribes and runs an
    agent turn against the payload summary.
    """

    provider: str = ""
    event_type_name: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    delivery_id: str = ""
    user_id: uuid.UUID | None = None
    source: str = "webhook"


@dataclass
class ScheduledEvent(Event):
    """One scheduled-job firing.

    The scheduler (PR 12) reads the ``scheduled_jobs`` row, builds
    this event, publishes.  AgentHandler subscribes and runs the
    job's prompt as an agent turn.  ``target_chat_ids`` lets the
    notification service know which Telegram chats to deliver the
    response to.
    """

    job_id: uuid.UUID | None = None
    job_name: str = ""
    prompt: str = ""
    skill_name: str | None = None
    target_chat_ids: list[str] = field(default_factory=list)
    # When set, AgentHandler persists the response as an assistant
    # message in this conversation before publishing AgentResponseEvent.
    # Used by the heartbeat sync to surface scheduled output in the
    # web chat UI (the conversation is auto-created with a "heartbeat"
    # label so the sidebar can pin it). Optional so general webhook +
    # scheduled flows that only target Telegram stay unchanged.
    target_conversation_id: uuid.UUID | None = None
    working_directory: Path | None = None
    user_id: uuid.UUID | None = None
    source: str = "scheduler"


@dataclass
class AgentResponseEvent(Event):
    """An agent turn produced text + needs to be delivered.

    Emitted by AgentHandler after a webhook / scheduled run.  The
    notification service subscribes and sends to the configured
    Telegram chats.  The ``originating_event_id`` field lets the
    delivery layer correlate back to the inbound event.
    """

    user_id: uuid.UUID | None = None
    chat_id: str | None = None
    text: str = ""
    originating_event_id: str | None = None
    source: str = "agent"
