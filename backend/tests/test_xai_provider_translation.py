"""Unit tests for xAI provider's xai-sdk message/stream translation helpers.

Exercises the small pure helpers that turn ``AgentMessage`` lists into
``chat_pb2`` protos and translate xai-sdk ``Chunk`` / ``Response``
typed objects back into loop-shaped ``LLMEvent`` / ``StreamEvent``.

These tests DO NOT hit the agent loop — that path is covered by
``test_xai_stream_fn.py`` via ``ScriptedStreamFn``.  Splitting the
concerns keeps each file focused: the helpers only do shape
translation, so they should be testable without booting the loop.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from xai_sdk.proto import chat_pb2

from app.core.agent_loop.types import (
    AgentTool,
    AssistantMessage,
    TextContent,
    ToolCallContent,
    ToolResultContent,
    ToolResultMessage,
    UserMessage,
)
from app.core.providers._xai_messages import (
    build_xai_messages,
    build_xai_tools,
)
from app.core.providers._xai_stream import (
    UsageAccumulator,
    deltas_from_chunk,
    done_event_from_response,
    tool_call_events_from_response,
    usage_record_from_response,
)
from app.core.providers.xai_provider import (
    XaiLLM,
    _map_reasoning_effort,
    _resolve_xai_api_key,
    make_xai_stream_fn,
)

# ---------------------------------------------------------------------------
# Fake xai-sdk surface
# ---------------------------------------------------------------------------


def _fake_chunk(
    *,
    content: str | None = None,
    reasoning_content: str | None = None,
    tool_calls: list[Any] | None = None,
) -> SimpleNamespace:
    """Shape a ``xai_sdk.chat.Chunk``-like object the provider can iterate."""
    return SimpleNamespace(
        content=content or "",
        reasoning_content=reasoning_content or "",
        tool_calls=tool_calls or [],
    )


def _fake_tool_call(
    *,
    name: str,
    arguments: dict[str, Any] | None = None,
    call_id: str = "tc-1",
) -> SimpleNamespace:
    """One xai-sdk-style tool call: ``call.id``, ``call.function.name``, ``call.function.arguments``."""
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments or {}),
        ),
    )


def _fake_response(
    *,
    content: str = "",
    reasoning_content: str = "",
    tool_calls: list[Any] | None = None,
    finish_reason: str = "REASON_STOP",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float | None = None,
) -> SimpleNamespace:
    """Shape a ``xai_sdk.chat.Response``-like accumulated object."""
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    return SimpleNamespace(
        content=content,
        reasoning_content=reasoning_content,
        tool_calls=tool_calls or [],
        finish_reason=finish_reason,
        usage=usage,
        cost_usd=cost_usd,
    )


class _FakeChat:
    """Stand-in for ``client.chat.create(...)`` returning an iterable Chat.

    ``last_create_kwargs`` records the kwargs the provider passed so
    tests can assert on request shape (model, tools, search_parameters,
    reasoning_effort).  The constructor takes a script of
    ``(response, chunk)`` tuples — yielded by ``stream()`` in order.
    """

    def __init__(
        self,
        steps: list[tuple[Any, Any]],
        create_kwargs: dict[str, Any],
    ) -> None:
        self._steps = steps
        self.last_create_kwargs = create_kwargs

    async def stream(self) -> AsyncIterator[tuple[Any, Any]]:
        for step in self._steps:
            yield step


class _FakeChatNamespace:
    """Holds the captured kwargs across ``create()`` calls."""

    def __init__(self, steps: list[tuple[Any, Any]]) -> None:
        self._steps = steps
        self.last_create_kwargs: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> _FakeChat:
        self.last_create_kwargs = kwargs
        return _FakeChat(self._steps, kwargs)


class _FakeAsyncClient:
    """Async-context-manager stand-in for ``xai_sdk.AsyncClient``."""

    def __init__(self, steps: list[tuple[Any, Any]]) -> None:
        self.chat = _FakeChatNamespace(steps)

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def close(self) -> None:
        return None


def _patch_async_client(
    monkeypatch: pytest.MonkeyPatch,
    steps: list[tuple[Any, Any]],
) -> _FakeAsyncClient:
    """Patch ``AsyncClient`` in the provider module and return the fake."""
    fake = _FakeAsyncClient(steps)
    monkeypatch.setattr(
        "app.core.providers.xai_provider.AsyncClient",
        lambda **_kwargs: fake,
    )
    return fake


# ---------------------------------------------------------------------------
# build_xai_tools
# ---------------------------------------------------------------------------


def test_build_tools_returns_none_when_empty() -> None:
    """No tools → None so the create() call omits the field entirely."""
    assert build_xai_tools([]) is None


def test_build_tools_wraps_each_agent_tool_in_function_proto() -> None:
    """Each AgentTool becomes one ``chat_pb2.Tool`` with the function spec."""

    async def _execute(_call_id: str, **_kwargs: Any) -> str:
        return ""

    pawrrtal_tool = AgentTool(
        name="search",
        description="Search the web",
        parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        execute=_execute,
    )

    declarations = build_xai_tools([pawrrtal_tool])
    assert declarations is not None
    assert len(declarations) == 1
    proto = declarations[0]
    assert proto.function.name == "search"
    assert proto.function.description == "Search the web"
    parsed = json.loads(proto.function.parameters)
    assert parsed == {
        "type": "object",
        "properties": {"q": {"type": "string"}},
    }


# ---------------------------------------------------------------------------
# build_xai_messages
# ---------------------------------------------------------------------------


def test_build_messages_prepends_developer_system_prompt() -> None:
    """The system prompt becomes the first ``ROLE_DEVELOPER`` message."""
    msgs = build_xai_messages(
        [UserMessage(role="user", content="hello")],
        system_prompt="you are helpful",
    )
    assert msgs[0].role == chat_pb2.MessageRole.ROLE_DEVELOPER
    assert msgs[0].content[0].text == "you are helpful"
    assert msgs[1].role == chat_pb2.MessageRole.ROLE_USER
    assert msgs[1].content[0].text == "hello"


def test_build_messages_translates_assistant_with_tool_calls() -> None:
    """An assistant turn with tool calls renders the proto's ``tool_calls`` field."""
    assistant = AssistantMessage(
        role="assistant",
        content=[
            TextContent(type="text", text="searching..."),
            ToolCallContent(
                type="toolCall",
                tool_call_id="tc-1",
                name="search",
                arguments={"q": "pawrrtal"},
            ),
        ],
        stop_reason="tool_use",
    )
    msgs = build_xai_messages([assistant], system_prompt="sys")
    proto = msgs[1]
    assert proto.role == chat_pb2.MessageRole.ROLE_ASSISTANT
    assert proto.content[0].text == "searching..."
    assert len(proto.tool_calls) == 1
    call = proto.tool_calls[0]
    assert call.id == "tc-1"
    assert call.function.name == "search"
    assert json.loads(call.function.arguments) == {"q": "pawrrtal"}


def test_build_messages_assistant_tool_calls_only_includes_empty_text() -> None:
    """An assistant turn that's only tool_calls includes an empty text element.

    The xAI server requires at least one content element per message,
    so tool-calls-only turns get ``text("")`` instead of an empty list.
    """
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCallContent(type="toolCall", tool_call_id="tc-2", name="ping", arguments={}),
        ],
        stop_reason="tool_use",
    )
    msgs = build_xai_messages([assistant], system_prompt="sys")
    proto = msgs[1]
    assert len(proto.content) == 1
    assert proto.content[0].text == ""
    assert proto.tool_calls[0].function.name == "ping"


def test_build_messages_translates_tool_result_to_role_tool() -> None:
    """A toolResult message renders the SDK's tool_result helper output."""
    msg = ToolResultMessage(
        role="toolResult",
        tool_call_id="tc-1",
        name="search",
        content=[
            ToolResultContent(type="text", text="line 1"),
            ToolResultContent(type="text", text="line 2"),
        ],
        is_error=False,
    )
    msgs = build_xai_messages([msg], system_prompt="sys")
    proto = msgs[1]
    assert proto.role == chat_pb2.MessageRole.ROLE_TOOL
    assert proto.tool_call_id == "tc-1"
    assert proto.content[0].text == "line 1\nline 2"


def test_build_messages_drops_empty_user_messages() -> None:
    """Blank-only user messages are dropped — historical behaviour."""
    msgs = build_xai_messages([UserMessage(role="user", content="   ")], system_prompt="sys")
    # Only the system prompt survives.
    assert len(msgs) == 1
    assert msgs[0].role == chat_pb2.MessageRole.ROLE_DEVELOPER


# ---------------------------------------------------------------------------
# _resolve_xai_api_key
# ---------------------------------------------------------------------------


def test_resolve_api_key_uses_settings_when_no_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No workspace_id → use the gateway-global key from Settings."""
    monkeypatch.setattr(
        "app.core.providers.xai_provider.settings",
        SimpleNamespace(xai_api_key="gateway-key"),
    )
    assert _resolve_xai_api_key(None) == "gateway-key"


def test_resolve_api_key_workspace_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """workspace_root present → delegate to resolve_api_key (mocked)."""
    workspace_root = Path("/tmp/some-workspace")
    monkeypatch.setattr(
        "app.core.providers.xai_provider.resolve_api_key",
        lambda wr, key: "workspace-key" if (wr, key) == (workspace_root, "XAI_API_KEY") else None,
    )
    assert _resolve_xai_api_key(workspace_root) == "workspace-key"


# ---------------------------------------------------------------------------
# _map_reasoning_effort
# ---------------------------------------------------------------------------


def test_map_reasoning_effort_collapses_five_levels_to_three() -> None:
    """Pawrrtal's five-level UI knob → grok-4.3's three-tier proto enum.

    xAI's Grok 4.3 reasoning enum is ``EFFORT_NONE``, ``EFFORT_LOW``,
    ``EFFORT_HIGH``. ``"minimal"`` opts into the no-thinking tier
    (issue #373); ``"low"`` and ``"medium"`` collapse to
    ``EFFORT_LOW``; ``"high"`` and ``"extra-high"`` collapse to
    ``EFFORT_HIGH``; ``None`` omits the field so xAI's server-side
    default fires.
    """
    assert _map_reasoning_effort(None) is None
    assert _map_reasoning_effort("minimal") == chat_pb2.ReasoningEffort.EFFORT_NONE
    assert _map_reasoning_effort("low") == chat_pb2.ReasoningEffort.EFFORT_LOW
    assert _map_reasoning_effort("medium") == chat_pb2.ReasoningEffort.EFFORT_LOW
    assert _map_reasoning_effort("high") == chat_pb2.ReasoningEffort.EFFORT_HIGH
    assert _map_reasoning_effort("extra-high") == chat_pb2.ReasoningEffort.EFFORT_HIGH


# ---------------------------------------------------------------------------
# Stream helpers (Chunk → ChunkDeltas, Response → events)
# ---------------------------------------------------------------------------


def test_deltas_from_chunk_text_only() -> None:
    """A plain text chunk yields ``ChunkDeltas(text=..., thinking=None)``."""
    deltas = deltas_from_chunk(_fake_chunk(content="hi"))
    assert deltas.text == "hi"
    assert deltas.thinking is None


def test_deltas_from_chunk_reasoning_only() -> None:
    """A reasoning-only chunk yields ``thinking`` without bleeding into ``text``."""
    deltas = deltas_from_chunk(_fake_chunk(reasoning_content="Let me think..."))
    assert deltas.text is None
    assert deltas.thinking == "Let me think..."


def test_deltas_from_chunk_empty_strings_normalise_to_none() -> None:
    """Empty-string fields normalise to None so the caller can branch on truthiness."""
    deltas = deltas_from_chunk(_fake_chunk(content="", reasoning_content=""))
    assert deltas.text is None
    assert deltas.thinking is None


def test_tool_call_events_from_response_translates_each_call() -> None:
    """Each accumulated tool call becomes one :class:`LLMToolCallEvent`."""
    response = _fake_response(
        tool_calls=[
            _fake_tool_call(name="search", arguments={"q": "x"}, call_id="tc-A"),
            _fake_tool_call(name="get_weather", arguments={"city": "Paris"}, call_id="tc-B"),
        ],
    )
    events = tool_call_events_from_response(response)
    assert len(events) == 2
    assert events[0]["name"] == "search"
    assert events[0]["arguments"] == {"q": "x"}
    assert events[0]["tool_call_id"] == "tc-A"
    assert events[1]["name"] == "get_weather"
    assert events[1]["arguments"] == {"city": "Paris"}
    assert events[1]["tool_call_id"] == "tc-B"


def test_tool_call_events_handle_empty_arguments_as_dict() -> None:
    """A tool call with empty-string arguments becomes ``{}``."""
    call = SimpleNamespace(
        id="tc-1",
        function=SimpleNamespace(name="ping", arguments=""),
    )
    response = _fake_response(tool_calls=[call])
    events = tool_call_events_from_response(response)
    assert events[0]["arguments"] == {}


def test_done_event_marks_tool_use_when_tool_calls_present() -> None:
    """``done.stop_reason="tool_use"`` when the response carries tool calls."""
    response = _fake_response(
        content="thinking...",
        tool_calls=[_fake_tool_call(name="search", arguments={"q": "x"})],
        finish_reason="REASON_TOOL_CALLS",
    )
    done = done_event_from_response(response)
    assert done["stop_reason"] == "tool_use"
    blocks = list(done["content"])
    text_blocks = [b for b in blocks if b["type"] == "text"]
    tool_blocks = [b for b in blocks if b["type"] == "toolCall"]
    assert text_blocks[0]["text"] == "thinking..."
    assert tool_blocks[0]["name"] == "search"


def test_done_event_marks_stop_for_text_only_response() -> None:
    """``done.stop_reason="stop"`` when there are no tool calls."""
    response = _fake_response(content="final answer", finish_reason="REASON_STOP")
    done = done_event_from_response(response)
    assert done["stop_reason"] == "stop"
    assert done["content"] == [TextContent(type="text", text="final answer")]


def test_done_event_marks_tool_use_when_finish_reason_says_so() -> None:
    """Even with no tool_calls list, ``REASON_TOOL_CALLS`` flips stop_reason.

    Defensive — guards against an SDK chunk-vs-response race where the
    response's ``tool_calls`` is empty momentarily but the finish reason
    has already been written.
    """
    response = _fake_response(content="", finish_reason="REASON_TOOL_CALLS")
    done = done_event_from_response(response)
    assert done["stop_reason"] == "tool_use"


def test_usage_record_reads_tokens_and_cost() -> None:
    """``usage_record_from_response`` reads ``cost_usd`` and token counts."""
    response = _fake_response(prompt_tokens=42, completion_tokens=17, cost_usd=0.0001234)
    record = usage_record_from_response(response)
    assert record is not None
    assert record.input_tokens == 42
    assert record.output_tokens == 17
    assert record.cost_usd == pytest.approx(0.0001234)


def test_usage_record_returns_none_when_nothing_reported() -> None:
    """Empty usage + missing cost → None, so the ledger sees nothing."""
    response = _fake_response(prompt_tokens=0, completion_tokens=0, cost_usd=None)
    assert usage_record_from_response(response) is None


def test_usage_accumulator_sums_across_iterations() -> None:
    """The accumulator sums multiple :class:`UsageRecord` instances."""
    from app.core.providers._xai_stream import UsageRecord

    sink = UsageAccumulator()
    sink.absorb(UsageRecord(input_tokens=10, output_tokens=5, cost_usd=0.001))
    sink.absorb(UsageRecord(input_tokens=20, output_tokens=15, cost_usd=0.003))
    sink.absorb(None)  # no-op for turns without usage
    assert sink.saw_any is True
    assert sink.input_tokens == 30
    assert sink.output_tokens == 20
    assert sink.cost_usd == pytest.approx(0.004)


# ---------------------------------------------------------------------------
# StreamFn integration against a fake xai-sdk client
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stream_fn_yields_text_and_thinking_deltas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Text chunks → ``LLMTextDeltaEvent``; reasoning chunks → ``LLMThinkingDeltaEvent``.

    The frontend's "thinking" pane (already wired for Gemini) renders
    these as a separate panel from the assistant transcript.
    """
    response_text_only = _fake_response(content="4", finish_reason="REASON_STOP")
    response_after_reasoning = _fake_response(
        content="4",
        reasoning_content="Let me think... 2 + 2 = 4.",
        finish_reason="REASON_STOP",
    )
    steps: list[tuple[Any, Any]] = [
        (response_after_reasoning, _fake_chunk(reasoning_content="Let me think... 2 + 2 = 4.")),
        (response_text_only, _fake_chunk(content="4")),
    ]
    _patch_async_client(monkeypatch, steps)

    stream_fn = make_xai_stream_fn("grok-4.3", None, system_prompt="sys")
    events = [event async for event in stream_fn([], [])]
    thinking = [e for e in events if e["type"] == "thinking_delta"]
    text = [e for e in events if e["type"] == "text_delta"]
    assert any("2 + 2 = 4" in e["text"] for e in thinking)
    assert any(e["text"] == "4" for e in text)
    # Reasoning must not bleed into the regular text stream.
    assert not any("Let me think" in e["text"] for e in text)


@pytest.mark.anyio
async def test_stream_fn_emits_tool_calls_after_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool calls surface as ``LLMToolCallEvent`` after the stream ends.

    Reading from the accumulated :class:`Response` (not from streamed
    chunks) sidesteps the question of how xAI partitions tool-call
    chunks — the SDK accumulates either way.
    """
    final_response = _fake_response(
        content="searching",
        tool_calls=[_fake_tool_call(name="search", arguments={"q": "pawrrtal"})],
        finish_reason="REASON_TOOL_CALLS",
    )
    steps: list[tuple[Any, Any]] = [
        (final_response, _fake_chunk(content="searching")),
    ]
    _patch_async_client(monkeypatch, steps)

    stream_fn = make_xai_stream_fn("grok-4.3", None, system_prompt="sys")
    events = [event async for event in stream_fn([], [])]
    tool_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0]["name"] == "search"
    assert tool_events[0]["arguments"] == {"q": "pawrrtal"}
    # Tool call must arrive after every delta but before the done event.
    delta_idx = next(i for i, e in enumerate(events) if e["type"] == "text_delta")
    tool_idx = next(i for i, e in enumerate(events) if e["type"] == "tool_call")
    done_idx = next(i for i, e in enumerate(events) if e["type"] == "done")
    assert delta_idx < tool_idx < done_idx


@pytest.mark.anyio
async def test_stream_fn_request_carries_reasoning_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The create() kwargs forward the mapped reasoning effort."""
    fake = _patch_async_client(
        monkeypatch, [(_fake_response(content="hi"), _fake_chunk(content="hi"))]
    )

    stream_fn = make_xai_stream_fn(
        "grok-4.3", None, system_prompt="custom-sys", reasoning_effort="extra-high"
    )
    async for _ in stream_fn([UserMessage(role="user", content="hello")], []):
        pass

    kwargs = fake.chat.last_create_kwargs
    assert kwargs is not None
    assert kwargs["model"] == "grok-4.3"
    assert kwargs["messages"][0].role == chat_pb2.MessageRole.ROLE_DEVELOPER
    assert kwargs["messages"][0].content[0].text == "custom-sys"
    assert kwargs["reasoning_effort"] == chat_pb2.ReasoningEffort.EFFORT_HIGH


@pytest.mark.anyio
async def test_stream_fn_captures_usage_into_accumulator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The terminal :class:`Response`'s usage lands on the shared accumulator.

    Multiple iterations of the agent loop each call the StreamFn; the
    accumulator must sum across them so a tool-using turn pays for
    every internal LLM call.
    """
    final_response = _fake_response(
        content="hi",
        prompt_tokens=120,
        completion_tokens=45,
        cost_usd=0.0001234,
        finish_reason="REASON_STOP",
    )
    _patch_async_client(monkeypatch, [(final_response, _fake_chunk(content="hi"))])

    sink = UsageAccumulator()
    stream_fn = make_xai_stream_fn("grok-4.3", None, system_prompt="sys", usage_sink=sink)
    async for _ in stream_fn([], []):
        pass

    assert sink.saw_any
    assert sink.input_tokens == 120
    assert sink.output_tokens == 45
    assert sink.cost_usd == pytest.approx(0.0001234)


@pytest.mark.anyio
async def test_stream_fn_surfaces_upstream_error_as_done_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exception during streaming becomes a graceful error ``done`` event."""

    class _ExplodingChatNamespace:
        def create(self, **_kwargs: Any) -> Any:
            raise RuntimeError("upstream 503")

    class _ExplodingClient:
        def __init__(self) -> None:
            self.chat = _ExplodingChatNamespace()

        async def __aenter__(self) -> _ExplodingClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        "app.core.providers.xai_provider.AsyncClient",
        lambda **_kwargs: _ExplodingClient(),
    )

    stream_fn = make_xai_stream_fn("grok-4.3", None, system_prompt="sys")
    events = [event async for event in stream_fn([], [])]
    text_events = [e for e in events if e["type"] == "text_delta"]
    done_events = [e for e in events if e["type"] == "done"]
    assert any("upstream 503" in e["text"] for e in text_events)
    assert done_events[-1]["stop_reason"] == "error"


# ---------------------------------------------------------------------------
# End-to-end: XaiLLM.stream emits the terminal usage StreamEvent
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_xai_provider_emits_terminal_usage_stream_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``XaiLLM.stream`` emits ``StreamEvent(type="usage", ...)`` after agent_loop.

    The chat aggregator folds this into the cost ledger via
    :func:`record_turn_cost_if_enabled`, same shape as Claude's
    ``_build_usage_event``.  Real ``agent_loop`` runs end-to-end with
    a fake :class:`AsyncClient` so the actual usage-capture code path
    is exercised, not a patched factory.
    """
    final_response = _fake_response(
        content="hi",
        prompt_tokens=42,
        completion_tokens=17,
        cost_usd=0.000125,
        finish_reason="REASON_STOP",
    )
    _patch_async_client(monkeypatch, [(final_response, _fake_chunk(content="hi"))])

    provider = XaiLLM("grok-4.3")
    events = [
        e
        async for e in provider.stream(
            question="Hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
        )
    ]
    usage_events = [e for e in events if e["type"] == "usage"]
    assert len(usage_events) == 1
    usage_event = usage_events[0]
    assert usage_event["input_tokens"] == 42
    assert usage_event["output_tokens"] == 17
    assert usage_event["cost_usd"] == pytest.approx(0.000125)
    # Usage event arrives after the visible reply — cost ledger row is
    # finalised once the user-visible reply is on the wire.
    delta_idx = events.index(next(e for e in events if e["type"] == "delta"))
    usage_idx = events.index(usage_event)
    assert usage_idx > delta_idx


@pytest.mark.anyio
async def test_xai_provider_skips_usage_event_when_no_chunk_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no turn reported usage, no usage event fires — no spurious zeros."""
    from tests.agent_harness import ScriptedStreamFn, text_turn

    provider = XaiLLM("grok-4.3")
    monkeypatch.setattr(provider, "_stream_fn", ScriptedStreamFn([text_turn("hi")]))
    events = [
        e
        async for e in provider.stream(
            question="Hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
        )
    ]
    assert not any(e["type"] == "usage" for e in events)
