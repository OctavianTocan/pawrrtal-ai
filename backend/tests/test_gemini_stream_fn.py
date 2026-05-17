"""Tests for GeminiLLM's StreamFn wiring into agent_loop.

Uses ``ScriptedStreamFn`` from ``tests.agent_harness`` — no real Gemini
API calls are made.  These tests exercise the provider's translation layer
(AgentEvent → StreamEvent) and confirm that safety config flows end-to-end
from ``safety_from_settings`` through ``agent_loop`` to the SSE output.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from app.core.agent_loop.types import (
    AgentMessage,
    AgentTool,
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    LLMToolCallEvent,
    TextContent,
    ToolCallContent,
)
from app.core.providers.base import StreamEvent
from tests.agent_harness import (
    ScriptedStreamFn,
    echo_tool,
    text_turn,
    thinking_then_text_turn,
    tool_call_turn,
)

# ---------------------------------------------------------------------------
# Test 1 — delta events pass through the provider translation layer
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gemini_provider_yields_delta_events_from_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GeminiLLM.stream() translates agent_loop text_deltas to StreamEvent deltas."""
    from app.core.providers.gemini_provider import GeminiLLM

    provider = GeminiLLM("gemini-test")
    monkeypatch.setattr(provider, "_stream_fn", ScriptedStreamFn([text_turn("hello")]))

    events: list[StreamEvent] = [
        event
        async for event in provider.stream(
            question="Hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
        )
    ]

    delta_events = [e for e in events if e["type"] == "delta"]
    assert len(delta_events) >= 1
    assert any("hello" in e.get("content", "") for e in delta_events)


# ---------------------------------------------------------------------------
# Test 2 — history is included in the message list seen by the StreamFn
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gemini_provider_passes_history_to_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prior messages in history are included in what the StreamFn sees."""
    from app.core.providers.gemini_provider import GeminiLLM

    seen_messages: list[list[AgentMessage]] = []

    async def recording_stream_fn(
        messages: list[AgentMessage], tools: list[AgentTool]
    ) -> AsyncIterator[LLMEvent]:
        seen_messages.append(list(messages))
        yield LLMTextDeltaEvent(type="text_delta", text="ok")
        yield LLMDoneEvent(
            type="done",
            stop_reason="stop",
            content=[TextContent(type="text", text="ok")],
        )

    provider = GeminiLLM("gemini-test")
    monkeypatch.setattr(provider, "_stream_fn", recording_stream_fn)

    history = [
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "4"},
    ]

    async for _ in provider.stream(
        question="And 3+3?",
        conversation_id=uuid4(),
        user_id=uuid4(),
        history=history,
    ):
        pass

    # 2 history messages + current question = 3 total.
    assert len(seen_messages) == 1
    assert len(seen_messages[0]) == 3


# ---------------------------------------------------------------------------
# Test 3 — tool call lifecycle events translate correctly to StreamEvents
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gemini_provider_emits_tool_use_and_result_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool call lifecycle events translate from AgentEvents to StreamEvents.

    Uses the real GeminiLLM.stream() with a ScriptedStreamFn so we exercise
    the provider's own translation code, not a hand-rolled reimplementation.
    """
    from app.core.providers.gemini_provider import GeminiLLM

    executed: list[str] = []

    async def echo_execute(tool_call_id: str, **kwargs: object) -> str:
        executed.append(str(kwargs.get("value", "")))
        return f"echoed: {kwargs.get('value', '')}"

    from app.core.agent_loop.types import AgentTool

    echo = AgentTool(
        name="echo",
        description="Echo",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        execute=echo_execute,
    )

    provider = GeminiLLM("gemini-test")
    monkeypatch.setattr(
        provider,
        "_stream_fn",
        ScriptedStreamFn(
            [
                tool_call_turn("echo", {"value": "hi"}, turn_id="tc-0"),
                text_turn("Done!"),
            ]
        ),
    )

    events: list[StreamEvent] = [
        event
        async for event in provider.stream(
            question="Echo hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
            tools=[echo],
        )
    ]

    # The real tool executed.
    assert executed == ["hi"]

    # All three event types appeared in the SSE stream.
    assert any(e["type"] == "tool_use" for e in events)
    assert any(e["type"] == "tool_result" for e in events)
    assert any(e["type"] == "delta" and "Done!" in e.get("content", "") for e in events)


# ---------------------------------------------------------------------------
# Test 4 — safety config is wired and terminates a runaway loop
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gemini_provider_surfaces_agent_terminated_from_safety_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """safety_from_settings flows through GeminiLLM to agent_loop.

    Patches ``safety_from_settings`` to return ``max_iterations=3`` and
    injects a script with 10 tool-call turns.  After 3 iterations the
    safety layer must emit an ``agent_terminated`` StreamEvent; the script
    must be cut short at exactly 3 calls.

    This proves the full chain:
        safety_from_settings → AgentLoopConfig.safety → agent_loop →
        AgentTerminatedEvent → GeminiLLM.stream() → StreamEvent("agent_terminated")
    """
    from app.core.agent_loop import AgentSafetyConfig
    from app.core.providers.gemini_provider import GeminiLLM

    # 10-turn runaway script — much more than the 3-iteration limit.
    turns = [tool_call_turn("ping", {}, turn_id=f"tc-{i}") for i in range(10)]
    script = ScriptedStreamFn(turns)

    provider = GeminiLLM("gemini-test")
    monkeypatch.setattr(provider, "_stream_fn", script)

    # Patch the safety factory to inject a tight limit.
    monkeypatch.setattr(
        "app.core.providers.gemini_provider.safety_from_settings",
        lambda _settings: AgentSafetyConfig(
            max_iterations=3,
            max_wall_clock_seconds=None,
            max_consecutive_llm_errors=None,
            max_consecutive_tool_errors=None,
        ),
    )

    events: list[StreamEvent] = [
        event
        async for event in provider.stream(
            question="go",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
            tools=[echo_tool("ping")],
        )
    ]

    # The termination event surfaces as a StreamEvent.
    terminated = [e for e in events if e["type"] == "agent_terminated"]
    assert len(terminated) == 1
    assert "max_iterations" in terminated[0]["content"]

    # The script was cut short — no more than 3 LLM calls.
    assert script.call_count == 3


# ---------------------------------------------------------------------------
# Test 4b — thinking_delta events translate to StreamEvent(type="thinking")
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gemini_provider_emits_thinking_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``LLMThinkingDeltaEvent`` from the stream_fn surfaces as a thinking SSE event.

    Regression test for issue #98 — before the fix, Gemini's StreamFn
    only forwarded plain text deltas and dropped reasoning chunks, so
    the frontend's "thinking" pane was always empty for Gemini users
    even though the type vocabulary supported it.

    Authoring a turn with ``thinking_then_text_turn`` proves the full
    chain:
        ScriptedStreamFn yields LLMThinkingDeltaEvent →
        agent_loop forwards as ThinkingDeltaEvent →
        GeminiLLM.stream() translates to StreamEvent(type="thinking").
    Thinking content must NOT appear as a regular ``delta`` event
    (it would render in the assistant transcript otherwise) and the
    user-visible reply must still flow through as ``delta``.
    """
    from app.core.providers.gemini_provider import GeminiLLM

    provider = GeminiLLM("gemini-test")
    monkeypatch.setattr(
        provider,
        "_stream_fn",
        ScriptedStreamFn([thinking_then_text_turn("Let me think... 2 + 2 = 4.", "4")]),
    )

    events: list[StreamEvent] = [
        event
        async for event in provider.stream(
            question="2+2?",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
        )
    ]

    thinking = [e for e in events if e["type"] == "thinking"]
    delta = [e for e in events if e["type"] == "delta"]

    # At least one thinking event surfaced with the reasoning text.
    assert len(thinking) >= 1
    assert any("2 + 2 = 4" in e.get("content", "") for e in thinking)

    # The user-visible reply still flows through as a regular delta.
    assert any(e.get("content") == "4" for e in delta)

    # Thinking text MUST NOT bleed into the regular delta stream.
    assert not any("Let me think" in e.get("content", "") for e in delta)


# ---------------------------------------------------------------------------
# Test 5 — tool result is included in context for the subsequent LLM call
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gemini_provider_accumulates_tool_result_in_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each LLM turn receives more messages than the previous one.

    After the tool executes, the second call's message list must include a
    ``toolResult`` role, proving history accumulation flows through
    GeminiLLM.stream() → agent_loop.
    """
    from app.core.providers.gemini_provider import GeminiLLM

    seen_per_call: list[int] = []
    second_call_roles: list[str] = []
    # Use a list as a mutable counter to avoid nonlocal + inline import conflicts.
    turn_counter: list[int] = [0]

    async def recording_fn(
        messages: list[AgentMessage], tools: list[AgentTool]
    ) -> AsyncIterator[LLMEvent]:
        idx = turn_counter[0]
        turn_counter[0] += 1
        seen_per_call.append(len(messages))
        if idx == 1:
            second_call_roles.extend(m["role"] for m in messages)

        if idx == 0:
            # First turn: request a tool call.
            yield LLMToolCallEvent(
                type="tool_call",
                tool_call_id="tc-r",
                name="echo",
                arguments={"value": "ctx"},
            )
            yield LLMDoneEvent(
                type="done",
                stop_reason="tool_use",
                content=[
                    ToolCallContent(
                        type="toolCall",
                        tool_call_id="tc-r",
                        name="echo",
                        arguments={"value": "ctx"},
                    )
                ],
            )
        else:
            # Subsequent turns: reply with text.
            yield LLMTextDeltaEvent(type="text_delta", text="done")
            yield LLMDoneEvent(
                type="done",
                stop_reason="stop",
                content=[TextContent(type="text", text="done")],
            )

    provider = GeminiLLM("gemini-test")
    monkeypatch.setattr(provider, "_stream_fn", recording_fn)

    async for _ in provider.stream(
        question="go",
        conversation_id=uuid4(),
        user_id=uuid4(),
        history=[],
        tools=[echo_tool()],
    ):
        pass

    # Two LLM calls were made.
    assert len(seen_per_call) == 2

    # Second call sees more messages than the first.
    assert seen_per_call[1] > seen_per_call[0]

    # Second call's message list includes the tool result.
    assert "toolResult" in second_call_roles
