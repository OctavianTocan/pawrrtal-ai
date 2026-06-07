"""Tests for XaiLLM's StreamFn wiring into run_model_tool_loop.

Uses ``ScriptedStreamFn`` from ``tests.agent_loop_harness`` per
``.claude/rules/testing/agent-loop-testing-philosophy.md`` — no real
xAI API calls are made.  These tests exercise the provider's
translation layer (AgentEvent → StreamEvent) and confirm that safety
config flows end-to-end from ``safety_from_settings`` through
``run_model_tool_loop`` to the SSE output, mirroring the Gemini test suite so
parity is verified, not asserted.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from app.agents.types import (
    AgentMessage,
    AgentTool,
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    LLMToolCallEvent,
    TextContent,
    ToolCallContent,
)
from app.providers.base import StreamEvent
from tests.agent_loop_harness import (
    ScriptedStreamFn,
    echo_tool,
    text_turn,
    tool_call_turn,
)


@pytest.mark.anyio
async def test_xai_provider_yields_delta_events_from_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """XaiLLM.stream() translates run_model_tool_loop text_deltas to StreamEvent deltas."""
    from app.providers.xai import XaiLLM

    provider = XaiLLM("grok-test")
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


@pytest.mark.anyio
async def test_xai_provider_passes_history_to_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prior messages in history are included in what the StreamFn sees."""
    from app.providers.xai import XaiLLM

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

    provider = XaiLLM("grok-test")
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

    assert len(seen_messages) == 1
    # 2 history messages + current question = 3 total visible to the LLM.
    assert len(seen_messages[0]) == 3


@pytest.mark.anyio
async def test_xai_provider_emits_tool_use_and_result_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool call lifecycle events translate from AgentEvents to StreamEvents."""
    from app.providers.xai import XaiLLM

    executed: list[str] = []

    async def echo_execute(tool_call_id: str, **kwargs: object) -> str:
        executed.append(str(kwargs.get("value", "")))
        return f"echoed: {kwargs.get('value', '')}"

    from app.tools.display import make_tool_display

    echo = AgentTool(
        name="echo",
        description="Echo",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        execute=echo_execute,
        display=make_tool_display(
            icon="🔁",
            label="Echo",
            present=lambda args: f"🔁 Echoing {args['value']}",
            compact=lambda args: f"Echo -> {args['value']}",
        ),
    )

    provider = XaiLLM("grok-test")
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

    assert executed == ["hi"]
    tool_use = next(e for e in events if e["type"] == "tool_use")
    assert tool_use["input"] == {"value": "hi"}
    assert tool_use["display"] == {
        "icon": "🔁",
        "label": "Echo",
        "present": "🔁 Echoing hi",
        "compact": "Echo -> hi",
    }
    assert any(e["type"] == "tool_result" for e in events)
    assert any(e["type"] == "delta" and "Done!" in e.get("content", "") for e in events)


@pytest.mark.anyio
async def test_xai_provider_surfaces_agent_terminated_from_safety_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """safety_from_settings flows through XaiLLM to run_model_tool_loop."""
    from app.agents import AgentSafetyConfig
    from app.providers.xai import XaiLLM

    turns = [tool_call_turn("ping", {}, turn_id=f"tc-{i}") for i in range(10)]
    script = ScriptedStreamFn(turns)

    provider = XaiLLM("grok-test")
    monkeypatch.setattr(provider, "_stream_fn", script)

    monkeypatch.setattr(
        "app.providers.xai.provider.safety_from_settings",
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

    terminated = [e for e in events if e["type"] == "agent_terminated"]
    assert len(terminated) == 1
    assert "max_iterations" in terminated[0]["content"]
    # The script was cut short — no more than 3 LLM calls.
    assert script.call_count == 3


@pytest.mark.anyio
async def test_xai_provider_accumulates_tool_result_in_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each LLM turn receives more messages than the previous one.

    Proves the tool-result message accumulates in the loop's context
    even though xAI itself has no native session concept.
    """
    from app.providers.xai import XaiLLM

    seen_per_call: list[int] = []
    second_call_roles: list[str] = []
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
            yield LLMTextDeltaEvent(type="text_delta", text="done")
            yield LLMDoneEvent(
                type="done",
                stop_reason="stop",
                content=[TextContent(type="text", text="done")],
            )

    provider = XaiLLM("grok-test")
    monkeypatch.setattr(provider, "_stream_fn", recording_fn)

    async for _ in provider.stream(
        question="go",
        conversation_id=uuid4(),
        user_id=uuid4(),
        history=[],
        tools=[echo_tool()],
    ):
        pass

    assert len(seen_per_call) == 2
    assert seen_per_call[1] > seen_per_call[0]
    assert "toolResult" in second_call_roles
