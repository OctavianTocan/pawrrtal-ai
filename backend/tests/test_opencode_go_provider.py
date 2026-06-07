"""Tests for the OpenCode Go provider.

Mirrors the shape of ``test_gemini_stream_fn.py``: every agent-loop
behaviour is exercised through ``ScriptedStreamFn`` so the real loop
runs end-to-end and we only replace the LLM at its seam. The pure
helpers in ``_opencode_go_events`` and the catalogue-driven factory
branch are covered with direct unit tests.

No live HTTP — the AsyncOpenAI client is never constructed in any test
in this module.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from app.agents.types import AgentMessage, AgentTool
from app.providers.base import StreamEvent
from app.providers.catalog import find
from app.providers.factory import resolve_llm
from app.providers.model_id import Host, Vendor, parse_model_id
from app.providers.opencode_go.events import (
    ToolCallBuffer,
    _UsageAccumulator,
    build_openai_messages,
    build_openai_tools,
    compute_cost_usd,
    read_reasoning,
)
from app.providers.opencode_go.provider import (
    OpencodeGoLLM,
    OpencodeGoLLMConfig,
)
from tests.agent_loop_harness import (
    ScriptedStreamFn,
    text_turn,
    thinking_then_text_turn,
    tool_call_turn,
)

# OpenCode Go runs on subscription pricing (per
# https://opencode.ai/docs/go/), so the catalogue exposes 0.0 for all
# per-token rates ("unknown — skip cost accounting"). These constants
# are kept locally for the cost-arithmetic helpers below so we can still
# verify the pure compute_cost_usd math without depending on catalogue
# values.
_GLM_IN_USD = 1.4
_GLM_OUT_USD = 4.4


def _make_provider() -> OpencodeGoLLM:
    """Construct an ``OpencodeGoLLM`` with an arbitrary cost profile."""
    return OpencodeGoLLM(
        "glm-5.1",
        config=OpencodeGoLLMConfig(
            cost_per_mtok_in_usd=_GLM_IN_USD,
            cost_per_mtok_out_usd=_GLM_OUT_USD,
        ),
    )


# ---------------------------------------------------------------------------
# Helper unit tests — pure functions in _opencode_go_events
# ---------------------------------------------------------------------------


def test_read_reasoning_handles_typed_field_and_extra_dict() -> None:
    """``reasoning_content`` is read from the typed attr OR pydantic extras."""
    typed = SimpleNamespace(reasoning_content="step one", model_extra={})
    assert read_reasoning(typed) == "step one"

    extras_only = SimpleNamespace(
        reasoning_content=None, model_extra={"reasoning_content": "step two"}
    )
    assert read_reasoning(extras_only) == "step two"

    nothing = SimpleNamespace(reasoning_content=None, model_extra={})
    assert read_reasoning(nothing) == ""


def test_tool_call_buffer_accumulates_and_parses_arguments() -> None:
    """Streamed tool-call fragments concatenate and JSON-parse on finalize."""
    buffer = ToolCallBuffer()
    buffer.append(
        [
            SimpleNamespace(
                index=0,
                id="tc-abc",
                function=SimpleNamespace(name="search", arguments='{"query": "py'),
            )
        ]
    )
    buffer.append(
        [
            SimpleNamespace(
                index=0,
                id=None,
                function=SimpleNamespace(name=None, arguments='thon"}'),
            )
        ]
    )
    calls = buffer.finalize()
    assert calls == [
        {
            "tool_call_id": "tc-abc",
            "name": "search",
            "arguments": {"query": "python"},
        }
    ]


def test_tool_call_buffer_orders_calls_by_index() -> None:
    """Calls are emitted in ascending ``index`` order regardless of arrival order."""
    buffer = ToolCallBuffer()
    buffer.append(
        [
            SimpleNamespace(
                index=1,
                id="tc-1",
                function=SimpleNamespace(name="b", arguments="{}"),
            ),
            SimpleNamespace(
                index=0,
                id="tc-0",
                function=SimpleNamespace(name="a", arguments="{}"),
            ),
        ]
    )
    calls = buffer.finalize()
    assert [c["tool_call_id"] for c in calls] == ["tc-0", "tc-1"]


def test_tool_call_buffer_downgrades_invalid_json_to_raw() -> None:
    """Malformed argument JSON does not raise — it surfaces as ``{"_raw": ...}``."""
    buffer = ToolCallBuffer()
    buffer.append(
        [
            SimpleNamespace(
                index=0,
                id="tc-bad",
                function=SimpleNamespace(name="x", arguments="not json"),
            )
        ]
    )
    calls = buffer.finalize()
    assert calls[0]["arguments"] == {"_raw": "not json"}


def test_build_openai_tools_returns_none_for_empty_list() -> None:
    """An empty tool list maps to ``None`` so the request omits ``tools``."""
    assert build_openai_tools([]) is None


def test_build_openai_tools_emits_function_shape() -> None:
    """``AgentTool`` is rendered as OpenAI's ``{"type": "function", ...}`` shape."""

    async def _execute(tool_call_id: str, **kwargs: object) -> str:
        return ""

    tool = AgentTool(
        name="echo",
        description="Echo a value",
        parameters={"type": "object", "properties": {"v": {"type": "string"}}},
        execute=_execute,
    )
    rendered = build_openai_tools([tool])
    assert rendered == [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo a value",
                "parameters": {
                    "type": "object",
                    "properties": {"v": {"type": "string"}},
                },
            },
        }
    ]


def test_build_openai_messages_prepends_system_and_renders_all_roles() -> None:
    """User / assistant (text + tool-call) / tool-result roles round-trip."""
    from app.agents.types import (
        AssistantMessage,
        TextContent,
        ToolCallContent,
        ToolResultContent,
        ToolResultMessage,
        UserMessage,
    )

    history = [
        UserMessage(role="user", content="hi"),
        AssistantMessage(
            role="assistant",
            content=[
                TextContent(type="text", text="thinking…"),
                ToolCallContent(
                    type="toolCall",
                    tool_call_id="tc-0",
                    name="search",
                    arguments={"q": "foo"},
                ),
            ],
            stop_reason="tool_use",
        ),
        ToolResultMessage(
            role="toolResult",
            tool_call_id="tc-0",
            name="search",
            content=[ToolResultContent(type="text", text="found bar")],
            is_error=False,
        ),
    ]

    # mypy infers the heterogeneous TypedDict list as the empty TypedDict union;
    # cast back to the AgentMessage union the function expects.
    rendered = build_openai_messages(
        system_prompt="be helpful",
        messages=cast("list[AgentMessage]", history),
    )

    assert rendered[0] == {"role": "system", "content": "be helpful"}
    assert rendered[1] == {"role": "user", "content": "hi"}
    assert rendered[2]["role"] == "assistant"
    assert rendered[2]["content"] == "thinking…"
    assert rendered[2]["tool_calls"][0]["id"] == "tc-0"
    assert json.loads(rendered[2]["tool_calls"][0]["function"]["arguments"]) == {"q": "foo"}
    assert rendered[3] == {
        "role": "tool",
        "tool_call_id": "tc-0",
        "name": "search",
        "content": "found bar",
    }


def test_compute_cost_usd_matches_catalogue_arithmetic() -> None:
    """``compute_cost_usd`` is exactly (tokens * rate) / 1e6 for each direction."""
    cost = compute_cost_usd(
        input_tokens=1_000_000,
        output_tokens=500_000,
        cost_per_mtok_in_usd=_GLM_IN_USD,
        cost_per_mtok_out_usd=_GLM_OUT_USD,
    )
    expected = (1_000_000 * _GLM_IN_USD + 500_000 * _GLM_OUT_USD) / 1_000_000
    assert cost == pytest.approx(expected)


def test_usage_accumulator_ignores_none_payloads() -> None:
    """``None`` token counts are no-ops so a quiet stream stays at 0/0."""
    acc = _UsageAccumulator()
    acc.add(prompt_tokens=None, completion_tokens=None)
    assert acc.input_tokens == 0
    assert acc.output_tokens == 0

    acc.add(prompt_tokens=12, completion_tokens=34)
    acc.add(prompt_tokens=None, completion_tokens=6)
    assert acc.input_tokens == 12
    assert acc.output_tokens == 40


# ---------------------------------------------------------------------------
# Factory / catalogue wiring — confirms the new entries plug in cleanly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("wire_id", "expected_vendor", "expected_model"),
    [
        ("opencode-go:zai/glm-5.1", Vendor.zai, "glm-5.1"),
        ("opencode-go:moonshot/kimi-k2.6", Vendor.moonshot, "kimi-k2.6"),
    ],
)
def test_catalogue_contains_opencode_go_entries(
    wire_id: str,
    expected_vendor: Vendor,
    expected_model: str,
) -> None:
    """Both GLM-5.1 and Kimi K2.6 round-trip through parse + catalogue lookup."""
    parsed = parse_model_id(wire_id)
    assert parsed.host is Host.opencode_go
    assert parsed.vendor is expected_vendor
    assert parsed.model == expected_model

    entry = find(parsed)
    assert entry is not None
    # OpenCode Go uses subscription pricing — every catalogue entry
    # reports 0.0 ("skip cost accounting") for per-token rates.
    assert entry.cost_per_mtok_in_usd == 0.0
    assert entry.cost_per_mtok_out_usd == 0.0


def test_resolve_llm_returns_opencodego_with_catalog_costs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Factory builds an ``OpencodeGoLLM`` whose config mirrors the catalogue rates."""
    # Ensure the gateway URL comes from settings (default value).
    provider = resolve_llm("opencode-go:zai/glm-5.1")
    assert isinstance(provider, OpencodeGoLLM)
    assert provider._config.cost_per_mtok_in_usd == 0.0
    assert provider._config.cost_per_mtok_out_usd == 0.0
    assert provider._config.base_url == "https://opencode.ai/zen/go/v1"


# ---------------------------------------------------------------------------
# Provider behaviour — driven through ScriptedStreamFn at the StreamFn seam
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_opencode_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a dummy API key so the fail-fast guard does not short-circuit."""
    from app.infrastructure.config import settings as _settings

    monkeypatch.setattr(_settings, "opencode_api_key", "test-key")


@pytest.mark.anyio
async def test_provider_yields_delta_events_from_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OpencodeGoLLM.stream`` translates run_model_tool_loop text deltas to ``delta`` SSE events."""
    provider = _make_provider()
    script = ScriptedStreamFn([text_turn("hello world")])
    monkeypatch.setattr(provider, "_stream_fn", script)

    events: list[StreamEvent] = [
        event
        async for event in provider.stream(
            question="hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
        )
    ]

    deltas = [e for e in events if e["type"] == "delta"]
    assert any("hello world" in e.get("content", "") for e in deltas)
    assert script.call_count == 1


@pytest.mark.anyio
async def test_provider_translates_thinking_deltas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reasoning chunks surface as ``thinking`` StreamEvents, separately from text."""
    provider = _make_provider()
    script = ScriptedStreamFn([thinking_then_text_turn("reasoning…", "answer")])
    monkeypatch.setattr(provider, "_stream_fn", script)

    events: list[StreamEvent] = [
        event
        async for event in provider.stream(
            question="hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
        )
    ]

    assert any(e["type"] == "thinking" and e.get("content") == "reasoning…" for e in events)
    assert any(e["type"] == "delta" and e.get("content") == "answer" for e in events)
    assert script.call_count == 1


@pytest.mark.anyio
async def test_provider_dispatches_tool_calls_through_real_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scripted tool call dispatches to the supplied ``AgentTool`` and emits result events."""
    provider = _make_provider()
    executed: list[str] = []

    async def echo_execute(tool_call_id: str, **kwargs: object) -> str:
        executed.append(str(kwargs.get("value", "")))
        return f"echoed: {kwargs.get('value', '')}"

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
    script = ScriptedStreamFn(
        [
            tool_call_turn("echo", {"value": "hi"}, turn_id="tc-0"),
            text_turn("done"),
        ]
    )
    monkeypatch.setattr(provider, "_stream_fn", script)

    events: list[StreamEvent] = [
        event
        async for event in provider.stream(
            question="echo hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
            tools=[echo],
        )
    ]

    assert executed == ["hi"]
    assert script.call_count == 2
    assert any(e["type"] == "tool_use" for e in events)
    assert any(e["type"] == "tool_result" for e in events)
    assert any(e["type"] == "delta" and "done" in e.get("content", "") for e in events)


@pytest.mark.anyio
async def test_provider_passes_history_to_stream_fn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prior messages reach the ``StreamFn`` so the model sees full context."""
    provider = _make_provider()
    script = ScriptedStreamFn([text_turn("ok")])
    monkeypatch.setattr(provider, "_stream_fn", script)

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

    # 2 history messages + the new question = 3 user-visible messages.
    assert script.call_count == 1
    assert len(script.messages_seen[0]) == 3
