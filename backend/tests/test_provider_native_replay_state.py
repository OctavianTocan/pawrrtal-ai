"""Red tests for provider-native replay state in the agent loop.

These tests specify the next Gemini tool-calling fix without implementing it:
the loop should stay provider-agnostic, but providers need an opaque replay
slot so Gemini can preserve native ``Content``/``Part`` metadata such as
``thought_signature`` between tool-call turns.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from google.genai import types as gtypes

from app.core.agent_loop.loop import agent_loop
from app.core.agent_loop.types import (
    AgentContext,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    AgentTool,
    LLMDoneEvent,
    LLMEvent,
    LLMToolCallEvent,
    TextContent,
    ToolCallContent,
    UserMessage,
)
from app.core.providers import gemini_provider


async def _execute_noop(tool_call_id: str, **kwargs: object) -> str:
    """Return a deterministic result for tool loop tests."""
    return f"ok:{tool_call_id}:{len(kwargs)}"


def _identity_convert(messages: list[AgentMessage]) -> list[AgentMessage]:
    """Pass through only messages providers understand."""
    return [m for m in messages if m["role"] in {"user", "assistant", "toolResult"}]


def _make_tool(name: str = "list_dir") -> AgentTool:
    """Return a minimal provider-neutral tool."""
    return AgentTool(
        name=name,
        description="List a directory.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        execute=_execute_noop,
    )


def _make_signed_function_call_part(signature: bytes) -> gtypes.Part:
    """Return a Gemini function-call part carrying native replay metadata."""
    return gtypes.Part(
        function_call=gtypes.FunctionCall(name="list_dir", args={"path": ""}),
        thought_signature=signature,
    )


@pytest.mark.anyio
async def test_agent_loop_carries_provider_state_to_followup_turn() -> None:
    """Opaque provider state from one assistant turn reaches the next LLM call."""
    seen_second_turn: list[AgentMessage] = []
    native_state = {"gemini": {"model_content": "native-content-placeholder"}}
    calls = 0

    async def stream_fn(
        messages: list[AgentMessage],
        tools: list[AgentTool],
    ) -> AsyncIterator[LLMEvent]:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield LLMToolCallEvent(
                type="tool_call",
                tool_call_id="call-list_dir-0",
                name="list_dir",
                arguments={"path": ""},
            )
            yield cast(
                LLMEvent,
                {
                    "type": "done",
                    "stop_reason": "tool_use",
                    "content": [
                        ToolCallContent(
                            type="toolCall",
                            tool_call_id="call-list_dir-0",
                            name="list_dir",
                            arguments={"path": ""},
                        )
                    ],
                    "provider_state": native_state,
                },
            )
            return

        seen_second_turn.extend(messages)
        yield LLMDoneEvent(
            type="done",
            stop_reason="stop",
            content=[TextContent(type="text", text="done")],
        )

    events: list[AgentEvent] = [
        event
        async for event in agent_loop(
            [UserMessage(role="user", content="List files.")],
            AgentContext(system_prompt="", messages=[], tools=[_make_tool()]),
            AgentLoopConfig(convert_to_llm=_identity_convert),
            stream_fn,
        )
    ]

    assert any(event["type"] == "agent_end" for event in events)
    assistant_turns = [msg for msg in seen_second_turn if msg["role"] == "assistant"]
    assert assistant_turns
    assert assistant_turns[0].get("provider_state") == native_state


@pytest.mark.anyio
async def test_gemini_stream_done_preserves_native_model_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gemini function-call turns preserve the original model content."""
    signature = b"gemini-thought-signature"
    signed_part = _make_signed_function_call_part(signature)
    chunk = SimpleNamespace(
        candidates=[SimpleNamespace(content=gtypes.ModelContent(parts=[signed_part]))]
    )

    class SingleChunkStream:
        """Async iterator that yields one fake Gemini chunk."""

        def __init__(self) -> None:
            self._used = False

        def __aiter__(self) -> SingleChunkStream:
            return self

        async def __anext__(self) -> Any:
            if self._used:
                raise StopAsyncIteration
            self._used = True
            return chunk

    class CapturingModels:
        """Fake ``client.aio.models`` surface."""

        async def generate_content_stream(
            self,
            *,
            model: str,
            contents: list[gtypes.Content],
            config: gtypes.GenerateContentConfig,
        ) -> SingleChunkStream:
            return SingleChunkStream()

    class CapturingClient:
        """Fake Gemini client that avoids real network calls."""

        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key
            self.aio = SimpleNamespace(models=CapturingModels())

    monkeypatch.setattr(gemini_provider.genai, "Client", CapturingClient)
    monkeypatch.setattr(gemini_provider, "_resolve_gemini_api_key", lambda _user_id: "test-key")
    stream_fn = gemini_provider.make_gemini_stream_fn("gemini-test")
    events = [
        event
        async for event in stream_fn(
            [UserMessage(role="user", content="List files.")],
            [_make_tool()],
        )
    ]

    done = events[-1]
    assert done["type"] == "done"
    provider_state = done.get("provider_state")
    assert provider_state is not None
    native_content = provider_state["gemini"]["model_content"]
    native_parts = native_content.parts or []
    assert native_parts[0].thought_signature == signature


def test_gemini_replay_prefers_native_model_content_with_thought_signature() -> None:
    """Gemini history conversion uses native content when provider state exists."""
    signature = b"gemini-thought-signature"
    native_content = gtypes.ModelContent(parts=[_make_signed_function_call_part(signature)])
    assistant_message = cast(
        AgentMessage,
        {
            "role": "assistant",
            "stop_reason": "tool_use",
            "content": [
                ToolCallContent(
                    type="toolCall",
                    tool_call_id="call-list_dir-0",
                    name="list_dir",
                    arguments={"path": ""},
                )
            ],
            "provider_state": {"gemini": {"model_content": native_content}},
        },
    )

    contents = gemini_provider._build_gemini_contents([assistant_message])

    assert len(contents) == 1
    replay_parts = contents[0].parts or []
    assert replay_parts[0].function_call is not None
    assert replay_parts[0].thought_signature == signature
