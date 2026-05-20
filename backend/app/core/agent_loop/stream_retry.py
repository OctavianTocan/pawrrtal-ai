"""Stream-with-retry helper for the agent loop.

Extracted from :mod:`app.core.agent_loop.loop` so the provider-stream
retry budget, partial-output detection, and per-attempt event translation
live in one place that the main loop can read at a glance.

The retry budget is intentionally exponential and capped — the upstream
provider is the slow / unreliable surface and we don't want to hammer a
rate-limited model with no spacing.

All names beginning with an underscore are package-internal — call them
only from sibling modules inside :mod:`app.core.agent_loop` (see
``.claude/rules/clean-code/python-module-privacy.md``).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.core.agent_loop.display import ToolDisplay, tool_display_map
from app.core.agent_loop.events import _carry_provider_state, _consume_llm_event
from app.core.agent_loop.types import (
    AgentEvent,
    AgentMessage,
    AgentSafetyConfig,
    AgentTerminatedEvent,
    AgentTool,
    LLMEvent,
    StreamFn,
    TextContent,
    ToolCallContent,
)

_log = logging.getLogger(__name__)

# Retry-backoff cap: exponential growth is fine until it overshoots a
# reasonable per-attempt sleep ceiling, at which point we clamp so a long
# tail of provider errors doesn't park the loop indefinitely.
_RETRY_BACKOFF_CAP_SECONDS = 30.0


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
                "agent_loop: provider stream failed (attempt %d, consecutive=%d/%s): %s",
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
    wait = min(backoff * (2 ** (attempts - 1)), _RETRY_BACKOFF_CAP_SECONDS)
    await asyncio.sleep(wait)


async def _stream_attempt_events(
    stream: AsyncIterator[LLMEvent],
    outcome: _StreamOutcome,
    attempt_state: _StreamAttemptState,
    display_by_name: dict[str, ToolDisplay],
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


def _terminated(
    *,
    reason: str,
    message: str,
    **details: Any,
) -> AgentTerminatedEvent:
    """Build an :class:`AgentTerminatedEvent` with structured details.

    Module-local copy of the same helper in :mod:`app.core.agent_loop.safety`.
    Duplicated — rather than imported — to honour the Python module-privacy
    convention (``.claude/rules/clean-code/python-module-privacy.md``):
    private names with a leading underscore should not be imported across
    modules, even within the same package. Keep the two copies in sync.
    """
    return AgentTerminatedEvent(
        type="agent_terminated",
        reason=reason,  # type: ignore[typeddict-item]
        details=details,
        message=message,
    )
