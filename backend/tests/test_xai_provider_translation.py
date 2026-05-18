"""Unit tests for xAI provider request/response translation helpers.

These exercise the small pure helpers that turn ``AgentMessage`` lists
and openai-SDK streaming chunks into the OpenAI wire shape (and back).
They do NOT hit the agent loop — that path is covered by
``test_xai_stream_fn.py`` via ``ScriptedStreamFn``.  Splitting the
concerns keeps each test focused: the helpers only do shape
translation, so they should be testable without booting the loop.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from app.core.agent_loop.types import (
    AgentTool,
    AssistantMessage,
    LLMDoneEvent,
    TextContent,
    ToolCallContent,
    ToolResultContent,
    ToolResultMessage,
    UserMessage,
)
from app.core.providers._xai_messages import (
    build_xai_messages,
    build_xai_tool_declarations,
)
from app.core.providers._xai_stream import parse_tool_arguments
from app.core.providers.xai_provider import (
    XAI_BASE_URL,
    XaiLLM,
    _build_xai_extra_body,
    _map_reasoning_effort,
    _resolve_xai_api_key,
    make_xai_stream_fn,
)


def _delta(
    *,
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    finish: str | None = None,
) -> SimpleNamespace:
    """Shape a ``ChatCompletionChunk``-like fake the provider can iterate."""
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish, index=0)
    return SimpleNamespace(choices=[choice])


def _tc_delta(
    *,
    index: int,
    tc_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> SimpleNamespace:
    """Fake one ``ChoiceDeltaToolCall`` fragment."""
    fn = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=tc_id, function=fn)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_build_tool_declarations_returns_none_when_empty() -> None:
    """No tools → None (not []) so we skip the param entirely on the wire."""
    assert build_xai_tool_declarations([]) is None


def test_build_tool_declarations_wraps_each_tool_in_function_shape() -> None:
    """Each AgentTool becomes one ``{"type":"function", "function": ...}`` entry."""

    async def _execute(_call_id: str, **_kwargs: Any) -> str:
        return ""

    tool = AgentTool(
        name="search",
        description="Search the web",
        parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        execute=_execute,
    )

    declarations = build_xai_tool_declarations([tool])

    assert declarations is not None
    assert declarations == [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search the web",
                "parameters": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                },
            },
        }
    ]


def test_build_xai_messages_prepends_system_prompt() -> None:
    """The system prompt becomes the first ``role="system"`` entry."""
    msgs = build_xai_messages(
        [UserMessage(role="user", content="hello")],
        system_prompt="you are helpful",
    )
    assert msgs[0] == {"role": "system", "content": "you are helpful"}
    assert msgs[1] == {"role": "user", "content": "hello"}


def test_build_xai_messages_translates_assistant_with_tool_calls() -> None:
    """An assistant turn splits text + tool calls into the OpenAI shape."""
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
    # Index 0 is the system prompt; index 1 is the assistant turn.
    entry = msgs[1]
    assert entry["role"] == "assistant"
    assert entry["content"] == "searching..."
    assert entry["tool_calls"] == [
        {
            "id": "tc-1",
            "type": "function",
            "function": {"name": "search", "arguments": json.dumps({"q": "pawrrtal"})},
        }
    ]


def test_build_xai_messages_assistant_without_text_uses_none_content() -> None:
    """An assistant turn that's only tool_calls still wires content=None."""
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCallContent(type="toolCall", tool_call_id="tc-2", name="ping", arguments={}),
        ],
        stop_reason="tool_use",
    )
    msgs = build_xai_messages([assistant], system_prompt="sys")
    entry = msgs[1]
    assert entry["content"] is None
    assert entry["tool_calls"][0]["function"]["name"] == "ping"


def test_build_xai_messages_translates_tool_result() -> None:
    """A toolResult message renders into OpenAI's ``role="tool"`` entry."""
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
    assert msgs[1] == {
        "role": "tool",
        "tool_call_id": "tc-1",
        "content": "line 1\nline 2",
    }


def test_parse_tool_arguments_handles_empty_and_invalid() -> None:
    """Empty string → empty dict; bad JSON → empty dict with a warning."""
    assert parse_tool_arguments("", "ping") == {}
    assert parse_tool_arguments('{"x": 1}', "ping") == {"x": 1}
    # Invalid JSON should fall back to empty, not raise.
    assert parse_tool_arguments("{not json", "ping") == {}


def test_resolve_xai_api_key_uses_settings_when_no_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No workspace_id → use the gateway-global key from Settings."""
    monkeypatch.setattr(
        "app.core.providers.xai_provider.settings",
        SimpleNamespace(xai_api_key="gateway-key"),
    )
    assert _resolve_xai_api_key(None) == "gateway-key"


def test_resolve_xai_api_key_workspace_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """workspace_id present → delegate to resolve_api_key (mocked)."""
    workspace_id = uuid4()
    monkeypatch.setattr(
        "app.core.providers.xai_provider.resolve_api_key",
        lambda wid, key: "workspace-key" if (wid, key) == (workspace_id, "XAI_API_KEY") else None,
    )
    assert _resolve_xai_api_key(workspace_id) == "workspace-key"


# ---------------------------------------------------------------------------
# StreamFn integration with a fake openai client
# ---------------------------------------------------------------------------


class _FakeStream:
    """Async-iterable wrapper around a list of chunk fakes."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Any]:
        for chunk in self._chunks:
            yield chunk


class _FakeCompletions:
    """Captures the kwargs the provider passes to ``chat.completions.create``."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks
        self.last_kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> _FakeStream:
        self.last_kwargs = kwargs
        return _FakeStream(self._chunks)


class _FakeClient:
    """Replaces ``AsyncOpenAI`` so no network call happens during tests."""

    def __init__(self, chunks: list[Any]) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(chunks))


@pytest.mark.anyio
async def test_stream_fn_assembles_tool_call_from_streamed_fragments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streamed tool-call arg fragments are accumulated into one LLMToolCallEvent."""
    chunks = [
        _delta(content="thinking..."),
        _delta(
            tool_calls=[
                _tc_delta(index=0, tc_id="call-1", name="search", arguments='{"q":'),
            ]
        ),
        _delta(tool_calls=[_tc_delta(index=0, arguments=' "grok"')]),
        _delta(tool_calls=[_tc_delta(index=0, arguments="}")]),
        _delta(finish="tool_calls"),
    ]
    fake = _FakeClient(chunks)
    monkeypatch.setattr("app.core.providers.xai_provider.AsyncOpenAI", lambda **_kwargs: fake)

    stream_fn = make_xai_stream_fn("grok-4.3", None, system_prompt="sys")
    events = [event async for event in stream_fn([], [])]

    text_events = [e for e in events if e["type"] == "text_delta"]
    tool_events = [e for e in events if e["type"] == "tool_call"]
    done_events = [e for e in events if e["type"] == "done"]

    assert [e["text"] for e in text_events] == ["thinking..."]
    assert len(tool_events) == 1
    assert tool_events[0]["name"] == "search"
    assert tool_events[0]["arguments"] == {"q": "grok"}
    assert tool_events[0]["tool_call_id"] == "call-1"

    assert len(done_events) == 1
    done = done_events[0]
    assert done["stop_reason"] == "tool_use"
    assert any(b["type"] == "toolCall" for b in done["content"])


@pytest.mark.anyio
async def test_stream_fn_plain_text_turn_emits_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pure-text turn ends with ``stop_reason='stop'`` and one text block."""
    chunks = [_delta(content="hi"), _delta(content=" there"), _delta(finish="stop")]
    fake = _FakeClient(chunks)
    monkeypatch.setattr("app.core.providers.xai_provider.AsyncOpenAI", lambda **_kwargs: fake)

    stream_fn = make_xai_stream_fn("grok-4.3", None, system_prompt="sys")
    events = [event async for event in stream_fn([], [])]

    assert events[-1]["type"] == "done"
    assert events[-1]["stop_reason"] == "stop"
    assert events[-1]["content"] == [TextContent(type="text", text="hi there")]


@pytest.mark.anyio
async def test_stream_fn_request_payload_includes_system_and_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The request kwargs carry the system prompt and tool declarations."""
    fake = _FakeClient([_delta(finish="stop")])
    monkeypatch.setattr("app.core.providers.xai_provider.AsyncOpenAI", lambda **_kwargs: fake)

    async def _execute(_call_id: str, **_kwargs: Any) -> str:
        return ""

    tool = AgentTool(
        name="ping",
        description="ping",
        parameters={"type": "object", "properties": {}},
        execute=_execute,
    )

    stream_fn = make_xai_stream_fn("grok-4.3", None, system_prompt="custom-sys")
    async for _ in stream_fn([UserMessage(role="user", content="hello")], [tool]):
        pass

    kwargs = fake.chat.completions.last_kwargs
    assert kwargs is not None
    assert kwargs["model"] == "grok-4.3"
    assert kwargs["stream"] is True
    assert kwargs["messages"][0] == {"role": "system", "content": "custom-sys"}
    assert kwargs["tools"] is not None
    # Live Search must be disabled by default: pawrrtal uses exa_search
    # as the canonical web tool and we don't want xAI double-billing or
    # ghost-searching every turn.  See ``_LIVE_SEARCH_DISABLED``.
    assert kwargs["extra_body"]["search_parameters"] == {"mode": "off"}
    assert kwargs["tools"][0]["function"]["name"] == "ping"


@pytest.mark.anyio
async def test_stream_fn_surfaces_upstream_error_as_done_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exception raised by the SDK becomes a graceful error ``done`` event."""

    class _ExplodingCompletions:
        async def create(self, **_kwargs: Any) -> Any:
            raise RuntimeError("upstream 503")

    class _ExplodingClient:
        chat = SimpleNamespace(completions=_ExplodingCompletions())

    monkeypatch.setattr(
        "app.core.providers.xai_provider.AsyncOpenAI",
        lambda **_kwargs: _ExplodingClient(),
    )

    stream_fn = make_xai_stream_fn("grok-4.3", None, system_prompt="sys")
    events = [event async for event in stream_fn([], [])]

    text = next(e for e in events if e["type"] == "text_delta")
    done = next(e for e in events if e["type"] == "done")
    assert "upstream 503" in text["text"]
    assert done["stop_reason"] == "error"


def test_xai_base_url_points_at_xai_v1() -> None:
    """Regression guard: ensure we never accidentally hit api.openai.com."""
    assert XAI_BASE_URL == "https://api.x.ai/v1"


def test_provider_class_construction_records_model_and_workspace() -> None:
    """Smoke check the class shape (the chat router constructs the provider)."""
    workspace = uuid4()
    provider = XaiLLM("grok-4.3", workspace_id=workspace)
    # No public getters — assert via private slots since this is an internal contract.
    assert provider._model_id == "grok-4.3"
    assert provider._workspace_id == workspace


@pytest.mark.anyio
async def test_done_assistant_blocks_include_unstreamed_text_and_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMDoneEvent.content lists every text + tool-call block from the turn."""
    chunks = [
        _delta(content="ack"),
        _delta(
            tool_calls=[
                _tc_delta(index=0, tc_id="call-A", name="echo", arguments='{"value":"hi"}'),
            ]
        ),
        _delta(finish="tool_calls"),
    ]
    fake = _FakeClient(chunks)
    monkeypatch.setattr("app.core.providers.xai_provider.AsyncOpenAI", lambda **_kwargs: fake)

    stream_fn = make_xai_stream_fn("grok-4.3", None, system_prompt="sys")
    events = [event async for event in stream_fn([], [])]

    done = next(e for e in events if e["type"] == "done")
    assert isinstance(done, dict)
    # Narrow for the type checker so mypy understands the union shape.
    done_event: LLMDoneEvent = done  # type: ignore[assignment]
    text_blocks = [b for b in done_event["content"] if b["type"] == "text"]
    tool_blocks = [b for b in done_event["content"] if b["type"] == "toolCall"]
    assert [b["text"] for b in text_blocks] == ["ack"]
    assert len(tool_blocks) == 1
    assert tool_blocks[0]["name"] == "echo"
    assert tool_blocks[0]["arguments"] == {"value": "hi"}


# ---------------------------------------------------------------------------
# xAI-specific extensions: reasoning_effort + reasoning_content + Live Search
# ---------------------------------------------------------------------------


def test_map_reasoning_effort_collapses_four_levels_to_two() -> None:
    """Pawrrtal's four-level UI knob → grok-4.3's two-level enum.

    grok-4.3 rejects anything other than ``"low"`` or ``"high"``
    (https://docs.x.ai/docs/models/grok-4-3), so the mapper has to
    collapse ``medium``/``extra-high`` rather than pass them through.
    """
    assert _map_reasoning_effort(None) is None
    assert _map_reasoning_effort("low") == "low"
    assert _map_reasoning_effort("medium") == "low"
    assert _map_reasoning_effort("high") == "high"
    assert _map_reasoning_effort("extra-high") == "high"


def test_build_xai_extra_body_always_disables_live_search() -> None:
    """search_parameters.mode is always ``off`` regardless of effort."""
    assert _build_xai_extra_body(None) == {"search_parameters": {"mode": "off"}}
    assert _build_xai_extra_body("low") == {
        "search_parameters": {"mode": "off"},
        "reasoning_effort": "low",
    }
    assert _build_xai_extra_body("high") == {
        "search_parameters": {"mode": "off"},
        "reasoning_effort": "high",
    }


@pytest.mark.anyio
async def test_stream_fn_forwards_mapped_reasoning_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``reasoning_effort='extra-high'`` lands as ``'high'`` in extra_body."""
    fake = _FakeClient([_delta(finish="stop")])
    monkeypatch.setattr("app.core.providers.xai_provider.AsyncOpenAI", lambda **_kwargs: fake)

    stream_fn = make_xai_stream_fn(
        "grok-4.3", None, system_prompt="sys", reasoning_effort="extra-high"
    )
    async for _ in stream_fn([], []):
        pass

    kwargs = fake.chat.completions.last_kwargs
    assert kwargs is not None
    assert kwargs["extra_body"]["reasoning_effort"] == "high"
    assert kwargs["extra_body"]["search_parameters"] == {"mode": "off"}


@pytest.mark.anyio
async def test_stream_fn_emits_thinking_deltas_from_reasoning_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """xAI's ``delta.reasoning_content`` surfaces as ``thinking_delta`` events.

    Mirrors the Gemini regression test for issue #98 — without this
    wiring the frontend's thinking pane is empty for Grok even though
    grok-4.3 streams its chain-of-thought back on every reasoning turn.
    """
    # ``ChoiceDelta`` has ``extra='allow'``; the openai SDK preserves
    # ``reasoning_content`` on unknown-field deltas via Pydantic.  We
    # mimic that here so the test stays decoupled from the SDK's
    # internal mutation API.
    thinking_chunk = SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=None,
                    tool_calls=None,
                    reasoning_content="Let me think... 2 + 2 = 4.",
                ),
                finish_reason=None,
                index=0,
            )
        ]
    )
    answer_chunk = _delta(content="4", finish="stop")
    fake = _FakeClient([thinking_chunk, answer_chunk])
    monkeypatch.setattr("app.core.providers.xai_provider.AsyncOpenAI", lambda **_kwargs: fake)

    stream_fn = make_xai_stream_fn("grok-4.3", None, system_prompt="sys")
    events = [event async for event in stream_fn([], [])]

    thinking_events = [e for e in events if e["type"] == "thinking_delta"]
    text_events = [e for e in events if e["type"] == "text_delta"]
    assert any("2 + 2 = 4" in e["text"] for e in thinking_events)
    # Reasoning content must NOT bleed into the regular text stream — the
    # frontend renders text_delta in the assistant transcript.
    assert not any("Let me think" in e["text"] for e in text_events)
    assert any(e["text"] == "4" for e in text_events)
