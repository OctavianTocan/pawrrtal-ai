"""Shared turn input and event-hook types."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.plugins.adapters.turn_context import TurnContextProviderAdapter
from app.provider_sessions import ProviderSessionTurnState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.agents.types import AgentTool
    from app.channels.base import Channel, ChannelMessage
    from app.providers.base import AILLM, ReasoningEffort, StreamEvent

EventHook = Callable[["StreamEvent"], list["StreamEvent"]]


@dataclass(frozen=True)
class ChatTurnInput:
    """Resolved inputs for one persisted user/assistant turn.

    Attributes:
        conversation_id: The conversation UUID.
        user_id: The user UUID.
        question: The user message.
        provider: The LLM provider.
        channel: The channel.
        channel_message: The channel message.
        db_session: The database session.
        workspace_root: The workspace root path.
        tools: The workspace-scoped agent tools.
        reasoning_effort: The reasoning effort.
        images: The multimodal image inputs.
        history_window: The history window.
        log_tag: The log tag.
        log_extras: The log extras.
        verbose_level: The verbose level.
        provider_session: Opaque provider continuity state prepared by the provider.
        turn_context_providers: Plugin context providers run before the main model turn.
    """

    conversation_id: uuid.UUID
    user_id: uuid.UUID
    question: str
    provider: AILLM
    channel: Channel
    channel_message: ChannelMessage
    db_session: AsyncSession | None = field(default=None, repr=False, compare=False)
    workspace_root: Path | None = None
    tools: list[AgentTool] | None = None
    reasoning_effort: ReasoningEffort | None = None
    # Multimodal image inputs in the same wire shape as ChatRequest.images.
    # None indicates a text-only turn.
    images: list[dict[str, str]] | None = None
    history_window: int = 20
    log_tag: str = "TURN"
    log_extras: dict[str, Any] = field(default_factory=dict)
    verbose_level: int | None = None
    provider_session: ProviderSessionTurnState = field(default_factory=ProviderSessionTurnState)
    turn_context_providers: list[TurnContextProviderAdapter] | None = None
    # Optional callback for context providers to stream draft status back to the channel.
    draft_updater: Callable[[str], Awaitable[None]] | None = None
    on_turn_context_finished: Callable[[], Awaitable[None]] | None = None


@dataclass
class _EventCounter:
    """Mutable counter shared with the nested provider-stream wrapper.

    ``value`` is the total event count, used in error logs and turn
    finalisation.
    ``by_type`` is the per-event-type breakdown so the postmortem log line
    can answer "what kinds of 51 events did this turn produce?" — invaluable
    when debugging stuck Telegram placeholders or runaway tool loops.
    """

    value: int = 0
    by_type: Counter[str] = field(default_factory=Counter)

    def record(self, event: StreamEvent) -> None:
        """Increment both the total and the per-type bucket for *event*."""
        self.value += 1
        self.by_type[event.get("type", "unknown")] += 1
