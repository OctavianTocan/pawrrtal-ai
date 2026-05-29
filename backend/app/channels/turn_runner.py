"""Shared LLM turn pipeline for chat surfaces."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import exc as sa_exc
from sqlalchemy import select, update

from app.agents.plugins.types import PreTurnHook, PreTurnHookContext
from app.channels._turn_cost import record_turn_cost_if_enabled
from app.channels._turn_runtime_context import system_prompt_for_turn
from app.channels._turn_workspace import workspace_system_prompt
from app.chat.aggregator import ChatTurnAggregator, should_emit_event
from app.conversations.messages_crud import (
    append_assistant_placeholder,
    append_user_message,
    finalize_assistant_message,
    get_messages_for_conversation,
)
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import async_session_maker
from app.infrastructure.event_bus import TurnCompletedEvent, publish_if_available
from app.infrastructure.observability import (
    TurnSpanRecorder,
    aggregator_stop_reason,
    build_llm_view_messages,
    llm_span,
    turn_span,
    workshop_event_hook,
)
from app.lcm import (
    assemble_context as lcm_assemble_context,
)
from app.lcm import (
    ingest_message as lcm_ingest_message,
)
from app.lcm import (
    schedule_lcm_compaction,
)
from app.models import Conversation

# Strong references to in-flight codex_thread_id persist tasks so they
# survive (a) GC, and (b) cancellation of the streaming response.  The
# UPDATE itself is small (~1 ms) but a SIGTERM mid-stream cancels every
# awaitable in the request task tree; without an independent task here,
# the multi-turn Codex thread id would be silently lost between turns.
# Drained at app shutdown via ``await_pending_codex_persist_tasks``
# (called from ``main.lifespan``'s finally block).
_PENDING_CODEX_PERSIST_TASKS: set[asyncio.Task[None]] = set()

# Soft cap on the shutdown drain timeout. The UPDATE is small enough
# that 10 s is generous; tests can override.
_DEFAULT_PERSIST_DRAIN_TIMEOUT_S: float = 10.0


def _register_codex_persist_task(task: asyncio.Task[None]) -> None:
    """Track an in-flight persist task so shutdown can await it."""
    _PENDING_CODEX_PERSIST_TASKS.add(task)
    task.add_done_callback(_PENDING_CODEX_PERSIST_TASKS.discard)


async def await_pending_codex_persist_tasks(
    timeout: float = _DEFAULT_PERSIST_DRAIN_TIMEOUT_S,  # noqa: ASYNC109 — public shutdown drain; bound is the API
) -> None:
    """Wait for in-flight Codex thread-id persist tasks to finish.

    Called from the FastAPI lifespan shutdown handler so a graceful
    SIGTERM can complete the in-flight UPDATEs before the event loop
    exits. The ``timeout`` parameter caps how long shutdown will block;
    a soft warning surfaces when the deadline is exceeded so operators
    can correlate dropped thread ids with the shutdown event.

    ASYNC109 is intentional here — the drain is a public lifespan-
    shutdown surface where callers want a single bound on how long the
    cleanup can block. Wrapping with ``asyncio.timeout`` internally
    keeps the contract caller-friendly.
    """
    if not _PENDING_CODEX_PERSIST_TASKS:
        return
    pending = list(_PENDING_CODEX_PERSIST_TASKS)
    try:
        async with asyncio.timeout(timeout):
            await asyncio.gather(*pending, return_exceptions=True)
    except TimeoutError:
        # Surface the drop loud — operators need to know thread ids
        # may be lost from this shutdown cycle.
        outstanding = [t for t in pending if not t.done()]
        logger.warning(
            "codex: shutdown drain timed out after %.1fs; %d persist task(s) still running",
            timeout,
            len(outstanding),
        )


if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.agents.types import AgentTool, PermissionCheckFn
    from app.channels.base import Channel, ChannelMessage
    from app.providers.base import AILLM, ReasoningEffort, StreamEvent

logger = logging.getLogger(__name__)

EventHook = Callable[["StreamEvent"], list["StreamEvent"]]

# Fallback for the Workshop LLM span's ``gen_ai.request.model`` attribute
# when the channel envelope arrives without a resolved model id (e.g.
# Telegram surfaces that haven't selected one yet). Workshop tolerates
# any string here but a recognisable placeholder makes it obvious in the
# UI that the model wasn't pinned for this turn.
_MODEL_ID_UNKNOWN = "unknown"

# Seconds → milliseconds for the canonical CHAT_OUT / TELEGRAM_OUT log
# line and the ``TurnCompletedEvent.duration_ms`` payload.  Named so the
# magnitude is self-documenting rather than a bare ``* 1000``.
_MS_PER_SECOND_FOR_LOG = 1000

# Placeholder used in the canonical log line when a turn finished
# without ever producing a user-visible event (provider error before
# any token).  Cheaper than a conditional format string and keeps the
# field-position contract stable for log parsers.
_TTFT_LOG_MISSING = "-"


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
        permission_check: The permission check function.
        images: The multimodal image inputs.
        history_window: The history window.
        log_tag: The log tag.
        log_extras: The log extras.
        verbose_level: The verbose level.
        pre_turn_hooks: The pre-turn hooks.
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
    # PR 03b — cross-provider can_use_tool gate.  ``None`` (the
    # default) means no permission check; when supplied, the provider
    # plumbs it into AgentLoopConfig (Gemini) or
    # ClaudeAgentOptions.can_use_tool (Claude) so the same policy
    # applies regardless of model.
    permission_check: PermissionCheckFn | None = None
    # PR 09 — multimodal image inputs forwarded to the provider.  Each
    # entry is ``{"data": <base64>, "media_type": "image/<mime>"}`` —
    # the same wire shape ``ChatRequest.images`` carries on the API
    # boundary.  ``None`` (the default) indicates a text-only turn.
    images: list[dict[str, str]] | None = None
    history_window: int = 20
    log_tag: str = "TURN"
    log_extras: dict[str, Any] = field(default_factory=dict)
    verbose_level: int | None = None
    # For the native openai_codex provider: the Codex thread id to resume
    # if one was previously persisted for this conversation.
    codex_thread_id: str | None = None
    # These are the pre-turn hooks that will be run before the turn is started. They come from the plugin registry (for now).
    pre_turn_hooks: list[PreTurnHook] | None = None
    # Optional callback for pre-turn hooks to stream draft status back to the channel.
    draft_updater: Callable[[str], Awaitable[None]] | None = None
    on_pre_turn_finished: Callable[[], Awaitable[None]] | None = None


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


async def _run_pre_turn_hooks(turn_input: ChatTurnInput) -> str | None:
    # --- Pre-turn hooks ---
    if not turn_input.pre_turn_hooks:
        return None

    async def _run_single_hook(hook: PreTurnHook) -> str | None:
        hook_name = hook.__name__
        logger.info(
            "PRE_TURN_HOOK %s conversation_id=%s user_id=%s question=%s",
            hook_name,
            turn_input.conversation_id,
            turn_input.user_id,
            turn_input.question,
        )
        try:
            async with asyncio.timeout(settings.pre_turn_hook_timeout_seconds or 10):
                result = await hook(
                    PreTurnHookContext(
                        conversation_id=turn_input.conversation_id,
                        user_id=turn_input.user_id,
                        question=turn_input.question,
                        workspace_root=turn_input.workspace_root or Path(),
                        draft_updater=turn_input.draft_updater,
                    )
                )
                if result is not None:
                    logger.info(
                        "PRE_TURN_HOOK_SUCCESS %s conversation_id=%s user_id=%s hook_name=%s question=%s result=%s",
                        hook_name,
                        turn_input.conversation_id,
                        turn_input.user_id,
                        hook_name,
                        turn_input.question,
                        result,
                    )
                return result
        except Exception:
            logger.exception(
                "PRE_TURN_HOOK_ERR %s conversation_id=%s user_id=%s hook_name=%s question=%s",
                hook_name,
                turn_input.conversation_id,
                turn_input.user_id,
                hook_name,
                turn_input.question,
            )
            return None

    results = await asyncio.gather(
        *[_run_single_hook(hook) for hook in turn_input.pre_turn_hooks],
        return_exceptions=False,
    )

    pre_turn_added_context = [res for res in results if res is not None]
    if not pre_turn_added_context:
        return None

    return "# PRE-TURN CONTEXT\n\n" + "\n\n".join(pre_turn_added_context)


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

    ``_finalize_turn`` runs **inside** ``turn_span`` but **outside**
    ``llm_span``: a database failure during persist + cost-ledger write
    is a turn-level problem, not an LLM problem, so it must not bleed
    into ``llm_span``'s error path (which would otherwise mark a
    successful LLM call as ``Status.ERROR`` with a database message).
    """
    started_at = time.perf_counter()
    history, assistant_message_id = await _load_history_and_persist(turn_input)

    # --- Pre-turn hooks ---
    pre_turn_added_context: str | None = await _run_pre_turn_hooks(turn_input)
    if turn_input.on_pre_turn_finished:
        await turn_input.on_pre_turn_finished()

    # --- Main turn ---
    aggregator = ChatTurnAggregator()
    counter = _EventCounter()
    model_id = _channel_model_id(turn_input.channel_message)
    # Compose the per-turn system prompt: workspace identity files +
    # runtime metadata (current time, model/provider, iteration budget,
    # tool inventory) appended on every turn so the model never has to
    # guess at its environment.  See issues #289, #291, #294, #309 and
    # ``app.channels._turn_runtime_context`` for the rationale.
    system_prompt = system_prompt_for_turn(
        turn_input.workspace_root,
        model_id=model_id,
        tools=turn_input.tools,
        extra_context=pre_turn_added_context,
        reasoning_effort=turn_input.reasoning_effort,
    )

    with turn_span(
        conversation_id=turn_input.conversation_id,
        user_id=turn_input.user_id,
        surface=turn_input.log_tag,
        request_id=_request_id_from_extras(turn_input.log_extras),
        model_id=model_id,
    ) as turn_recorder:
        try:
            async for chunk in _stream_with_llm_span(
                turn_input=turn_input,
                history=history,
                system_prompt=system_prompt,
                aggregator=aggregator,
                counter=counter,
                event_hooks=event_hooks,
                model_id=model_id,
                turn_recorder=turn_recorder,
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
                ttft_ms=turn_recorder.ttft_ms,
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
    turn_recorder: TurnSpanRecorder,
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
        hooks = [
            workshop_event_hook(llm_recorder, turn_recorder=turn_recorder),
            *(event_hooks or []),
        ]
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
    # ``codex_thread_id`` is an openai_codex-specific extension kwarg
    # (multi-turn thread resume). Other providers' ``stream()`` signatures
    # don't accept it, so we only forward it when it's actually set —
    # which only happens for conversations bound to the openai_codex
    # provider. The Protocol stays clean.
    extra_kwargs: dict[str, Any] = {}
    if turn_input.codex_thread_id is not None:
        extra_kwargs["codex_thread_id"] = turn_input.codex_thread_id
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
            if not _should_deliver_event(event, turn_input.verbose_level):
                continue
            # Handle Codex native provider internal signals (e.g. new thread created
            # so we can persist the thread_id for resume on future turns).
            if event.get("type") == "internal" and event.get("kind") == "codex_thread_created":
                thread_id = event.get("thread_id")
                if isinstance(thread_id, str) and thread_id:
                    # Detached task so the UPDATE survives cancellation of
                    # the streaming response (SIGTERM mid-stream, client
                    # disconnect). We track a strong reference in
                    # ``_PENDING_CODEX_PERSIST_TASKS`` so the GC can't
                    # collect it and ``main.lifespan`` awaits the set on
                    # shutdown before the event loop exits.
                    persist_task = asyncio.create_task(
                        persist_codex_thread_id(turn_input.conversation_id, thread_id)
                    )
                    _register_codex_persist_task(persist_task)
                # Do not forward this internal event to the UI.
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


def _request_id_from_extras(extras: dict[str, Any]) -> str:
    """Pull the request id from ``log_extras`` (set by the chat router)."""
    raw = extras.get("request_id", "") if extras else ""
    return str(raw) if raw is not None else ""


def _channel_model_id(channel_message: ChannelMessage | None) -> str | None:
    """Return the ``model_id`` from the channel envelope, or ``None``."""
    if not channel_message:
        return None
    model_id = channel_message.get("model_id")
    return model_id


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
    ttft_ms: float | None,
) -> None:
    """Patch the assistant placeholder with the final aggregated stream state.

    The two writes (message finalize + cost ledger) are split across
    separate transactions so a cost-write failure can't leave the
    assistant row stuck at ``status="streaming"`` forever — which would
    surface to the user as a "thinking..." placeholder that never
    resolves. Message finalize is the hard requirement; the cost write
    is best-effort observability.
    """
    duration_ms = (time.perf_counter() - started_at) * _MS_PER_SECOND_FOR_LOG
    final_status = "failed" if aggregator.error_text else "complete"
    snapshot = aggregator.to_persisted_shape(status=final_status)
    try:
        async with _turn_session(turn_input) as session:
            await finalize_assistant_message(
                session,
                message_id=assistant_message_id,
                **snapshot,
            )
            await session.commit()
    except sa_exc.SQLAlchemyError:
        # Broad ``SQLAlchemyError`` (not bare ``Exception``) covers the full
        # set of SQLAlchemy failure modes that can reach this finalize path:
        # ``OperationalError``/``IntegrityError`` (the original narrow set)
        # plus ``PendingRollbackError`` / ``InvalidRequestError`` /
        # ``DataError`` raised when a prior statement inside the session
        # left the transaction in an unrecoverable state. Narrowing to just
        # the original two let those leak out of ``_finalize_turn`` (called
        # from ``run_turn``'s ``finally``) into the ``StreamingResponse``
        # generator after the body had already yielded, truncating the SSE
        # stream and stranding the assistant row at ``status="streaming"``.
        logger.exception(
            "%s_PERSIST_ERR conversation_id=%s message_id=%s",
            turn_input.log_tag,
            turn_input.conversation_id,
            assistant_message_id,
        )

    # Cost ledger write runs in its own transaction so a ledger-side
    # failure can't roll back the assistant-row finalize above. Runs for
    # every surface (web + Telegram) so the per-user cap applies uniformly.
    channel_message = turn_input.channel_message
    cost_model_id = (channel_message.get("model_id") or "") if channel_message else ""
    cost_surface = (channel_message.get("surface") or "") if channel_message else ""
    try:
        async with _turn_session(turn_input) as session:
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
    except sa_exc.SQLAlchemyError:
        # See the matching except above: narrow ``OperationalError`` /
        # ``IntegrityError`` skips ``PendingRollbackError`` and friends,
        # which would propagate into the streaming generator and break
        # the SSE response after the body has yielded.
        logger.exception(
            "%s_COST_PERSIST_ERR conversation_id=%s message_id=%s",
            turn_input.log_tag,
            turn_input.conversation_id,
            assistant_message_id,
        )

    extras = " ".join(f"{key}={value}" for key, value in turn_input.log_extras.items())
    breakdown = (
        " ".join(f"{name}={count}" for name, count in sorted(event_breakdown.items())) or "none"
    )
    ttft_field = f"{ttft_ms:.1f}" if ttft_ms is not None else _TTFT_LOG_MISSING
    logger.info(
        "%s_OUT conversation_id=%s events=%d duration_ms=%.1f ttft_ms=%s "
        "input_tokens=%d output_tokens=%d breakdown=[%s] %s",
        turn_input.log_tag,
        turn_input.conversation_id,
        event_count,
        duration_ms,
        ttft_field,
        aggregator.total_input_tokens,
        aggregator.total_output_tokens,
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
            ttft_ms=ttft_ms,
            input_tokens=aggregator.total_input_tokens,
            output_tokens=aggregator.total_output_tokens,
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
        model_id=model_id,
    )


async def persist_codex_thread_id(conversation_id: uuid.UUID, thread_id: str) -> None:
    """Persist a newly created Codex thread id against the conversation.

    Called inline from the streaming wrapper when the openai_codex
    provider emits a ``codex_thread_created`` internal signal. The call
    is awaited (not fire-and-forget) so a graceful shutdown can't cancel
    the write mid-flight and silently lose multi-turn Codex context.
    A single small UPDATE is fast enough that the per-event latency
    impact is negligible, and the signal is emitted at most once per
    conversation (when the Codex thread is first created).
    """
    try:
        async with async_session_maker() as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(codex_thread_id=thread_id)
            )
            await session.commit()
            logger.debug(
                "codex: persisted thread_id=%s for conversation=%s",
                thread_id,
                conversation_id,
            )
    except (sa_exc.OperationalError, sa_exc.IntegrityError):
        logger.exception("codex: failed to persist thread_id for conversation %s", conversation_id)


async def load_codex_thread_id(conversation_id: uuid.UUID) -> str | None:
    """Load the persisted Codex thread id for resume support (if any)."""
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Conversation.codex_thread_id).where(Conversation.id == conversation_id)
            )
            row = result.first()
            return row[0] if row else None
    except sa_exc.OperationalError:
        logger.exception("codex: failed to load thread_id for conversation %s", conversation_id)
        return None
