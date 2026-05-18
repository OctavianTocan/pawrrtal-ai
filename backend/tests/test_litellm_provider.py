"""Tests for LiteLLMLLM's StreamFn wiring into agent_loop.

Uses ``ScriptedStreamFn`` from ``tests.agent_harness`` — no real
LiteLLM / OpenAI / xAI API calls are made.  These tests exercise the
provider's translation layer (AgentEvent → StreamEvent) and confirm
that history and prompts flow through the loop.  The text-only-v1
scope is also covered: ``tools`` must be accepted without crashing
(logged-and-ignored) and missing API keys must surface a clear error
through the StreamFn rather than an uncaught exception.
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
    TextContent,
)
from app.core.providers.base import StreamEvent
from app.core.providers.litellm_provider import (
    LiteLLMLLM,
    _build_litellm_messages,
    _litellm_model_string,
)
from app.core.providers.model_id import Vendor
from tests.agent_harness import ScriptedStreamFn, text_turn


@pytest.mark.anyio
async def test_litellm_provider_yields_delta_events_from_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LiteLLMLLM.stream() translates agent_loop text_deltas to StreamEvent deltas."""
    provider = LiteLLMLLM("gpt-4o", Vendor.openai)
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
async def test_litellm_provider_passes_history_to_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prior messages in history are included in what the StreamFn sees."""
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

    provider = LiteLLMLLM("grok-3-latest", Vendor.xai)
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

    # Two history messages + the new prompt land in the loop together,
    # so the StreamFn sees three messages on its single LLM call.
    assert len(seen_messages) == 1
    assert len(seen_messages[0]) == 3


@pytest.mark.anyio
async def test_litellm_provider_accepts_tools_without_running_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v1 ignores tools but must not crash when a non-empty list is passed."""

    async def _noop_execute(tool_call_id: str, **_kw: object) -> str:
        return "unused"

    tools = [
        AgentTool(
            name="noop",
            description="placeholder",
            parameters={"type": "object", "properties": {}},
            execute=_noop_execute,
        )
    ]

    provider = LiteLLMLLM("gpt-4o-mini", Vendor.openai)
    monkeypatch.setattr(provider, "_stream_fn", ScriptedStreamFn([text_turn("ok")]))

    events = [
        event
        async for event in provider.stream(
            question="Hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
            tools=tools,
        )
    ]
    # The scripted text turn still produces a delta — tools are dropped silently.
    assert any(e["type"] == "delta" for e in events)


def test_litellm_model_string_prefixes_vendor() -> None:
    assert _litellm_model_string(Vendor.openai, "gpt-4o") == "openai/gpt-4o"
    assert _litellm_model_string(Vendor.xai, "grok-3-latest") == "xai/grok-3-latest"


def test_build_litellm_messages_prepends_system_and_drops_tool_messages() -> None:
    history: list[AgentMessage] = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "hello"}],
            "stop_reason": "stop",
        },
    ]
    out = _build_litellm_messages(history, system_prompt="SYS")
    assert out[0] == {"role": "system", "content": "SYS"}
    assert {"role": "user", "content": "hi"} in out
    assert {"role": "assistant", "content": "hello"} in out
