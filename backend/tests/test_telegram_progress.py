"""Tests for telegram_progress.py — multi-state progress emoji renderers
and per-tool success/failure with timing.

Covers (Workstreams 3 and 4):
- render_initial, render_starting, render_working, render_tools_in_flight
- render_tool_success, render_tool_error
- Preview truncated to PREVIEW_MAX_CHARS chars + ellipsis
- HTML special chars escaped in model name and preview
- Tool error message truncated to TOOL_ERROR_MAX_CHARS + ellipsis
- handle_tool_use populates tool_states dict
- handle_tool_result updates line to success with timing
- handle_tool_result updates line to error with truncated escaped message
- Multiple tools render in order
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.channels.telegram.dispatch import (
    ToolLineState,
    handle_tool_progress,
    handle_tool_result,
    handle_tool_use,
)
from app.channels.telegram.progress import (
    PREVIEW_MAX_CHARS,
    TOOL_ERROR_MAX_CHARS,
    render_initial,
    render_starting,
    render_tool_error,
    render_tool_success,
    render_tools_in_flight,
    render_transient_status,
    render_working,
)
from app.providers.base import StreamEvent

# ---------------------------------------------------------------------------
# Static renderers
# ---------------------------------------------------------------------------


class TestRenderInitial:
    def test_returns_non_empty(self) -> None:
        result = render_initial()
        assert result
        assert isinstance(result, str)

    def test_contains_expected_content(self) -> None:
        result = render_initial()
        assert "Processing" in result or "🤔" in result


class TestRenderTransientStatus:
    def test_status_is_escaped(self) -> None:
        result = render_transient_status("<starting>")
        assert "<starting>" not in result
        assert "&lt;starting&gt;" in result


class TestRenderStarting:
    def test_contains_model_name(self) -> None:
        result = render_starting("claude-sonnet-4-6", 5)
        assert "claude-sonnet-4-6" in result

    def test_tool_count_singular(self) -> None:
        result = render_starting("gpt-4o", 1)
        assert "1 tool available" in result

    def test_tool_count_plural(self) -> None:
        result = render_starting("gpt-4o", 3)
        assert "3 tools available" in result

    def test_zero_tools_no_tools_clause(self) -> None:
        result = render_starting("gpt-4o", 0)
        assert "tool" not in result

    def test_model_name_html_escaped(self) -> None:
        result = render_starting("<bad>", 2)
        assert "<bad>" not in result
        assert "&lt;" in result

    def test_rocket_emoji_present(self) -> None:
        assert "🚀" in render_starting("any", 3)


class TestRenderWorking:
    def test_contains_preview_text(self) -> None:
        result = render_working("Hello world")
        assert "Hello world" in result

    def test_preview_truncated_at_limit(self) -> None:
        long_text = "a" * (PREVIEW_MAX_CHARS + 50)
        result = render_working(long_text)
        assert "…" in result
        # The truncated text should fit within budget
        # (heading + tags around it, but the 'a' sequence is trimmed)
        assert "a" * (PREVIEW_MAX_CHARS + 1) not in result

    def test_preview_not_truncated_when_under_limit(self) -> None:
        text = "a" * PREVIEW_MAX_CHARS
        result = render_working(text)
        assert "…" not in result

    def test_html_special_chars_escaped(self) -> None:
        result = render_working("<script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;" in result

    def test_robot_emoji_present(self) -> None:
        assert "🤖" in render_working("test")


class TestRenderToolsInFlight:
    def test_single_tool(self) -> None:
        result = render_tools_in_flight(["read_file"])
        assert "read_file" in result
        assert "🔧" in result

    def test_multiple_tools(self) -> None:
        result = render_tools_in_flight(["tool_a", "tool_b"])
        assert "tool_a" in result
        assert "tool_b" in result

    def test_empty_list_generic_message(self) -> None:
        result = render_tools_in_flight([])
        assert "🔧" in result


class TestRenderToolSuccess:
    def test_contains_tool_display(self) -> None:
        result = render_tool_success("read_file", 123)
        assert "read_file" in result

    def test_contains_elapsed(self) -> None:
        result = render_tool_success("search", 456)
        assert "456ms" in result

    def test_check_emoji(self) -> None:
        assert "✅" in render_tool_success("anything", 1)

    def test_html_escaped(self) -> None:
        result = render_tool_success("<b>bold</b>", 10)
        # The display value is escaped in the card
        assert "<b>bold</b>" not in result or "&lt;b&gt;" in result


class TestRenderToolError:
    def test_contains_tool_display(self) -> None:
        result = render_tool_error("exa_search", "API key invalid")
        assert "exa_search" in result

    def test_contains_error_message(self) -> None:
        result = render_tool_error("exa_search", "API key invalid")
        assert "API key invalid" in result

    def test_x_emoji(self) -> None:
        assert "❌" in render_tool_error("tool", "err")

    def test_error_truncated(self) -> None:
        long_error = "x" * (TOOL_ERROR_MAX_CHARS + 50)
        result = render_tool_error("tool", long_error)
        assert "…" in result
        assert "x" * (TOOL_ERROR_MAX_CHARS + 1) not in result

    def test_html_escaped(self) -> None:
        result = render_tool_error("tool", "<script>bad</script>")
        assert "<script>" not in result


# ---------------------------------------------------------------------------
# handle_tool_use — state tracking
# ---------------------------------------------------------------------------


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=888))
    return bot


@pytest.mark.anyio
class TestHandleToolUseStateTracking:
    async def test_populates_tool_states(self) -> None:
        bot = _make_bot()
        event: StreamEvent = {
            "type": "tool_use",
            "tool_use_id": "call_abc",
            "name": "read_file",
            "input": {"path": "README.md"},
        }
        tool_states: dict[str, ToolLineState] = {}
        await handle_tool_use(
            event=event,
            bot=bot,
            chat_id=1,
            message_id=10,
            tool_trace="",
            chars_since_edit=0,
            last_edit_at=0.0,
            tool_states=tool_states,
        )
        assert "call_abc" in tool_states
        state = tool_states["call_abc"]
        assert state.call_id == "call_abc"
        assert isinstance(state.started_at, float)
        assert state.result_line is None

    async def test_multiple_tools_render_in_order(self) -> None:
        bot = _make_bot()
        tool_states: dict[str, ToolLineState] = {}
        for i in range(3):
            event: StreamEvent = {
                "type": "tool_use",
                "tool_use_id": f"call_{i}",
                "name": f"tool_{i}",
                "input": {},
            }
            _trace, _, _ = await handle_tool_use(
                event=event,
                bot=bot,
                chat_id=1,
                message_id=10,
                tool_trace="",
                chars_since_edit=0,
                last_edit_at=0.0,
                tool_states=tool_states,
            )
        # All three call IDs are tracked
        assert len(tool_states) == 3
        assert all(f"call_{i}" in tool_states for i in range(3))

    async def test_no_tool_states_falls_back_to_legacy_trace(self) -> None:
        """When tool_states is None the old concatenation path is used."""
        bot = _make_bot()
        event: StreamEvent = {
            "type": "tool_use",
            "tool_use_id": "call_x",
            "name": "read_file",
            "input": {"path": "a.txt"},
        }
        trace, _, _ = await handle_tool_use(
            event=event,
            bot=bot,
            chat_id=1,
            message_id=10,
            tool_trace="prev_line",
            chars_since_edit=0,
            last_edit_at=0.0,
            tool_states=None,
        )
        assert "prev_line" in trace


# ---------------------------------------------------------------------------
# handle_tool_result — success and error paths
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestHandleToolResult:
    def _make_state(self, call_id: str, display: str = "read_file") -> ToolLineState:
        state = ToolLineState(call_id=call_id, display=display)
        # Back-date start so elapsed is non-zero
        state.started_at = time.monotonic() - 0.5
        return state

    async def test_success_result_updates_line(self) -> None:
        bot = _make_bot()
        tool_states = {"call_1": self._make_state("call_1", "read_file")}
        event: StreamEvent = {
            "type": "tool_result",
            "tool_use_id": "call_1",
            "content": "file contents here",
            "is_error": False,
        }
        await handle_tool_result(
            event=event,
            bot=bot,
            chat_id=1,
            message_id=10,
            tool_trace="",
            chars_since_edit=0,
            last_edit_at=0.0,
            tool_states=tool_states,
        )
        state = tool_states["call_1"]
        assert state.result_line is not None
        assert "✅" in state.result_line
        assert "ms" in state.result_line

    async def test_error_result_updates_line(self) -> None:
        bot = _make_bot()
        tool_states = {"call_2": self._make_state("call_2", "exa_search")}
        event: StreamEvent = {
            "type": "tool_result",
            "tool_use_id": "call_2",
            "content": "API key expired",
            "is_error": True,
        }
        await handle_tool_result(
            event=event,
            bot=bot,
            chat_id=1,
            message_id=10,
            tool_trace="",
            chars_since_edit=0,
            last_edit_at=0.0,
            tool_states=tool_states,
        )
        state = tool_states["call_2"]
        assert state.result_line is not None
        assert "❌" in state.result_line
        assert "API key expired" in state.result_line

    async def test_error_message_truncated(self) -> None:
        bot = _make_bot()
        tool_states = {"call_3": self._make_state("call_3")}
        long_msg = "e" * (TOOL_ERROR_MAX_CHARS + 100)
        event: StreamEvent = {
            "type": "tool_result",
            "tool_use_id": "call_3",
            "content": long_msg,
            "is_error": True,
        }
        await handle_tool_result(
            event=event,
            bot=bot,
            chat_id=1,
            message_id=10,
            tool_trace="",
            chars_since_edit=0,
            last_edit_at=0.0,
            tool_states=tool_states,
        )
        state = tool_states["call_3"]
        assert state.result_line is not None
        assert "…" in state.result_line
        assert "e" * (TOOL_ERROR_MAX_CHARS + 1) not in state.result_line

    async def test_unknown_call_id_leaves_trace_unchanged(self) -> None:
        bot = _make_bot()
        tool_states: dict[str, ToolLineState] = {}
        event: StreamEvent = {
            "type": "tool_result",
            "tool_use_id": "no_such_id",
            "content": "whatever",
        }
        trace, _, _ = await handle_tool_result(
            event=event,
            bot=bot,
            chat_id=1,
            message_id=10,
            tool_trace="existing_trace",
            chars_since_edit=5,
            last_edit_at=1.0,
            tool_states=tool_states,
        )
        assert trace == "existing_trace"
        bot.edit_message_text.assert_not_called()

    async def test_result_triggers_immediate_edit(self) -> None:
        """tool_result should force an immediate edit without debounce."""
        bot = _make_bot()
        tool_states = {"call_4": self._make_state("call_4")}
        event: StreamEvent = {
            "type": "tool_result",
            "tool_use_id": "call_4",
            "content": "ok",
            "is_error": False,
        }
        await handle_tool_result(
            event=event,
            bot=bot,
            chat_id=5,
            message_id=20,
            tool_trace="",
            chars_since_edit=0,
            last_edit_at=0.0,
            tool_states=tool_states,
        )
        bot.edit_message_text.assert_awaited_once()
        call_kwargs = bot.edit_message_text.await_args.kwargs
        assert call_kwargs["chat_id"] == 5
        assert call_kwargs["message_id"] == 20


@pytest.mark.anyio
class TestHandleToolProgress:
    def _make_state(self, call_id: str, display: str = "read_file") -> ToolLineState:
        return ToolLineState(call_id=call_id, display=display)

    async def test_progress_updates_preview_without_completing_tool(self) -> None:
        bot = _make_bot()
        tool_states = {"call_1": self._make_state("call_1", "run tests")}
        trace, _, _ = await handle_tool_progress(
            event={
                "type": "tool_progress",
                "tool_use_id": "call_1",
                "content": "collected 12 items",
            },
            bot=bot,
            chat_id=1,
            message_id=10,
            tool_trace="",
            chars_since_edit=40,
            last_edit_at=0.0,
            tool_states=tool_states,
        )

        state = tool_states["call_1"]
        assert state.result_line is None
        assert state.progress_line is not None
        assert "collected 12 items" in state.progress_line
        assert "✅" not in state.progress_line
        assert "collected 12 items" in trace
        bot.edit_message_text.assert_awaited_once()

    async def test_large_tool_trace_omits_complete_fragments_without_cutting_html(self) -> None:
        bot = _make_bot()
        tool_states = {f"call_{i}": self._make_state(f"call_{i}", f"tool_{i}") for i in range(12)}
        for state in tool_states.values():
            state.progress_line = f"⏳ <b>{state.display}</b>\n\n<code>{'x' * 600}</code>"

        trace, _, _ = await handle_tool_progress(
            event={
                "type": "tool_progress",
                "tool_use_id": "call_0",
                "content": "still running",
            },
            bot=bot,
            chat_id=1,
            message_id=10,
            tool_trace="",
            chars_since_edit=40,
            last_edit_at=0.0,
            tool_states=tool_states,
        )

        assert len(trace) <= 3600
        assert trace.count("<code>") == trace.count("</code>")
        assert "omitted" in trace
