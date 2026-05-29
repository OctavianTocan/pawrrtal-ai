"""End-to-end test of the agent-loop permission seam (PR 03b wire-up).

Uses :class:`ScriptedStreamFn` per
``.claude/rules/testing/agent-loop-testing-philosophy.md`` so the real
loop, the real tool dispatch, and the real permission gate all execute.
Only the LLM is replaced with a deterministic script.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.types import AgentTool, PermissionCheckResult
from tests.agent_harness import (
    ScriptedStreamFn,
    echo_tool,
    run_scenario,
    tool_call_turn,
)

pytestmark = pytest.mark.anyio


async def _allow_all(tool_name: str, arguments: dict[str, Any]) -> PermissionCheckResult:
    """Permission gate that allows every call."""
    _ = tool_name, arguments
    return PermissionCheckResult(allow=True, reason=None, violation_type=None)


async def _deny_all(tool_name: str, arguments: dict[str, Any]) -> PermissionCheckResult:
    """Permission gate that denies every call."""
    _ = tool_name, arguments
    return PermissionCheckResult(
        allow=False,
        reason="denied by test",
        violation_type="test_violation",
    )


async def _crash(_tool_name: str, _arguments: dict[str, Any]) -> PermissionCheckResult:
    """Permission gate that raises — verifies fail-closed semantics."""
    raise RuntimeError("policy crashed")


class TestPermissionGateLoop:
    async def test_no_gate_keeps_existing_behaviour(self) -> None:
        """Without a permission_check, tools execute normally."""
        script = ScriptedStreamFn(
            [
                tool_call_turn("echo", {"text": "hello"}),
                # Second turn ends the loop with plain text.
                [
                    {"type": "text_delta", "text": "ok"},
                    {
                        "type": "done",
                        "stop_reason": "stop",
                        "content": [{"type": "text", "text": "ok"}],
                    },
                ],
            ]
        )
        events = await run_scenario(script, tools=[echo_tool()])
        assert script.call_count == 2
        results = [e for e in events if e["type"] == "tool_result"]
        assert len(results) == 1
        assert results[0]["is_error"] is False

    async def test_allow_all_passes_through(self) -> None:
        """A permissive gate runs the tool exactly as the no-gate path would."""
        script = ScriptedStreamFn(
            [
                tool_call_turn("echo", {"text": "ok"}),
                [
                    {"type": "text_delta", "text": "done"},
                    {
                        "type": "done",
                        "stop_reason": "stop",
                        "content": [{"type": "text", "text": "done"}],
                    },
                ],
            ]
        )
        events = await run_scenario(script, tools=[echo_tool()], permission_check=_allow_all)
        assert script.call_count == 2
        results = [e for e in events if e["type"] == "tool_result"]
        assert len(results) == 1
        assert results[0]["is_error"] is False

    async def test_deny_short_circuits_tool_execute(self) -> None:
        """A denial surfaces as an error tool_result and the tool's body never runs."""
        executed: list[dict[str, Any]] = []

        async def _spy_execute(_tool_call_id: str, **kwargs: object) -> str:
            executed.append(dict(kwargs))
            return "should not happen"

        spy_tool = AgentTool(
            name="spy",
            description="spy tool",
            parameters={"type": "object", "properties": {}, "required": []},
            execute=_spy_execute,
        )

        script = ScriptedStreamFn(
            [
                tool_call_turn("spy", {"x": 1}),
                # The loop continues to the next turn after the tool result.
                [
                    {"type": "text_delta", "text": "fallback"},
                    {
                        "type": "done",
                        "stop_reason": "stop",
                        "content": [{"type": "text", "text": "fallback"}],
                    },
                ],
            ]
        )
        events = await run_scenario(script, tools=[spy_tool], permission_check=_deny_all)
        # Tool body never ran.
        assert executed == []
        # The denial surfaced as a tool_result event with is_error.
        results = [e for e in events if e["type"] == "tool_result"]
        assert len(results) == 1
        assert results[0]["is_error"] is True
        assert "denied by test" in results[0]["content"]

    async def test_crash_in_gate_fails_closed(self) -> None:
        """A crashing gate denies the call (fail-closed) instead of allowing it."""
        executed: list[dict[str, Any]] = []

        async def _spy_execute(_tool_call_id: str, **kwargs: object) -> str:
            executed.append(dict(kwargs))
            return "should not happen"

        spy_tool = AgentTool(
            name="spy",
            description="spy tool",
            parameters={"type": "object", "properties": {}, "required": []},
            execute=_spy_execute,
        )

        script = ScriptedStreamFn(
            [
                tool_call_turn("spy", {"x": 1}),
                [
                    {"type": "text_delta", "text": "after-crash"},
                    {
                        "type": "done",
                        "stop_reason": "stop",
                        "content": [{"type": "text", "text": "after-crash"}],
                    },
                ],
            ]
        )
        events = await run_scenario(script, tools=[spy_tool], permission_check=_crash)
        assert executed == []
        results = [e for e in events if e["type"] == "tool_result"]
        assert len(results) == 1
        assert results[0]["is_error"] is True
        assert "permission check error" in results[0]["content"]

    async def test_audit_sink_called_on_denial(self) -> None:
        """A denial fires the optional audit sink with (name, args, decision)."""
        sink_calls: list[tuple[str, dict[str, Any], PermissionCheckResult]] = []

        async def sink(name: str, args: dict[str, Any], decision: PermissionCheckResult) -> None:
            sink_calls.append((name, args, decision))

        script = ScriptedStreamFn(
            [
                tool_call_turn("echo", {"text": "blocked"}),
                [
                    {"type": "text_delta", "text": "ok"},
                    {
                        "type": "done",
                        "stop_reason": "stop",
                        "content": [{"type": "text", "text": "ok"}],
                    },
                ],
            ]
        )
        await run_scenario(
            script,
            tools=[echo_tool()],
            permission_check=_deny_all,
            permission_audit_sink=sink,
        )
        assert len(sink_calls) == 1
        name, args, decision = sink_calls[0]
        assert name == "echo"
        assert args == {"text": "blocked"}
        assert decision["allow"] is False

    async def test_audit_sink_failure_is_swallowed(self) -> None:
        """An exception from the audit sink must never break the turn."""

        async def crashing_sink(
            _name: str, _args: dict[str, Any], _decision: PermissionCheckResult
        ) -> None:
            raise RuntimeError("sink boom")

        script = ScriptedStreamFn(
            [
                tool_call_turn("echo", {"text": "x"}),
                [
                    {"type": "text_delta", "text": "ok"},
                    {
                        "type": "done",
                        "stop_reason": "stop",
                        "content": [{"type": "text", "text": "ok"}],
                    },
                ],
            ]
        )
        events = await run_scenario(
            script,
            tools=[echo_tool()],
            permission_check=_deny_all,
            permission_audit_sink=crashing_sink,
        )
        # Loop completed normally despite the sink crash.
        assert any(e["type"] == "agent_end" for e in events)
