"""
TDD tests for the Pi-inspired agent loop.

Test structure mirrors pi-mono/packages/agent/test/agent-loop.test.ts
(https://github.com/badlogic/pi-mono/blob/main/packages/agent/test/agent-loop.test.ts)

RED phase: all tests fail until loop.py and types.py are implemented.

.. note::

    **Legacy suite — prefer ``agent_harness`` for new tests.**

    These tests were written before ``ScriptedStreamFn`` existed and use the
    bespoke ``make_mock_stream`` helper, which operates on ``AssistantMessage``
    objects rather than ``LLMEvent`` sequences.  They are kept as-is for
    regression coverage.  Any *new* test of agent-loop behaviour, safety,
    tool dispatch, or context accumulation must use the shared primitives in
    ``backend/tests/agent_harness.py`` (see AGENTS.md §Agent-Loop Testing
    Philosophy).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.core.agent_loop.loop import agent_loop
from app.core.agent_loop.types import (
    AgentContext,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    AgentTool,
    AssistantMessage,
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    LLMToolCallEvent,
    TextContent,
    ToolCallContent,
    ToolResultContent,
    UserMessage,
)

# ---------------------------------------------------------------------------
# Helpers — mock primitives matching Pi's test helpers
# ---------------------------------------------------------------------------


def make_user_message(text: str) -> UserMessage:
    return UserMessage(role="user", content=text)


def make_assistant_message(
    content: list[TextContent | ToolCallContent],
    stop_reason: str = "stop",
) -> AssistantMessage:
    return AssistantMessage(role="assistant", content=content, stop_reason=stop_reason)


def make_text_content(text: str) -> TextContent:
    return TextContent(type="text", text=text)


def make_tool_call_content(
    tool_call_id: str, name: str, arguments: dict[str, Any]
) -> ToolCallContent:
    return ToolCallContent(
        type="toolCall", tool_call_id=tool_call_id, name=name, arguments=arguments
    )


def make_tool_result_content(text: str) -> ToolResultContent:
    return ToolResultContent(type="text", text=text)


def identity_converter(messages: list[AgentMessage]) -> list[AgentMessage]:
    """Pass through only roles the LLM understands (mirrors Pi's identityConverter)."""
    return [m for m in messages if m["role"] in {"user", "assistant", "toolResult"}]


def make_mock_stream(*responses: AssistantMessage):
    """Build a StreamFn that yields pre-scripted AssistantMessages in order."""
    call_count = 0

    async def stream_fn(
        messages: list[AgentMessage],
        tools: list[AgentTool],
    ) -> AsyncIterator[LLMEvent]:
        nonlocal call_count
        msg = responses[min(call_count, len(responses) - 1)]
        call_count += 1

        # Emit text deltas for any text content
        for block in msg["content"]:
            if block["type"] == "text":
                yield LLMTextDeltaEvent(type="text_delta", text=block["text"])
            elif block["type"] == "toolCall":
                yield LLMToolCallEvent(
                    type="tool_call",
                    tool_call_id=block["tool_call_id"],
                    name=block["name"],
                    arguments=block["arguments"],
                )

        yield LLMDoneEvent(
            type="done",
            stop_reason=msg["stop_reason"],
            content=msg["content"],
        )

    return stream_fn


# ---------------------------------------------------------------------------
# Test 1: basic turn, no tools (mirrors "should emit events with AgentMessage types")
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_agent_loop_emits_full_event_sequence_for_simple_turn() -> None:
    """A single user prompt with no tool calls emits the full lifecycle event sequence."""
    context = AgentContext(system_prompt="You are helpful.", messages=[], tools=[])
    prompt = make_user_message("Hello")
    config = AgentLoopConfig(convert_to_llm=identity_converter)
    stream_fn = make_mock_stream(make_assistant_message([make_text_content("Hi there!")]))

    events: list[AgentEvent] = []
    returned_messages: list[AgentMessage] = []

    async for event in agent_loop([prompt], context, config, stream_fn):
        events.append(event)
        if event["type"] == "agent_end":
            returned_messages = event["messages"]

    event_types = [e["type"] for e in events]

    assert "agent_start" in event_types
    assert "turn_start" in event_types
    assert "message_start" in event_types
    assert "message_end" in event_types
    assert "turn_end" in event_types
    assert "agent_end" in event_types

    # Prompt + assistant response
    assert len(returned_messages) == 2
    assert returned_messages[0]["role"] == "user"
    assert returned_messages[1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# Test 2: text deltas stream through during turn
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_agent_loop_streams_text_deltas() -> None:
    """Text delta events from the stream_fn are forwarded as agent events."""
    context = AgentContext(system_prompt="You are helpful.", messages=[], tools=[])
    prompt = make_user_message("Hi")
    config = AgentLoopConfig(convert_to_llm=identity_converter)
    stream_fn = make_mock_stream(make_assistant_message([make_text_content("Hello world")]))

    events: list[AgentEvent] = [
        event async for event in agent_loop([prompt], context, config, stream_fn)
    ]

    text_deltas = [e for e in events if e["type"] == "text_delta"]
    assert len(text_deltas) >= 1
    assert any("Hello world" in e.get("text", "") for e in text_deltas)


# ---------------------------------------------------------------------------
# Test 3: transformContext is applied before convert_to_llm
# (mirrors "should apply transformContext before convertToLlm")
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_agent_loop_applies_transform_context_before_convert() -> None:
    """transformContext prunes history before the LLM sees it."""
    old_messages: list[AgentMessage] = [
        make_user_message("old 1"),
        make_assistant_message([make_text_content("old reply 1")]),
        make_user_message("old 2"),
        make_assistant_message([make_text_content("old reply 2")]),
    ]
    context = AgentContext(system_prompt="You are helpful.", messages=old_messages, tools=[])
    prompt = make_user_message("new message")

    seen_by_llm: list[list[AgentMessage]] = []

    async def recording_stream_fn(
        messages: list[AgentMessage], tools: list[AgentTool]
    ) -> AsyncIterator[LLMEvent]:
        seen_by_llm.append(list(messages))
        msg = make_assistant_message([make_text_content("response")])
        yield LLMTextDeltaEvent(type="text_delta", text="response")
        yield LLMDoneEvent(type="done", stop_reason="stop", content=msg["content"])

    async def prune_to_last_two(messages: list[AgentMessage]) -> list[AgentMessage]:
        return messages[-2:]

    config = AgentLoopConfig(
        convert_to_llm=identity_converter,
        transform_context=prune_to_last_two,
    )

    async for _ in agent_loop([prompt], context, config, recording_stream_fn):
        pass

    # After pruning, LLM should only see the 2 most recent messages + the new prompt
    assert len(seen_by_llm) == 1
    # The pruned context (last 2) + new prompt = 3 messages max
    assert len(seen_by_llm[0]) <= 3


# ---------------------------------------------------------------------------
# Test 4: tool calls trigger execution and a second LLM turn
# (mirrors "should handle tool calls and results")
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_agent_loop_executes_tool_calls_and_loops() -> None:
    """When the assistant returns a tool call, the loop executes it and calls the LLM again."""
    executed: list[str] = []

    async def echo_execute(tool_call_id: str, **kwargs: Any) -> str:
        executed.append(kwargs["value"])
        return f"echoed: {kwargs['value']}"

    echo_tool = AgentTool(
        name="echo",
        description="Echoes a value",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        execute=echo_execute,
    )

    context = AgentContext(system_prompt="You are helpful.", messages=[], tools=[echo_tool])
    prompt = make_user_message("Echo hello")
    config = AgentLoopConfig(convert_to_llm=identity_converter)

    # First LLM call: request a tool call. Second: plain text response.
    stream_fn = make_mock_stream(
        make_assistant_message(
            [make_tool_call_content("call-1", "echo", {"value": "hello"})],
            stop_reason="tool_use",
        ),
        make_assistant_message([make_text_content("Done!")]),
    )

    events: list[AgentEvent] = []
    returned_messages: list[AgentMessage] = []

    async for event in agent_loop([prompt], context, config, stream_fn):
        events.append(event)
        if event["type"] == "agent_end":
            returned_messages = event["messages"]

    # Tool should have been called
    assert executed == ["hello"]

    event_types = [e["type"] for e in events]
    assert "tool_call_start" in event_types
    assert "tool_call_end" in event_types
    assert "tool_result" in event_types

    # Two full turns: one with tool call, one with final response
    turn_starts = [e for e in events if e["type"] == "turn_start"]
    assert len(turn_starts) == 2

    # Messages: user prompt, assistant (tool call), tool result, assistant (final)
    assert len(returned_messages) == 4
    assert returned_messages[2]["role"] == "toolResult"
    assert returned_messages[2]["name"] == "echo"


# ---------------------------------------------------------------------------
# Test 5: shouldStopAfterTurn stops the loop early
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_agent_loop_respects_should_stop_after_turn() -> None:
    """shouldStopAfterTurn returning True exits after the first turn."""
    context = AgentContext(system_prompt="You are helpful.", messages=[], tools=[])
    prompt = make_user_message("Hello")
    config = AgentLoopConfig(
        convert_to_llm=identity_converter,
        should_stop_after_turn=lambda ctx: True,  # always stop
    )
    stream_fn = make_mock_stream(
        make_assistant_message([make_text_content("Turn 1")]),
        make_assistant_message([make_text_content("Turn 2 — should not reach")]),
    )

    events: list[AgentEvent] = [
        event async for event in agent_loop([prompt], context, config, stream_fn)
    ]

    turn_starts = [e for e in events if e["type"] == "turn_start"]
    assert len(turn_starts) == 1  # stopped after first turn


# ---------------------------------------------------------------------------
# Test 6: existing messages in context are included in LLM call
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_agent_loop_includes_existing_context_messages() -> None:
    """Prior messages in context are passed to the LLM (multi-turn continuity)."""
    prior_messages: list[AgentMessage] = [
        make_user_message("What is 2+2?"),
        make_assistant_message([make_text_content("4")]),
    ]
    context = AgentContext(system_prompt="You are helpful.", messages=prior_messages, tools=[])
    prompt = make_user_message("And 3+3?")
    config = AgentLoopConfig(convert_to_llm=identity_converter)

    messages_seen_by_llm: list[list[AgentMessage]] = []

    async def recording_stream_fn(
        messages: list[AgentMessage], tools: list[AgentTool]
    ) -> AsyncIterator[LLMEvent]:
        messages_seen_by_llm.append(list(messages))
        msg = make_assistant_message([make_text_content("6")])
        yield LLMTextDeltaEvent(type="text_delta", text="6")
        yield LLMDoneEvent(type="done", stop_reason="stop", content=msg["content"])

    async for _ in agent_loop([prompt], context, config, recording_stream_fn):
        pass

    # LLM should have received: 2 prior messages + new prompt = 3 total
    assert len(messages_seen_by_llm[0]) == 3
