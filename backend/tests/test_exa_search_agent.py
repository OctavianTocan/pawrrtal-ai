"""Tests for the agent-loop Exa web-search adapter.

Coverage:
* ``make_exa_search_tool`` returns a correctly shaped ``AgentTool``.
* ``execute`` calls the exa_search core and formats results as Markdown.
* ``execute`` surfaces API-key-not-configured error as a string (not an
  exception) so the LLM can report gracefully.
* Tool is omitted from the Gemini provider's context when EXA_API_KEY is
  absent, and included when it is present.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.types import AgentTool
from app.tools.exa_search import ExaSearchResult
from app.tools.exa_search_agent import make_exa_search_tool

# ---------------------------------------------------------------------------
# make_exa_search_tool — shape
# ---------------------------------------------------------------------------


class TestMakeExaSearchTool:
    def test_returns_agent_tool(self) -> None:
        tool = make_exa_search_tool()
        assert isinstance(tool, AgentTool)

    def test_name_is_exa_search(self) -> None:
        tool = make_exa_search_tool()
        assert tool.name == "exa_search"

    def test_description_is_non_empty(self) -> None:
        tool = make_exa_search_tool()
        assert isinstance(tool.description, str)
        assert len(tool.description) > 20

    def test_parameters_schema_has_query(self) -> None:
        tool = make_exa_search_tool()
        props = tool.parameters.get("properties", {})
        assert "query" in props

    def test_query_is_required(self) -> None:
        tool = make_exa_search_tool()
        assert "query" in tool.parameters.get("required", [])

    def test_execute_is_callable(self) -> None:

        tool = make_exa_search_tool()
        assert callable(tool.execute)


# ---------------------------------------------------------------------------
# execute — happy path
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestExaSearchToolExecute:
    async def test_execute_calls_core_and_returns_markdown(self) -> None:
        """execute() should delegate to exa_search and format the results."""
        fake_result: ExaSearchResult = {
            "query": "python async",
            "results": [
                {
                    "title": "Real Python: asyncio",
                    "url": "https://realpython.com/async-io-python/",
                    "highlights": ["asyncio is the backbone of async Python"],
                }
            ],
            "error": None,
        }
        tool = make_exa_search_tool()
        with patch(
            "app.tools.exa_search_agent.exa_search",
            new=AsyncMock(return_value=fake_result),
        ):
            result = await tool.execute("dummy-id", query="python async")

        assert isinstance(result, str)
        assert "Real Python" in result
        assert "realpython.com" in result

    async def test_execute_propagates_error_as_string(self) -> None:
        """When the API key is missing the result error surfaces as a string."""
        error_result: ExaSearchResult = {
            "query": "test",
            "results": [],
            "error": "Exa API key is not configured on the server.",
        }
        tool = make_exa_search_tool()
        with patch(
            "app.tools.exa_search_agent.exa_search",
            new=AsyncMock(return_value=error_result),
        ):
            result = await tool.execute("dummy-id", query="test")

        assert isinstance(result, str)
        assert "not configured" in result.lower() or "failed" in result.lower()

    async def test_execute_passes_num_results(self) -> None:
        """num_results kwarg should be forwarded to the core function."""
        mock_search = AsyncMock(return_value={"query": "x", "results": [], "error": None})
        tool = make_exa_search_tool()
        with patch("app.tools.exa_search_agent.exa_search", new=mock_search):
            await tool.execute("dummy-id", query="x", num_results=3)

        mock_search.assert_called_once()
        _, kwargs = mock_search.call_args
        assert kwargs.get("num_results") == 3

    async def test_execute_passes_include_full_text(self) -> None:
        """include_full_text kwarg should be forwarded to the core function."""
        mock_search = AsyncMock(return_value={"query": "x", "results": [], "error": None})
        tool = make_exa_search_tool()
        with patch("app.tools.exa_search_agent.exa_search", new=mock_search):
            await tool.execute("dummy-id", query="x", include_full_text=True)

        _, kwargs = mock_search.call_args
        assert kwargs.get("include_full_text") is True

    async def test_execute_defaults_num_results_to_5(self) -> None:
        """When num_results is not supplied it should default to 5."""
        mock_search = AsyncMock(return_value={"query": "x", "results": [], "error": None})
        tool = make_exa_search_tool()
        with patch("app.tools.exa_search_agent.exa_search", new=mock_search):
            await tool.execute("dummy-id", query="x")

        _, kwargs = mock_search.call_args
        assert kwargs.get("num_results") == 5


# ---------------------------------------------------------------------------
# GeminiLLM wiring — tool list flows through the real run_model_tool_loop unchanged
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestGeminiToolPassthrough:
    """Gemini provider must pass caller-supplied tools through verbatim.

    Tool composition (which tools the agent gets) is the chat router's
    job — the provider is just a translator.  See
    `.claude/rules/architecture/no-tools-in-providers.md`.

    These tests use a *recording* StreamFn and let the real ``run_model_tool_loop``
    run — no ``run_model_tool_loop`` monkeypatching.  This verifies the full path:
    ``provider.stream()`` → ``AgentContext.tools`` → ``StreamFn`` receives
    the tools list, not just that someone set a field somewhere.
    """

    async def test_provider_passes_tools_through_unchanged(self) -> None:
        """Tools supplied by the caller arrive at the StreamFn unmodified."""
        import uuid

        from app.agents.types import AgentMessage
        from app.providers.gemini import GeminiLLM

        in_tools = [make_exa_search_tool()]
        captured_tools: list[AgentTool] | None = None

        async def recording_stream_fn(
            messages: list[AgentMessage], tools: list[AgentTool]
        ) -> AsyncIterator[Any]:
            nonlocal captured_tools
            captured_tools = list(tools)
            # Yield a clean stop so run_model_tool_loop exits immediately.
            from app.agents.types import LLMDoneEvent, TextContent

            yield LLMDoneEvent(
                type="done",
                stop_reason="stop",
                content=[TextContent(type="text", text="")],
            )

        provider = GeminiLLM("gemini-test")
        # Inject our recording StreamFn so no real API calls are made.
        with patch.object(provider, "_stream_fn", recording_stream_fn):
            async for _ in provider.stream(
                "hello",
                uuid.uuid4(),
                uuid.uuid4(),
                history=[],
                tools=in_tools,
            ):
                pass

        assert captured_tools is not None
        assert [t.name for t in captured_tools] == ["exa_search"]

    async def test_provider_does_not_inject_tools_when_caller_passes_none(self) -> None:
        """Provider must NOT inject its own tools when the caller passes none.

        Even if EXA_API_KEY is set in the environment, tool composition is the
        chat router's responsibility — the provider stays tool-agnostic.
        """
        import uuid

        from app.agents.types import AgentMessage
        from app.providers.gemini import GeminiLLM

        captured_tools: list[AgentTool] | None = None

        async def recording_stream_fn(
            messages: list[AgentMessage], tools: list[AgentTool]
        ) -> AsyncIterator[Any]:
            nonlocal captured_tools
            captured_tools = list(tools)
            from app.agents.types import LLMDoneEvent, TextContent

            yield LLMDoneEvent(
                type="done",
                stop_reason="stop",
                content=[TextContent(type="text", text="")],
            )

        provider = GeminiLLM("gemini-test")
        with (
            patch("app.infrastructure.config.settings.exa_api_key", "test-key"),
            patch.object(provider, "_stream_fn", recording_stream_fn),
        ):
            async for _ in provider.stream("hello", uuid.uuid4(), uuid.uuid4(), history=[]):
                pass

        # Even with EXA_API_KEY set, the provider must NOT inject Exa
        # — that's the chat router's job.
        assert captured_tools == []

    async def test_exa_tool_failure_surfaces_as_tool_result_not_exception(self) -> None:
        """An Exa API failure produces a graceful tool_result, not a crash.

        The tool's ``execute()`` returns an error string (never raises) so the
        LLM can respond gracefully rather than the agent loop seeing an
        unexpected exception.
        """
        import uuid

        from app.providers.gemini import GeminiLLM
        from tests.agent_loop_harness import ScriptedStreamFn, text_turn, tool_call_turn

        exa_tool = make_exa_search_tool()

        # Script: LLM calls exa_search, Exa fails (returns error result),
        # then LLM replies with an apology.
        script = ScriptedStreamFn(
            [
                tool_call_turn("exa_search", {"query": "python"}, turn_id="tc-exa"),
                text_turn("I was unable to search right now."),
            ]
        )

        provider = GeminiLLM("gemini-test")
        patch.object(provider, "_stream_fn", script)

        error_result = {
            "query": "python",
            "results": [],
            "error": "Exa API key is not configured on the server.",
        }

        events = []
        with (
            patch(
                "app.tools.exa_search_agent.exa_search",
                new=AsyncMock(return_value=error_result),
            ),
            patch.object(provider, "_stream_fn", script),
        ):
            events.extend(
                [
                    event
                    async for event in provider.stream(
                        "Search for python",
                        uuid.uuid4(),
                        uuid.uuid4(),
                        history=[],
                        tools=[exa_tool],
                    )
                ]
            )

        # The tool error becomes a tool_result event (not an uncaught exception).
        tool_results = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_results) == 1
        # Error text surfaces in the result content so the LLM can see it.
        assert (
            "not configured" in tool_results[0]["content"].lower()
            or "failed" in tool_results[0]["content"].lower()
        )

        # The LLM's graceful reply also arrives.
        delta_events = [e for e in events if e["type"] == "delta"]
        assert any("unable" in e.get("content", "").lower() for e in delta_events)
