"""Regression tests for Gemini manual function-calling translation.

These tests intentionally describe the fixed behavior before the provider
implements it. They protect the SDK contract documented by google-genai:
model function calls must be replayed as model ``function_call`` parts and
tool results must be replayed as tool ``function_response`` parts.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.genai import types as gtypes

from app.core.agent_loop.types import (
    AgentMessage,
    AgentTool,
    AssistantMessage,
    LLMDoneEvent,
    LLMEvent,
    TextContent,
    ToolCallContent,
    ToolResultContent,
    ToolResultMessage,
    UserMessage,
)
from app.core.providers import gemini_provider


async def _execute_noop(tool_call_id: str, **kwargs: object) -> str:
    """Return a deterministic result for tool declaration tests."""
    return f"ok:{tool_call_id}:{len(kwargs)}"


def _make_search_tool() -> AgentTool:
    """Return a minimal AgentTool shaped like a real JSON-schema function."""
    return AgentTool(
        name="exa_search",
        description="Search the web for up-to-date information.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query.",
                },
                "num_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        execute=_execute_noop,
    )


def test_gemini_contents_replay_function_call_and_function_response() -> None:
    """Tool turns must be visible to Gemini on the next model call."""
    messages: list[AgentMessage] = [
        UserMessage(role="user", content="Search the docs."),
        AssistantMessage(
            role="assistant",
            stop_reason="tool_use",
            content=[
                ToolCallContent(
                    type="toolCall",
                    tool_call_id="tc-search",
                    name="exa_search",
                    arguments={"query": "google-genai function calling"},
                )
            ],
        ),
        ToolResultMessage(
            role="toolResult",
            tool_call_id="tc-search",
            name="exa_search",
            content=[
                ToolResultContent(
                    type="text",
                    text="Manual function calling requires a function_response part.",
                )
            ],
            is_error=False,
        ),
    ]

    contents = gemini_provider.build_gemini_contents(messages)

    assert len(contents) == 3
    assert contents[0].role == "user"

    model_content = contents[1]
    assert model_content.role == "model"
    model_parts = model_content.parts or []
    assert len(model_parts) == 1
    function_call = model_parts[0].function_call
    assert function_call is not None
    assert function_call.name == "exa_search"
    assert function_call.args == {"query": "google-genai function calling"}

    tool_content = contents[2]
    assert tool_content.role == "user"
    tool_parts = tool_content.parts or []
    assert len(tool_parts) == 1
    function_response = tool_parts[0].function_response
    assert function_response is not None
    assert function_response.name == "exa_search"
    assert function_response.response == {
        "result": "Manual function calling requires a function_response part."
    }


def test_gemini_contents_preserve_text_and_function_call_parts() -> None:
    """Assistant text and tool calls from one turn must stay in order."""
    messages: list[AgentMessage] = [
        AssistantMessage(
            role="assistant",
            stop_reason="tool_use",
            content=[
                TextContent(type="text", text="I need to search first."),
                ToolCallContent(
                    type="toolCall",
                    tool_call_id="tc-search",
                    name="exa_search",
                    arguments={"query": "Gemini tool response format"},
                ),
            ],
        )
    ]

    contents = gemini_provider.build_gemini_contents(messages)

    assert len(contents) == 1
    assert contents[0].role == "model"
    parts = contents[0].parts or []
    assert len(parts) == 2
    assert parts[0].text == "I need to search first."
    assert parts[1].function_call is not None
    assert parts[1].function_call.name == "exa_search"


def test_gemini_tool_declarations_use_parameters_json_schema() -> None:
    """Function declarations should pass raw JSON Schema to google-genai."""
    gemini_tools = gemini_provider.build_gemini_tool_declarations([_make_search_tool()])

    assert gemini_tools is not None
    declarations = gemini_tools[0].function_declarations or []
    assert len(declarations) == 1
    declaration_dump = declarations[0].model_dump(exclude_none=True)
    assert "parameters_json_schema" in declaration_dump
    assert declaration_dump["parameters_json_schema"] == _make_search_tool().parameters
    assert "parameters" not in declaration_dump


class _EmptyGeminiStream:
    """Async iterator with no chunks, used to inspect stream config."""

    def __aiter__(self) -> _EmptyGeminiStream:
        return self

    async def __anext__(self) -> object:
        raise StopAsyncIteration


class _CapturingModels:
    """Fake ``client.aio.models`` that records the generated config."""

    def __init__(self) -> None:
        self.configs: list[gtypes.GenerateContentConfig] = []

    async def generate_content_stream(
        self,
        *,
        model: str,
        contents: list[gtypes.Content],
        config: gtypes.GenerateContentConfig,
    ) -> _EmptyGeminiStream:
        self.configs.append(config)
        return _EmptyGeminiStream()


@pytest.mark.anyio
async def test_stream_config_disables_sdk_automatic_function_calling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pawrrtal's agent loop must own tool execution, not the SDK."""
    captured_models = _CapturingModels()

    class CapturingClient:
        """Fake Gemini client that exposes the async model surface."""

        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key
            self.aio = SimpleNamespace(models=captured_models)

    monkeypatch.setattr(gemini_provider.genai, "Client", CapturingClient)
    monkeypatch.setattr(gemini_provider, "resolve_gemini_api_key", lambda _user_id: "test-key")

    stream_fn = gemini_provider.make_gemini_stream_fn(
        "gemini-test",
        system_prompt="test-prompt",
    )
    events: list[LLMEvent] = [
        event
        async for event in stream_fn(
            [UserMessage(role="user", content="Search the docs.")],
            [_make_search_tool()],
        )
    ]

    assert events == [
        LLMDoneEvent(type="done", stop_reason="stop", content=[]),
    ]
    assert len(captured_models.configs) == 1
    automatic_function_calling = captured_models.configs[0].automatic_function_calling
    assert automatic_function_calling is not None
    assert automatic_function_calling.disable is True


@pytest.mark.anyio
async def test_stream_threads_system_prompt_into_gemini_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The factory-captured ``system_prompt`` lands on ``GenerateContentConfig.system_instruction``.

    ``GeminiLLM.stream()`` builds a fresh StreamFn per request via
    ``make_gemini_stream_fn(..., system_prompt=context.system_prompt)`` so the
    workspace-assembled prompt (SOUL.md + AGENTS.md + CLAUDE.md + skills) is
    baked into the closure and reaches the SDK.  If this wiring breaks, the
    model silently runs on the bare provider fallback and the workspace
    identity is lost — so this test asserts on the SDK-bound value, not just
    the call shape.
    """
    captured_models = _CapturingModels()

    class CapturingClient:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key
            self.aio = SimpleNamespace(models=captured_models)

    monkeypatch.setattr(gemini_provider.genai, "Client", CapturingClient)
    monkeypatch.setattr(gemini_provider, "resolve_gemini_api_key", lambda _user_id: "test-key")

    workspace_prompt = "You are PAWRRTAL, the assistant for octavian's workspace."
    stream_fn = gemini_provider.make_gemini_stream_fn(
        "gemini-test",
        system_prompt=workspace_prompt,
    )
    async for _ in stream_fn(
        [UserMessage(role="user", content="hi")],
        [],
    ):
        pass

    assert len(captured_models.configs) == 1
    assert captured_models.configs[0].system_instruction == workspace_prompt
