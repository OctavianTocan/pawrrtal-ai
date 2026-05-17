"""Shared LLM turn pipeline for chat surfaces."""

from __future__ import annotations

import logging
import time
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels._turn_cost import record_turn_cost_if_enabled
from app.channels._turn_workspace import workspace_system_prompt
from app.core.chat_aggregator import ChatTurnAggregator, should_emit_event
from app.core.config import settings
from app.core.event_bus import TurnCompletedEvent, publish_if_available
from app.core.lcm import assemble_context as lcm_assemble_context
from app.core.lcm import ingest_message as lcm_ingest_message
from app.core.lcm.background import schedule_lcm_compaction
from app.core.observability import (
    aggregator_stop_reason,
    build_llm_view_messages,
    llm_span,
    turn_span,
    workshop_event_hook,
)
from app.crud.chat_message import (
    append_assistant_placeholder,
    append_user_message,
    finalize_assistant_message,
    get_messages_for_conversation,
)
from app.db import async_session_maker

if TYPE_CHECKING:
    from app.channels.base import Channel, ChannelMessage
    from app.core.agent_loop.types import AgentTool, PermissionCheckFn
    from app.core.providers.base import AILLM, ReasoningEffort, StreamEvent

logger = logging.getLogger(__name__)

EventHook = Callable[["StreamEvent"], list["StreamEvent"]]

# Fallback for the Workshop LLM span's ``gen_ai.request.model`` attribute
# when the channel envelope arrives without a resolved model id (e.g.
# Telegram surfaces that haven't selected one yet). Workshop tolerates
# any string here but a recognisable placeholder makes it obvious in the
# UI that the model wasn't pinned for this turn.
_MODEL_ID_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ChatTurnInput:
    """Resolved inputs for one persisted user/assistant turn."""

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
    # PR 03b — cross-provider can_use_tool gate. None preserves the
    # historical behaviour (no permission check); when supplied, the
    # provider plumbs it into AgentLoopConfig (Gemini) or
    # ClaudeAgentOptions.can_use_tool (Claude) so the same policy
    # applies regardless of model.
    permission_check: PermissionCheckFn | None = None
    # PR 09 — multimodal image inputs forwarded to the provider.  Each
    # entry is ``{"data": <base64>, "media_type": "image/<mime>"}`` —
    # the same wire shape ``ChatRequest.images`` carries on the API
    # boundary.  ``None`` (the default) is the legacy text-only path.
    images: list[dict[str, str]] | None = None
    history_window: int = 20
    log_tag: str = "TURN"
    log_extras: dict[str, Any] = field(default_factory=dict)
    verbose_level: int | None = None


@dataclass
class _EventCounter:
    """Mutable counter shared with the nested provider-stream wrapper.

    ``value`` is the total event count (kept for backwards-compatible logs).
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


async def run_turn(
    turn_input: ChatTurnInput,
    *,
    event_hooks: list[EventHook] | None = None,
) -> AsyncIterator[bytes]:
    """Persist, stream, deliver, and finalize one chat turn.

    Wraps the turn body in a Workshop-compatible OTel ``turn_span`` so
    every LLM stream and tool call dispatched downstream lands in the
    same trace.  When telemetry is disabled the spans are no-ops and
    add zero overhead (see ``app.core.telemetry.setup_tracing``).

    ``_finalize_turn`` runs **inside** ``turn_span`` but **outside**
    ``llm_span``: a database failure during persist + cost-ledger write
    is a turn-level problem, not an LLM problem, so it must not bleed
    into ``llm_span``'s error path (which would otherwise mark a
    successful LLM call as ``Status.ERROR`` with a database message).
    """
    started_at = time.perf_counter()
    history, assistant_message_id = await _load_history_and_persist(turn_input)
    system_prompt = workspace_system_prompt(turn_input.workspace_root)
    aggregator = ChatTurnAggregator()
    counter = _EventCounter()
    model_id = _channel_model_id(turn_input.channel_message)

    with turn_span(
        conversation_id=turn_input.conversation_id,
        user_id=turn_input.user_id,
        surface=turn_input.log_tag,
        request_id=_request_id_from_extras(turn_input.log_extras),
        model_id=model_id,
    ):
        try:
            async for chunk in _stream_with_llm_span(
                turn_input=turn_input,
                history=history,
                system_prompt=system_prompt,
                aggregator=aggregator,
                counter=counter,
                event_hooks=event_hooks,
                model_id=model_id,
            ):
                yield chunk
        finally:
            await _finalize_turn(
                turn_input=turn_input,
                aggregator=aggregator,
                assistant_message_id=assistant_message_id,
                started_at=started_at,
                event_count=counter.value,
                event_breakdown=counter.by_type,
            )


async def _stream_with_llm_span(
    *,
    turn_input: ChatTurnInput,
    history: list[dict[str, str]],
    system_prompt: str | None,
    aggregator: ChatTurnAggregator,
    counter: _EventCounter,
    event_hooks: list[EventHook] | None,
    model_id: str | None,
) -> AsyncIterator[bytes]:
    """Yield channel chunks under one ``llm_span`` context manager.

    Pulled out of ``run_turn`` for two reasons:

    1. Keeps the function below the project's nesting-depth budget
       (``scripts/check-nesting.py``).
    2. Scopes ``llm_span`` to the provider/channel stream only — so
       a downstream database error in ``_finalize_turn`` cannot be
       caught by ``llm_span``'s ``except`` clause and stamped as an
       LLM error.

    Workshop's UI panel for ``gen_ai.input.messages`` shows whatever
    list this function passes in — the full ``history`` plus the new
    user turn — so operators debugging a multi-turn conversation
    see the same context the provider sees.
    """
    with llm_span(
        model_id=model_id or _MODEL_ID_UNKNOWN,
        messages=build_llm_view_messages(history, turn_input.question),
        system_prompt=system_prompt,
    ) as llm_recorder:
        hooks = [workshop_event_hook(llm_recorder), *(event_hooks or [])]
        try:
            async for chunk in turn_input.channel.deliver(
                _guarded_stream(
                    turn_input=turn_input,
                    history=history,
                    system_prompt=system_prompt,
                    aggregator=aggregator,
                    counter=counter,
                    hooks=hooks,
                ),
                turn_input.channel_message,
            ):
                yield chunk
        finally:
            llm_recorder.record_stop(aggregator_stop_reason(aggregator))
            llm_recorder.record_usage(
                input_tokens=aggregator.total_input_tokens,
                output_tokens=aggregator.total_output_tokens,
                cost_usd=aggregator.total_cost_usd,
            )


async def _guarded_stream(
    *,
    turn_input: ChatTurnInput,
    history: list[dict[str, str]],
    system_prompt: str | None,
    aggregator: ChatTurnAggregator,
    counter: _EventCounter,
    hooks: list[EventHook],
) -> AsyncIterator[StreamEvent]:
    """Yield provider events through the aggregator + hook fan-out.

    Pulled out of ``run_turn`` so the surrounding observability
    context-managers don't make the function exceed the project's
    nesting budget.  The behaviour is identical to the previous
    inline closure — any provider exception is logged, surfaced as an
    ``error`` ``StreamEvent``, and the generator exits cleanly so the
    channel deliverer can finish its turn-level chrome.
    """
    try:
        async for event in turn_input.provider.stream(
            turn_input.question,
            turn_input.conversation_id,
            turn_input.user_id,
            history=history,
            tools=turn_input.tools or None,
            system_prompt=system_prompt,
            reasoning_effort=turn_input.reasoning_effort,
            permission_check=turn_input.permission_check,
            images=turn_input.images,
        ):
            if not _should_deliver_event(event, turn_input.verbose_level):
                continue
            counter.record(event)
            aggregator.apply(event)
            yield event
            for extra in _expand_hook_events(event, hooks):
                counter.record(extra)
                aggregator.apply(extra)
                yield extra
    except Exception as exc:
        logger.exception(
            "%s_STREAM_ERR conversation_id=%s after %d events",
            turn_input.log_tag,
            turn_input.conversation_id,
            counter.value,
        )
        error_event: StreamEvent = {"type": "error", "content": str(exc)}
        counter.record(error_event)
        aggregator.apply(error_event)
        yield error_event


def _request_id_from_extras(extras: dict[str, Any]) -> str:
    """Pull the request id from ``log_extras`` (set by the chat router)."""
    raw = extras.get("request_id", "") if extras else ""
    return str(raw) if raw is not None else ""


def _channel_model_id(channel_message: ChannelMessage | None) -> str | None:
    """Return the ``model_id`` from the channel envelope, or ``None``."""
    if not channel_message:
        return None
    model_id = channel_message.get("model_id")
    return str(model_id) if model_id else None


def _expand_hook_events(
    event: StreamEvent,
    hooks: list[EventHook],
) -> Iterator[StreamEvent]:
    """Yield extra events produced by each hook for the upstream event."""
    for hook in hooks:
        yield from hook(event)


def _should_deliver_event(event: StreamEvent, verbose_level: int | None) -> bool:
    """Apply per-channel verbosity filtering when a channel requests it."""
    if verbose_level is None:
        return True
    return should_emit_event(event, verbose_level)


async def _load_history_and_persist(
    turn_input: ChatTurnInput,
) -> tuple[list[dict[str, str]], uuid.UUID]:
    """Read recent history, then persist the current user turn and placeholder.

    When ``settings.lcm_enabled`` is ``True``, the history slice is
    assembled from the LCM context list (``lcm_context_items``) so that
    compacted summaries are visible to the provider, and both the user
    turn and assistant placeholder are ingested into the LCM context
    list before the stream starts.  When LCM is off the behaviour is
    unchanged — a raw ``LIMIT history_window`` query over
    ``chat_messages``.
    """
    async with _turn_session(turn_input) as session:
        if settings.lcm_enabled:
            history = await lcm_assemble_context(
                session,
                conversation_id=turn_input.conversation_id,
                fresh_tail_count=settings.lcm_fresh_tail_count,
            )
        else:
            recent_rows = await get_messages_for_conversation(
                session,
                turn_input.conversation_id,
                limit=turn_input.history_window,
            )
            history = [
                {"role": row.role, "content": row.content or ""}
                for row in recent_rows
                if row.role in {"user", "assistant"}
            ]
        user_msg = await append_user_message(
            session,
            conversation_id=turn_input.conversation_id,
            user_id=turn_input.user_id,
            content=turn_input.question,
        )
        assistant_row = await append_assistant_placeholder(
            session,
            conversation_id=turn_input.conversation_id,
            user_id=turn_input.user_id,
        )
        if settings.lcm_enabled:
            await lcm_ingest_message(
                session,
                conversation_id=turn_input.conversation_id,
                message_id=user_msg.id,
            )
            await lcm_ingest_message(
                session,
                conversation_id=turn_input.conversation_id,
                message_id=assistant_row.id,
            )
        await session.commit()
        return history, assistant_row.id


@asynccontextmanager
async def _turn_session(turn_input: ChatTurnInput) -> AsyncIterator[AsyncSession]:
    """Yield the request session when provided, otherwise open a runner session."""
    if turn_input.db_session is not None:
        yield turn_input.db_session
        return
    async with async_session_maker() as session:
        yield session


def _workspace_system_prompt(workspace_root: Path | None) -> str | None:
    """Compatibility wrapper for tests and older internal imports."""
    return workspace_system_prompt(workspace_root)


async def _finalize_turn(
    *,
    turn_input: ChatTurnInput,
    aggregator: ChatTurnAggregator,
    assistant_message_id: uuid.UUID,
    started_at: float,
    event_count: int,
    event_breakdown: Counter[str],
) -> None:
    """Patch the assistant placeholder with the final aggregated stream state."""
    duration_ms = (time.perf_counter() - started_at) * 1000
    final_status = "failed" if aggregator.error_text else "complete"
    snapshot = aggregator.to_persisted_shape(status=final_status)
    try:
        async with _turn_session(turn_input) as session:
            await finalize_assistant_message(
                session,
                message_id=assistant_message_id,
                **snapshot,
            )
            # Cost ledger write (PR 04). Same session as the message
            # persist so a failed commit leaves no orphaned ledger row.
            # Runs for every surface (web + Telegram) so the per-user
            # cap applies uniformly.
            channel_message = turn_input.channel_message
            cost_model_id = (channel_message.get("model_id") or "") if channel_message else ""
            cost_surface = (channel_message.get("surface") or "") if channel_message else ""
            await record_turn_cost_if_enabled(
                session=session,
                aggregator=aggregator,
                user_id=turn_input.user_id,
                conversation_id=turn_input.conversation_id,
                model_id=cost_model_id,
                surface=cost_surface,
                log_tag=turn_input.log_tag,
            )
            await session.commit()
    except Exception:
        logger.exception(
            "%s_PERSIST_ERR conversation_id=%s message_id=%s",
            turn_input.log_tag,
            turn_input.conversation_id,
            assistant_message_id,
        )

    extras = " ".join(f"{key}={value}" for key, value in turn_input.log_extras.items())
    breakdown = (
        " ".join(f"{name}={count}" for name, count in sorted(event_breakdown.items())) or "none"
    )
    logger.info(
        "%s_OUT conversation_id=%s events=%d duration_ms=%.1f breakdown=[%s] %s",
        turn_input.log_tag,
        turn_input.conversation_id,
        event_count,
        duration_ms,
        breakdown,
        extras,
    )
    # PR 10: announce completion (success / failure both surface here
    # because the caller wraps run_turn in a try/finally).  Subscribers
    # can react to spend, latency, etc.
    surface = (
        (turn_input.channel_message.get("surface") or "") if turn_input.channel_message else ""
    )
    model_id = (
        (turn_input.channel_message.get("model_id") or "") if turn_input.channel_message else ""
    )
    await publish_if_available(
        TurnCompletedEvent(
            user_id=turn_input.user_id,
            conversation_id=turn_input.conversation_id,
            surface=surface,
            model_id=model_id,
            status=final_status,
            duration_ms=duration_ms,
            cost_usd=aggregator.total_cost_usd,
            source=turn_input.log_tag.lower(),
        )
    )
    # Fire-and-forget LCM leaf compaction.  Runs after the assistant row is
    # finalized so the just-completed turn is eligible for compaction.
    # The helper handles the ``settings.lcm_enabled`` gate, task-strong-ref
    # bookkeeping, and exception suppression in one place.
    schedule_lcm_compaction(
        conversation_id=turn_input.conversation_id,
        user_id=turn_input.user_id,
        model_id=model_id or "",
    )
