"""Per-turn safety helpers for the agent loop.

Extracted from :mod:`app.core.agent_loop.loop` so the iteration / wall-clock
checks, tool-result collection, and stop predicate live in one place that
the main loop can read at a glance.

All names beginning with an underscore are package-internal — call them
only from sibling modules inside :mod:`app.core.agent_loop` (see
``.claude/rules/clean-code/python-module-privacy.md``).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.core.agent_loop.tool_dispatch import _execute_and_log_tool_call
from app.core.agent_loop.types import (
    AgentContext,
    AgentLoopConfig,
    AgentMessage,
    AgentSafetyConfig,
    AgentTerminatedEvent,
    AgentTool,
    ToolResultContent,
    ToolResultEvent,
    ToolResultMessage,
)

_log = logging.getLogger(__name__)


def _check_iteration_safety(
    safety: AgentSafetyConfig,
    iteration: int,
    started_at: float,
) -> AgentTerminatedEvent | None:
    """Return a termination event if any pre-turn safety limit is hit, else None."""
    if safety.max_iterations is not None and iteration >= safety.max_iterations:
        return _terminated(
            reason="max_iterations",
            message=(
                f"Agent stopped: hit max_iterations cap of "
                f"{safety.max_iterations}.  This usually means the "
                "model got stuck in a tool-call loop.  Reply with "
                "new context or raise the cap if the work needs "
                "more steps."
            ),
            limit=safety.max_iterations,
            observed=iteration,
        )

    elapsed = time.monotonic() - started_at
    if safety.max_wall_clock_seconds is not None and elapsed >= safety.max_wall_clock_seconds:
        return _terminated(
            reason="max_wall_clock",
            message=(
                f"Agent stopped: hit wall-clock budget of "
                f"{safety.max_wall_clock_seconds:.0f}s.  Raise "
                "`max_wall_clock_seconds` for legitimately long "
                "turns."
            ),
            limit_seconds=safety.max_wall_clock_seconds,
            observed_seconds=round(elapsed, 2),
            iterations=iteration,
        )

    return None


async def _collect_tool_results(
    tool_calls: list[Any],
    tool_map: dict[str, AgentTool],
    messages: list[AgentMessage],
    new_messages: list[AgentMessage],
    safety: AgentSafetyConfig,
    consecutive_tool_errors: int,
    iteration: int,
    config: AgentLoopConfig,
) -> tuple[list[ToolResultEvent], list[ToolResultMessage], int, AgentTerminatedEvent | None]:
    """Execute all tool calls for one turn and collect result events.

    Returns ``(result_events, tool_results, consecutive_tool_errors, terminated_event)``.
    ``terminated_event`` is non-None only when the consecutive-error budget is hit.
    Messages are appended to both ``messages`` and ``new_messages`` in-place.
    """
    result_events: list[ToolResultEvent] = []
    tool_results: list[ToolResultMessage] = []
    terminated: AgentTerminatedEvent | None = None

    for tc in tool_calls:
        if tc["type"] != "toolCall":
            continue
        result_text, is_error = await _execute_and_log_tool_call(
            tc=tc,
            tool_map=tool_map,
            iteration=iteration,
            config=config,
        )
        result_events.append(
            ToolResultEvent(
                type="tool_result",
                tool_call_id=tc["tool_call_id"],
                content=result_text,
                is_error=is_error,
            )
        )
        tool_result_msg = ToolResultMessage(
            role="toolResult",
            tool_call_id=tc["tool_call_id"],
            name=tc["name"],
            content=[ToolResultContent(type="text", text=result_text)],
            is_error=is_error,
        )
        tool_results.append(tool_result_msg)
        messages.append(tool_result_msg)
        new_messages.append(tool_result_msg)

        if is_error:
            consecutive_tool_errors += 1
            if (
                safety.max_consecutive_tool_errors is not None
                and consecutive_tool_errors >= safety.max_consecutive_tool_errors
            ):
                terminated = _terminated(
                    reason="consecutive_tool_errors",
                    message=(
                        "Agent stopped: "
                        f"{consecutive_tool_errors} tool calls "
                        "failed back-to-back.  The model is "
                        "likely retrying a broken tool with the "
                        "same arguments.  Inspect the last tool "
                        "errors and either fix the inputs or "
                        "raise `max_consecutive_tool_errors`."
                    ),
                    limit=safety.max_consecutive_tool_errors,
                    observed=consecutive_tool_errors,
                    iterations=iteration,
                )
                break
        else:
            consecutive_tool_errors = 0

    return result_events, tool_results, consecutive_tool_errors, terminated


def _should_stop(
    stop_reason: str,
    tool_calls: list[Any],
    config: AgentLoopConfig,
    messages: list[AgentMessage],
    tools: list[AgentTool],
) -> bool:
    """Return True if the loop should halt after this turn."""
    if stop_reason in {"error", "aborted"}:
        return True
    if config.should_stop_after_turn is not None:
        fake_ctx = _make_context_snapshot(messages, tools)
        if config.should_stop_after_turn(fake_ctx):
            return True
    return not tool_calls


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


def _make_context_snapshot(
    messages: list[AgentMessage],
    tools: list[AgentTool],
) -> AgentContext:
    """Build an AgentContext snapshot for the should_stop_after_turn predicate."""
    return AgentContext(system_prompt="", messages=messages, tools=tools)
