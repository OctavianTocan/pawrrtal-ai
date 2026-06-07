"""Runner for the provider-agnostic model/tool loop."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from app.agents.types import (
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
    MessageEndEvent,
    MessageStartEvent,
    StreamFn,
    ToolResultContent,
    ToolResultEvent,
    ToolResultMessage,
    TurnEndEvent,
    TurnStartEvent,
)

from .streaming import _stream_with_retry, _StreamOutcome, _terminated
from .tool_calls import _execute_and_log_tool_call

_log = logging.getLogger(__name__)


async def run_model_tool_loop(
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
        stream_outcome = _StreamOutcome(
            events=[],
            assistant_content=[],
            stop_reason="stop",
            consecutive_llm_errors_after=consecutive_llm_errors,
            terminated_event=None,
        )
        async for ev in _stream_with_retry(
            stream_fn=stream_fn,
            llm_messages=llm_messages,
            tools=tools,
            safety=safety,
            consecutive_llm_errors=consecutive_llm_errors,
            outcome=stream_outcome,
        ):
            yield ev

        if stream_outcome.terminated_event is not None:
            break

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


def _make_context_snapshot(
    messages: list[AgentMessage],
    tools: list[AgentTool],
) -> AgentContext:
    """Build an AgentContext snapshot for the should_stop_after_turn predicate."""
    return AgentContext(system_prompt="", messages=messages, tools=tools)
