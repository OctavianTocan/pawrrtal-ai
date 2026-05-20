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

This module is the entry point. Per-concern helpers live in sibling
modules within the :mod:`app.core.agent_loop` package:

* :mod:`app.core.agent_loop.tool_dispatch` — permission gate + tool
  invocation + per-call observability.
* :mod:`app.core.agent_loop.safety` — pre-turn iteration / wall-clock
  checks, tool-result collection, and the after-turn stop predicate.
* :mod:`app.core.agent_loop.events` — translation of one provider
  ``LLMEvent`` into one or more ``AgentEvent`` items + per-turn context
  preparation.
* :mod:`app.core.agent_loop.stream_retry` — provider stream retry budget
  and partial-output handling.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator

from app.core.agent_loop.events import _prepare_llm_messages
from app.core.agent_loop.safety import (
    _check_iteration_safety,
    _collect_tool_results,
    _should_stop,
)
from app.core.agent_loop.stream_retry import _stream_with_retry, _StreamOutcome

from .types import (
    AgentContext,
    AgentEndEvent,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    AgentStartEvent,
    AgentTool,
    AssistantMessage,
    MessageEndEvent,
    MessageStartEvent,
    StreamFn,
    TurnEndEvent,
    TurnStartEvent,
)

_log = logging.getLogger(__name__)


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
