"""Pi-inspired provider-agnostic agent loop.

Architecture mirrors @mariozechner/pi-agent-core from pi-mono:
  https://github.com/badlogic/pi-mono/blob/main/packages/agent/src/agent-loop.ts

The loop owns:
  - Turn lifecycle (agent_start → turn_start → ... → turn_end → agent_end)
  - Tool call execution (sequential, with before/after hooks TBD)
  - Context transform before each LLM call
  - shouldStopAfterTurn early exit
  - Safety layer: max_iterations, max_wall_clock, retry-with-backoff,
    consecutive-error termination.  See :class:`AgentSafetyConfig`.

Each provider supplies a StreamFn — the only provider-specific code.
The loop never imports any provider SDK directly.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from app.core.observability.workshop import tool_span

from .types import (
    AgentContext,
    AgentEndEvent,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    AgentSafetyConfig,
    AgentStartEvent,
    AgentTerminatedEvent,
    AgentTool,
    AssistantMessage,
    LLMEvent,
    MessageEndEvent,
    MessageStartEvent,
    StreamFn,
    TextContent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallContent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultContent,
    ToolResultEvent,
    ToolResultMessage,
    TurnEndEvent,
    TurnStartEvent,
)

_log = logging.getLogger(__name__)

# Truncation budgets for tool-call trace logs. We log enough to identify a
# stuck loop ("model keeps calling tool X with args Y") without flooding the
# log with full tool payloads. Full bodies stay at DEBUG.
_LOG_ARGS_MAX_CHARS = 500
_LOG_RESULT_MAX_CHARS = 500


def _truncate_for_log(value: Any, max_chars: int) -> str:
    """Render a tool argument or result for logs, truncating long payloads.

    Args:
        value: The object to render. Dicts are rendered as ``repr`` so keys
            stay readable; strings pass through untouched.
        max_chars: Maximum number of characters in the returned string. The
            truncation marker counts toward the limit so the returned string
            is always at most ``max_chars`` characters long.

    Returns:
        A single-line, length-bounded representation suitable for an INFO
        log line. Newlines are collapsed so each trace stays on one line.
    """
    text = value if isinstance(value, str) else repr(value)
    text = text.replace("\n", " ").replace("\r", " ")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


async def _execute_and_log_tool_call(
    *,
    tc: Any,
    tool_map: dict[str, AgentTool],
    iteration: int,
    config: AgentLoopConfig,
) -> tuple[str, bool]:
    """Execute one tool call, emit ``TOOL_CALL_*`` traces, and return the result.

    Pulled out of the main loop so the per-call observability (args preview,
    duration, result length) lives in one place and the outer loop stays
    inside the team's branch/statement budget.

    Args:
        tc: The ``toolCall`` content block from the assistant message.
        tool_map: ``name → AgentTool`` lookup built once per loop iteration.
        iteration: 1-based loop iteration, included in the trace lines so
            stuck loops are easy to bucket by turn in the log.
        config: Loop config carrying the optional permission gate; checked
            before ``tool.execute`` so denied calls become surfaced errors
            instead of side-effecting executions.

    Returns:
        A ``(result_text, is_error)`` tuple. ``result_text`` is always
        non-empty so the caller can hand it straight to ``ToolResultEvent``
        and ``ToolResultMessage`` without further branching.
    """
    name: str = tc["name"]
    call_id: str = tc["tool_call_id"]
    arguments: dict[str, Any] = tc["arguments"]
    args_preview = _truncate_for_log(arguments, _LOG_ARGS_MAX_CHARS)
    _log.info(
        "TOOL_CALL_START iteration=%d name=%s tool_call_id=%s args=%s",
        iteration,
        name,
        call_id,
        args_preview,
    )

    # Workshop / OTel tool span — gives the live trace viewer a row
    # per call with the args + result + duration, scoped under the
    # surrounding ``pawrrtal.turn`` span.  No-op when telemetry off.
    with tool_span(name=name, tool_call_id=call_id, arguments=arguments) as ts:
        started_at = time.monotonic()
        result_text, is_error = await _dispatch_tool_call(
            tool_map=tool_map,
            name=name,
            call_id=call_id,
            arguments=arguments,
            config=config,
        )
        duration_ms = (time.monotonic() - started_at) * 1000.0
        ts.record_result(result_text, is_error=is_error)

    _log.info(
        "TOOL_CALL_RESULT iteration=%d name=%s tool_call_id=%s "
        "is_error=%s duration_ms=%.1f result_len=%d",
        iteration,
        name,
        call_id,
        is_error,
        duration_ms,
        len(result_text),
    )
    _log.debug(
        "TOOL_CALL_RESULT_BODY tool_call_id=%s body=%s",
        call_id,
        _truncate_for_log(result_text, _LOG_RESULT_MAX_CHARS),
    )
    return result_text, is_error


async def _dispatch_tool_call(
    *,
    tool_map: dict[str, AgentTool],
    name: str,
    call_id: str,
    arguments: dict[str, Any],
    config: AgentLoopConfig,
) -> tuple[str, bool]:
    """Resolve permission + execute one tool call, returning ``(result_text, is_error)``.

    Pulled out of :func:`_execute_and_log_tool_call` so the surrounding
    ``tool_span`` context-manager + log lines keep their own scope and
    the dispatcher stays inside the team's nesting budget.

    Args:
        tool_map: ``name → AgentTool`` lookup built once per loop iteration.
        name: Tool name from the assistant's ``toolCall`` block.
        call_id: Provider-stable id so a permission gate can echo it.
        arguments: Kwargs the model produced for the tool.
        config: Loop config carrying the optional permission gate.

    Returns:
        ``(result_text, is_error)`` where ``result_text`` is always
        non-empty.
    """
    tool = tool_map.get(name)
    if tool is None:
        return f"Tool '{name}' not found.", True
    permission_denial = await _check_permission_or_none(
        config=config,
        tool_name=name,
        arguments=arguments,
    )
    if permission_denial is not None:
        return permission_denial, True
    try:
        return await tool.execute(call_id, **arguments), False
    except Exception as exc:
        return f"Tool error: {exc}", True


async def agent_loop(
    prompts: list[AgentMessage],
    context: AgentContext,
    config: AgentLoopConfig,
    stream_fn: StreamFn,
) -> AsyncIterator[AgentEvent]:
    """Run the agent loop and yield AgentEvents.

    See module docstring for the safety guarantees.  Configuration is
    via ``config.safety`` (an :class:`AgentSafetyConfig`).
    """
    new_messages: list[AgentMessage] = list(prompts)
    current_messages = list(context.messages) + list(prompts)

    yield AgentStartEvent(type="agent_start")
    yield TurnStartEvent(type="turn_start")

    for prompt in prompts:
        yield MessageStartEvent(type="message_start", message=prompt)
        yield MessageEndEvent(type="message_end", message=prompt)

    async for event in _run_loop(current_messages, context.tools, new_messages, config, stream_fn):
        yield event


async def _run_loop(
    messages: list[AgentMessage],
    tools: list[AgentTool],
    new_messages: list[AgentMessage],
    config: AgentLoopConfig,
    stream_fn: StreamFn,
) -> AsyncIterator[AgentEvent]:
    """Inner loop with the safety layer wired in.

    The pre-turn safety checks fire *before* incrementing the iteration
    counter so a freshly-started loop with ``max_iterations=0`` would
    bail immediately rather than running one turn (consistent with the
    intuitive reading of "max").  Wall-clock is sampled at the same
    pre-turn point so we never start a brand-new turn that we can't
    afford to finish.
    """
    safety = config.safety
    iteration = 0
    started_at = time.monotonic()
    consecutive_llm_errors = 0
    consecutive_tool_errors = 0
    first_turn = True

    while True:
        safety_terminated = _check_iteration_safety(safety, iteration, started_at)
        if safety_terminated is not None:
            yield safety_terminated
            break

        if not first_turn:
            yield TurnStartEvent(type="turn_start")
        first_turn = False
        iteration += 1

        llm_messages = await _prepare_llm_messages(messages, config)
        stream_outcome = await _stream_with_retry(
            stream_fn=stream_fn,
            llm_messages=llm_messages,
            tools=tools,
            safety=safety,
            consecutive_llm_errors=consecutive_llm_errors,
        )

        if stream_outcome.terminated_event is not None:
            yield stream_outcome.terminated_event
            break

        for ev in stream_outcome.events:
            yield ev

        consecutive_llm_errors = stream_outcome.consecutive_llm_errors_after
        assistant_msg = AssistantMessage(
            role="assistant",
            content=stream_outcome.assistant_content,
            stop_reason=stream_outcome.stop_reason,
        )
        # Forward opaque provider replay state so the next provider call
        # can replay native model content (e.g. Gemini ``thought_signature``)
        # while the loop remains generic.  The slot is optional and the
        # loop never inspects its contents.
        if stream_outcome.provider_state is not None:
            assistant_msg["provider_state"] = stream_outcome.provider_state
        messages.append(assistant_msg)
        new_messages.append(assistant_msg)

        tool_calls = [b for b in stream_outcome.assistant_content if b["type"] == "toolCall"]
        result_events, tool_results, consecutive_tool_errors, tool_safety_terminated = (
            await _collect_tool_results(
                tool_calls,
                {t.name: t for t in tools},
                messages,
                new_messages,
                safety,
                consecutive_tool_errors,
                iteration,
                config,
            )
            if tool_calls
            else ([], [], consecutive_tool_errors, None)
        )

        for ev in result_events:
            yield ev

        _log.info(
            "LOOP_ITERATION iteration=%d stop_reason=%s tool_calls=%d",
            iteration,
            stream_outcome.stop_reason,
            len(tool_calls),
        )
        yield TurnEndEvent(type="turn_end", message=assistant_msg, tool_results=tool_results)

        if tool_safety_terminated is not None:
            yield tool_safety_terminated
            break

        if _should_stop(stream_outcome.stop_reason, tool_calls, config, messages, tools):
            break

    yield AgentEndEvent(type="agent_end", messages=new_messages)


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


async def _prepare_llm_messages(
    messages: list[AgentMessage],
    config: AgentLoopConfig,
) -> list[AgentMessage]:
    """Apply context transform (if any) and convert to LLM format."""
    transformed = messages
    if config.transform_context is not None:
        transformed = await config.transform_context(list(messages))
    return config.convert_to_llm(transformed)


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


async def _stream_with_retry(
    stream_fn: StreamFn,
    llm_messages: list[AgentMessage],
    tools: list[AgentTool],
    safety: AgentSafetyConfig,
    consecutive_llm_errors: int,
) -> _StreamOutcome:
    """Stream one assistant turn, retrying transient provider errors.

    The retry budget is ``safety.max_consecutive_llm_errors`` — the
    cumulative count of failures since the last successful stream, not
    per-call.  This avoids the bug where two transient failures in two
    different turns silently consume the same budget.

    On success we reset the counter to 0.  On exhaustion we return a
    :class:`_StreamOutcome` carrying the terminal event so the caller
    can yield it cleanly.
    """
    backoff = max(safety.llm_retry_backoff_seconds, 0.0)
    max_errors = safety.max_consecutive_llm_errors
    attempts = 0

    while True:
        attempts += 1
        events: list[AgentEvent] = []
        assistant_content: list[TextContent | ToolCallContent] = []
        stop_reason = "stop"
        provider_state: dict[str, Any] | None = None

        try:
            async for llm_event in stream_fn(llm_messages, tools):
                done = _consume_llm_event(llm_event, events)
                # `done` is non-None only on the terminal ``done`` event;
                # we keep iterating in case the SDK emits trailers, but
                # the assignments here capture the final state.
                assistant_content = done["content"] if done else assistant_content
                stop_reason = done["stop_reason"] if done else stop_reason
                provider_state = _carry_provider_state(done, provider_state)
        except Exception as exc:
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
                return exhausted

            if backoff > 0:
                wait = min(backoff * (2 ** (attempts - 1)), 30.0)
                await asyncio.sleep(wait)
            continue

        return _StreamOutcome(
            events=events,
            assistant_content=assistant_content,
            stop_reason=stop_reason,
            consecutive_llm_errors_after=0,
            terminated_event=None,
            provider_state=provider_state,
        )


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


def _consume_llm_event(
    llm_event: LLMEvent,
    events: list[AgentEvent],
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
        events.append(ThinkingDeltaEvent(type="thinking_delta", text=llm_event["text"]))
        return None
    if llm_event["type"] == "tool_call":
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
        return done["provider_state"]
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
    return AgentTerminatedEvent(  # type: ignore[typeddict-item]
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


async def _check_permission_or_none(
    *,
    config: AgentLoopConfig,
    tool_name: str,
    arguments: dict[str, Any],
) -> str | None:
    """Run the configured permission gate, returning a denial message.

    Returns ``None`` when there's no gate or when the gate allows the
    call. Otherwise returns the denial reason as a string so the
    caller can surface it as the tool result. Also fires the optional
    ``permission_audit_sink`` (errors swallowed — audit failures must
    never break a turn).

    Kept as a module-level helper so the inner loop body in
    :func:`_run_loop` stays under the project's nesting budget.
    """
    if config.permission_check is None:
        return None
    try:
        decision = await config.permission_check(tool_name, arguments)
    except Exception as exc:
        # A crashed permission check is a configuration bug, not a
        # security signal — fail closed (deny) so a broken policy
        # doesn't silently allow tool use, but include the error so
        # the operator notices in logs.
        _log.exception("agent_loop: permission_check crashed; failing closed for %s", tool_name)
        return f"Tool '{tool_name}' denied: permission check error ({exc})."

    if decision.get("allow", False):
        return None

    reason = decision.get("reason") or "Tool call denied by permission policy."
    if config.permission_audit_sink is not None:
        try:
            await config.permission_audit_sink(tool_name, arguments, decision)
        except Exception:
            # Swallow audit failures — never break a turn over them.
            _log.exception("agent_loop: permission_audit_sink raised; ignoring")
    return reason
