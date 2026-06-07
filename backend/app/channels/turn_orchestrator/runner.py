"""Persisted turn runner and provider stream delivery."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from typing import TYPE_CHECKING, Any

from app.channels._turn_runtime_context import system_prompt_for_turn
from app.chat.aggregator import ChatTurnAggregator, should_emit_event
from app.infrastructure.observability import (
    TurnSpanRecorder,
    aggregator_stop_reason,
    build_llm_view_messages,
    llm_span,
    turn_span,
    workshop_event_hook,
)
from app.provider_sessions import (
    _register_provider_session_persist_task,
    persist_provider_session,
)

from .context_providers import _run_turn_context_providers
from .finalize import _finalize_turn
from .history import _load_history_and_persist
from .state import _register_turn_finalize_task
from .types import ChatTurnInput, EventHook, _EventCounter

if TYPE_CHECKING:
    from app.channels.base import ChannelMessage
    from app.providers.base import ReasoningEffort, StreamEvent

logger = logging.getLogger(__name__)
_MODEL_ID_UNKNOWN = "unknown"


async def run_turn(
    turn_input: ChatTurnInput,
    *,
    event_hooks: list[EventHook] | None = None,
) -> AsyncIterator[bytes]:
    """Persist, stream, deliver, and finalize one chat turn.

    Wraps the turn body in a Workshop-compatible OTel ``turn_span`` so
    every LLM stream and tool call dispatched downstream lands in the
    same trace.  When telemetry is disabled the spans are no-ops and
    add zero overhead (see ``app.infrastructure.telemetry.setup_tracing``).

    ``_finalize_turn`` is idempotently triggered before the channel sees
    end-of-stream. This lets SSE finalize the assistant row before it emits
    ``[DONE]``, so clients that stop reading at the terminal frame cannot
    race the persistence path.
    """
    started_at = time.perf_counter()
    history, assistant_message_id = await _load_history_and_persist(turn_input)

    # --- Turn context providers ---
    turn_context: str | None = None
    turn_context = await _run_turn_context_providers(turn_input)
    if turn_input.on_turn_context_finished:
        await turn_input.on_turn_context_finished()

    # --- Main turn ---
    aggregator = ChatTurnAggregator()
    counter = _EventCounter()
    model_id = _channel_model_id(turn_input.channel_message)
    # Compose the per-turn system prompt: workspace identity files +
    # runtime metadata (current time, model/provider, iteration budget,
    # tool inventory) appended on every turn so the model never has to
    # guess at its environment.  See issues #289, #291, #294, #309 and
    # ``app.channels._turn_runtime_context`` for the rationale.
    system_prompt: str | None = system_prompt_for_turn(
        turn_input.workspace_root,
        model_id=model_id,
        tools=turn_input.tools,
        extra_context=turn_context,
        reasoning_effort=turn_input.reasoning_effort,
    )

    with turn_span(
        conversation_id=turn_input.conversation_id,
        user_id=turn_input.user_id,
        surface=turn_input.log_tag,
        request_id=_request_id_from_extras(turn_input.log_extras),
        model_id=model_id,
    ) as turn_recorder:
        finalized = False

        async def finalize_once() -> None:
            nonlocal finalized
            if finalized:
                return
            finalized = True
            await _finalize_turn(
                turn_input=turn_input,
                aggregator=aggregator,
                assistant_message_id=assistant_message_id,
                started_at=started_at,
                event_count=counter.value,
                event_breakdown=counter.by_type,
                ttft_ms=turn_recorder.ttft_ms,
            )

        try:
            async for chunk in _stream_with_llm_span(
                turn_input=turn_input,
                history=history,
                system_prompt=system_prompt,
                per_turn_context=turn_context,
                aggregator=aggregator,
                counter=counter,
                event_hooks=event_hooks,
                model_id=model_id,
                turn_recorder=turn_recorder,
                finalize_turn=finalize_once,
            ):
                yield chunk
        finally:
            await finalize_once()


async def _stream_with_llm_span(
    *,
    turn_input: ChatTurnInput,
    history: list[dict[str, str]],
    system_prompt: str | None,
    per_turn_context: str | None,
    aggregator: ChatTurnAggregator,
    counter: _EventCounter,
    event_hooks: list[EventHook] | None,
    model_id: str | None,
    turn_recorder: TurnSpanRecorder,
    finalize_turn: Callable[[], Coroutine[Any, Any, None]],
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

    async def event_stream() -> AsyncIterator[StreamEvent]:
        with llm_span(
            model_id=model_id or _MODEL_ID_UNKNOWN,
            messages=build_llm_view_messages(history, turn_input.question),
            system_prompt=system_prompt,
        ) as llm_recorder:
            hooks = [
                workshop_event_hook(llm_recorder, turn_recorder=turn_recorder),
                *(event_hooks or []),
            ]
            try:
                async for event in _guarded_stream(
                    turn_input=turn_input,
                    history=history,
                    system_prompt=system_prompt,
                    per_turn_context=per_turn_context,
                    aggregator=aggregator,
                    counter=counter,
                    hooks=hooks,
                ):
                    yield event
            finally:
                llm_recorder.record_stop(aggregator_stop_reason(aggregator))
                llm_recorder.record_usage(
                    input_tokens=aggregator.total_input_tokens,
                    output_tokens=aggregator.total_output_tokens,
                    cost_usd=aggregator.total_cost_usd,
                )

    stream = _finalizing_stream(event_stream(), finalize_turn)
    async for chunk in turn_input.channel.deliver(
        stream,
        turn_input.channel_message,
    ):
        yield chunk


async def _finalizing_stream(
    stream: AsyncIterator[StreamEvent],
    finalize_turn: Callable[[], Coroutine[Any, Any, None]],
) -> AsyncIterator[StreamEvent]:
    """Finalize the turn before the channel observes end-of-stream."""
    try:
        async for event in stream:
            yield event
    finally:
        finalize_task: asyncio.Task[None] = asyncio.create_task(finalize_turn())
        _register_turn_finalize_task(finalize_task)
        await asyncio.shield(finalize_task)


async def _guarded_stream(
    *,
    turn_input: ChatTurnInput,
    history: list[dict[str, str]],
    system_prompt: str | None,
    per_turn_context: str | None,
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
    provider_session = turn_input.provider_session
    extra_kwargs: dict[str, Any] = dict(provider_session.stream_kwargs)
    provider_history = [] if provider_session.omit_history else history
    if provider_session.per_turn_context_kwarg is not None:
        extra_kwargs[provider_session.per_turn_context_kwarg] = per_turn_context
    try:
        async for event in turn_input.provider.stream(
            turn_input.question,
            turn_input.conversation_id,
            turn_input.user_id,
            history=provider_history,
            tools=turn_input.tools or None,
            system_prompt=system_prompt,
            reasoning_effort=_provider_reasoning_effort(turn_input),
            images=turn_input.images,
            **extra_kwargs,
        ):
            # Hooks fire BEFORE the verbose filter so observability sees
            # every provider event — including thinking-deltas at
            # ``verbose_level < 2``, which the filter would otherwise
            # drop before the Workshop span recorder ever sees them
            # (#347). The hook contract for ``workshop_event_hook``
            # returns ``[]`` (side-effects only); extras from any
            # future hook stay behind the filter so /verbose still
            # gates what the channel renders.
            extras = list(_expand_hook_events(event, hooks))
            if await _handle_internal_provider_event(event, turn_input):
                continue
            if not _should_deliver_event(event, turn_input.verbose_level):
                continue

            if event.get("transient"):
                yield event
                continue

            counter.record(event)
            aggregator.apply(event)
            yield event
            for extra in extras:
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


async def _handle_internal_provider_event(
    event: StreamEvent,
    turn_input: ChatTurnInput,
) -> bool:
    """Handle provider-internal signals and return whether the event was consumed."""
    if event.get("type") != "internal":
        return False
    if event.get("kind") != "provider_session_created":
        return True
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return True
    provider = event.get("provider")
    provider_kind = provider if isinstance(provider, str) else turn_input.provider_session.kind
    if provider_kind is None:
        return True
    # Detached task so the UPDATE survives cancellation of the streaming
    # response (SIGTERM mid-stream, client disconnect). We track a strong
    # reference so GC cannot collect it and lifespan shutdown drains it.
    persist_task = asyncio.create_task(
        persist_provider_session(
            turn_input.conversation_id,
            kind=provider_kind,
            session_id=session_id,
            fingerprint=turn_input.provider_session.fingerprint,
        )
    )
    _register_provider_session_persist_task(persist_task)
    await asyncio.shield(persist_task)
    return True


def _request_id_from_extras(extras: dict[str, Any]) -> str:
    """Pull the request id from ``log_extras`` (set by the chat router)."""
    raw = extras.get("request_id", "") if extras else ""
    return str(raw) if raw is not None else ""


def _channel_model_id(channel_message: ChannelMessage | None) -> str | None:
    """Return the ``model_id`` from the channel envelope, or ``None``."""
    if not channel_message:
        return None
    model_id = channel_message.get("model_id")
    return model_id if isinstance(model_id, str) else None


def _provider_reasoning_effort(turn_input: ChatTurnInput) -> ReasoningEffort | None:
    """Return the reasoning effort passed to the provider for this turn."""
    if turn_input.reasoning_effort is not None:
        return turn_input.reasoning_effort
    if turn_input.provider_session.force_low_reasoning:
        return "low"
    return None


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
