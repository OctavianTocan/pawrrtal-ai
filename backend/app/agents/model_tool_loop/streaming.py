"""Provider stream retry and LLM-event translation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.agents.display import render_display_from_map, tool_display_map
from app.agents.types import (
    AgentEvent,
    AgentMessage,
    AgentSafetyConfig,
    AgentTerminatedEvent,
    AgentTool,
    LLMEvent,
    StreamFn,
    TextContent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallContent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stream-with-retry helper
# ---------------------------------------------------------------------------


class _StreamOutcome:
    """Result of one (possibly retried) stream attempt.

    Either the stream succeeded — in which case ``events`` holds the
    AgentEvents we want the caller to yield in order, ``assistant_content``
    + ``stop_reason`` carry the final assistant message, and
    ``terminated_event`` is ``None`` — or every retry was exhausted, in
    which case ``terminated_event`` carries the safety termination notice
    and the other fields are empty defaults.
    """

    __slots__ = (
        "assistant_content",
        "consecutive_llm_errors_after",
        "events",
        "provider_state",
        "stop_reason",
        "terminated_event",
    )

    def __init__(
        self,
        events: list[AgentEvent],
        assistant_content: list[TextContent | ToolCallContent],
        stop_reason: str,
        consecutive_llm_errors_after: int,
        terminated_event: AgentTerminatedEvent | None,
        provider_state: dict[str, Any] | None = None,
    ) -> None:
        self.events = events
        self.assistant_content = assistant_content
        self.stop_reason = stop_reason
        self.consecutive_llm_errors_after = consecutive_llm_errors_after
        self.terminated_event = terminated_event
        self.provider_state = provider_state


class _StreamAttemptState:
    """Mutable state for one provider stream attempt."""

    __slots__ = ("emitted_event", "provider_state")

    def __init__(self) -> None:
        self.emitted_event = False
        self.provider_state: dict[str, Any] | None = None


async def _stream_with_retry(
    stream_fn: StreamFn,
    llm_messages: list[AgentMessage],
    tools: list[AgentTool],
    safety: AgentSafetyConfig,
    consecutive_llm_errors: int,
    outcome: _StreamOutcome,
) -> AsyncIterator[AgentEvent]:
    """Stream one assistant turn, updating ``outcome`` with final state."""
    backoff = max(safety.llm_retry_backoff_seconds, 0.0)
    max_errors = safety.max_consecutive_llm_errors
    attempts = 0
    display_by_name = tool_display_map(tools)

    while True:
        attempts += 1
        attempt_state = _StreamAttemptState()

        try:
            async for event in _stream_attempt_events(
                stream_fn(llm_messages, tools),
                outcome,
                attempt_state,
                display_by_name,
            ):
                yield event
        except Exception as exc:
            if attempt_state.emitted_event:
                outcome.terminated_event = _stream_interrupted_after_events(exc)
                yield outcome.terminated_event
                return

            consecutive_llm_errors += 1
            _log.warning(
                "run_model_tool_loop: provider stream failed (attempt %d, consecutive=%d/%s): %s",
                attempts,
                consecutive_llm_errors,
                max_errors if max_errors is not None else "∞",
                exc,
            )
            exhausted = _retry_budget_exhausted(
                max_errors=max_errors,
                consecutive_llm_errors=consecutive_llm_errors,
                exc=exc,
            )
            if exhausted is not None:
                _copy_stream_outcome(exhausted, outcome)
                assert outcome.terminated_event is not None
                yield outcome.terminated_event
                return

            await _sleep_before_retry(backoff, attempts)
            continue

        outcome.consecutive_llm_errors_after = 0
        outcome.provider_state = attempt_state.provider_state
        return


async def _sleep_before_retry(backoff: float, attempts: int) -> None:
    """Sleep for exponential retry backoff when configured."""
    if backoff <= 0:
        return
    wait = min(backoff * (2 ** (attempts - 1)), 30.0)
    await asyncio.sleep(wait)


async def _stream_attempt_events(
    stream: AsyncIterator[LLMEvent],
    outcome: _StreamOutcome,
    attempt_state: _StreamAttemptState,
    display_by_name: dict[str, Any],
) -> AsyncIterator[AgentEvent]:
    """Yield translated events for one provider stream attempt."""
    async for llm_event in stream:
        events: list[AgentEvent] = []
        done = _consume_llm_event(llm_event, events, display_by_name)
        if events:
            attempt_state.emitted_event = True
            outcome.events.extend(events)
        _apply_done_event(done, outcome, attempt_state)
        for event in events:
            yield event


def _apply_done_event(
    done: dict[str, Any] | None,
    outcome: _StreamOutcome,
    attempt_state: _StreamAttemptState,
) -> None:
    """Capture the final provider state from a terminal ``done`` event."""
    if done is None:
        return
    outcome.assistant_content = done["content"]
    outcome.stop_reason = done["stop_reason"]
    attempt_state.provider_state = _carry_provider_state(done, attempt_state.provider_state)


def _retry_budget_exhausted(
    *,
    max_errors: int | None,
    consecutive_llm_errors: int,
    exc: Exception,
) -> _StreamOutcome | None:
    """Return a terminating :class:`_StreamOutcome` if retry budget exhausted.

    Pulled out of :func:`_stream_with_retry` so the inner loop stays
    within the project's nesting-depth budget (depth 3) — enforced by
    ``scripts/check-nesting.py``.  Returns ``None`` when the budget
    still has room and the caller should retry.
    """
    if max_errors is None or consecutive_llm_errors < max_errors:
        return None
    terminated = _terminated(
        reason="consecutive_llm_errors",
        message=(
            "Agent stopped: "
            f"{consecutive_llm_errors} provider errors in a "
            "row.  The upstream model is likely down or "
            "rate-limiting.  Try again, switch model, or "
            "raise `max_consecutive_llm_errors`.  Last "
            f"error: {exc}"
        ),
        limit=max_errors,
        observed=consecutive_llm_errors,
        last_error=str(exc),
    )
    return _StreamOutcome(
        events=[],
        assistant_content=[],
        stop_reason="error",
        consecutive_llm_errors_after=consecutive_llm_errors,
        terminated_event=terminated,
    )


def _copy_stream_outcome(source: _StreamOutcome, target: _StreamOutcome) -> None:
    """Copy final stream state into the caller-owned outcome object."""
    target.events = source.events
    target.assistant_content = source.assistant_content
    target.stop_reason = source.stop_reason
    target.consecutive_llm_errors_after = source.consecutive_llm_errors_after
    target.terminated_event = source.terminated_event
    target.provider_state = source.provider_state


def _stream_interrupted_after_events(exc: Exception) -> AgentTerminatedEvent:
    """Build the no-retry termination used after partial output was emitted."""
    return _terminated(
        reason="stream_interrupted_after_events",
        message=(
            "Agent stopped: provider stream failed after partial output was "
            f"already emitted. Last error: {exc}"
        ),
        last_error=str(exc),
    )


def _consume_llm_event(
    llm_event: LLMEvent,
    events: list[AgentEvent],
    display_by_name: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Translate one LLMEvent into AgentEvents and append to ``events``.

    Returns the payload for the terminal ``done`` event
    (``{content, stop_reason}``) when the consumed event was that
    terminator; otherwise ``None``.  Returning instead of using a
    mutable out-param keeps the caller's loop body flat enough to fit
    inside the project nesting-depth budget.
    """
    if llm_event["type"] == "text_delta":
        events.append(TextDeltaEvent(type="text_delta", text=llm_event["text"]))
        return None
    if llm_event["type"] == "thinking_delta":
        thinking_event = ThinkingDeltaEvent(type="thinking_delta", text=llm_event["text"])
        # Forward ``block_index`` when the provider supplied one (#353).
        # Older provider stream functions omit the field; downstream
        # renderers treat absence as "same block as previous".
        block_index = llm_event.get("block_index")
        if block_index is not None:
            thinking_event["block_index"] = block_index
        events.append(thinking_event)
        return None
    if llm_event["type"] == "tool_call":
        display = render_display_from_map(
            display_by_name or {},
            llm_event["name"],
            llm_event["arguments"],
        )
        events.append(
            ToolCallStartEvent(
                type="tool_call_start",
                tool_call_id=llm_event["tool_call_id"],
                name=llm_event["name"],
            )
        )
        events.append(
            ToolCallEndEvent(
                type="tool_call_end",
                tool_call_id=llm_event["tool_call_id"],
                name=llm_event["name"],
                arguments=llm_event["arguments"],
                display=display,
            )
        )
        return None
    if llm_event["type"] == "done":
        result: dict[str, Any] = {
            "content": llm_event["content"],
            "stop_reason": llm_event["stop_reason"],
        }
        # Forward opaque provider replay state if the StreamFn populated
        # it.  ``provider_state`` is a ``total=False`` field on
        # ``LLMDoneEvent`` so we read it with ``.get`` and only copy it
        # forward when the provider actually returned one.  See
        # ``_stream_with_retry`` for the per-turn capture.
        provider_state = llm_event.get("provider_state")
        if provider_state is not None:
            result["provider_state"] = provider_state
        return result
    return None


def _carry_provider_state(
    done: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the provider_state from ``done`` if present, else keep ``current``.

    Extracted out of :func:`_stream_with_retry` so the streaming loop's
    body stays under the project nesting-depth budget.  The loop never
    inspects the contents — providers own the keyspace; we just forward
    the slot.
    """
    if done is not None and "provider_state" in done:
        state = done["provider_state"]
        # ``done`` is a TypedDict-shaped dict — narrow the dynamic value
        # back to the declared return type so mypy doesn't infer ``Any``.
        return state if isinstance(state, dict) else None
    return current


def _terminated(
    *,
    reason: str,
    message: str,
    **details: Any,
) -> AgentTerminatedEvent:
    """Build an :class:`AgentTerminatedEvent` with structured details.

    Centralised so every termination path uses the same dict shape.
    """
    return AgentTerminatedEvent(
        type="agent_terminated",
        reason=reason,  # type: ignore[typeddict-item]
        details=details,
        message=message,
    )
