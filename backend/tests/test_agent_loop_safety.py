"""Safety-layer tests for the agent loop.

These tests use the shared ``agent_harness`` primitives and run through the
**real** agent loop, safety layer, and tool-execution code.  Only the
``StreamFn`` seam is replaced — see ``agent_harness.py`` for the full pattern.

Exception: ``test_max_wall_clock_terminates_long_running_loop`` keeps a bespoke
``slow_stream`` because wall-clock tests require real ``asyncio.sleep`` delays
that ``ScriptedStreamFn`` does not support.  See the test docstring for why
this is the only acceptable deviation.
"""

from __future__ import annotations

import asyncio

import pytest

from app.agents import (
    AgentContext,
    AgentLoopConfig,
    AgentSafetyConfig,
    UserMessage,
    agent_loop,
)
from tests.agent_harness import (
    ScriptedStreamFn,
    echo_tool,
    error_turn,
    failing_tool,
    identity_convert,
    run_scenario,
    text_turn,
    tool_call_turn,
)


def _user(text: str) -> UserMessage:
    return UserMessage(role="user", content=text)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_max_iterations_terminates_runaway_tool_loop():
    """A model that calls a tool every turn should bail at the cap."""
    tool = echo_tool("ping")
    script = ScriptedStreamFn([tool_call_turn("ping", {})] * 10)

    events = await run_scenario(
        script,
        safety=AgentSafetyConfig(
            max_iterations=3,
            max_wall_clock_seconds=None,
            max_consecutive_llm_errors=None,
            max_consecutive_tool_errors=None,
        ),
        tools=[tool],
    )

    terminated = [e for e in events if e["type"] == "agent_terminated"]
    assert len(terminated) == 1
    assert terminated[0]["reason"] == "max_iterations"
    assert terminated[0]["details"]["limit"] == 3
    assert terminated[0]["details"]["observed"] == 3
    assert script.call_count == 3


@pytest.mark.anyio
async def test_max_wall_clock_terminates_long_running_loop():
    """A loop whose budget is already exceeded bails on the next pre-turn check.

    Note: this test intentionally keeps a bespoke ``slow_stream`` rather than
    ``ScriptedStreamFn`` because wall-clock behaviour requires real
    ``asyncio.sleep`` delays.  This is the only acceptable deviation from
    Rule 2 in the AGENTS.md Agent-Loop Testing Philosophy — document any
    future timing-sensitive tests with the same annotation.
    """
    tool = echo_tool("ping")

    async def slow_stream(_msgs, _tools):
        await asyncio.sleep(0.05)
        yield {
            "type": "tool_call",
            "tool_call_id": "tc",
            "name": "ping",
            "arguments": {},
        }
        yield {
            "type": "done",
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "toolCall",
                    "tool_call_id": "tc",
                    "name": "ping",
                    "arguments": {},
                }
            ],
        }

    ctx = AgentContext(system_prompt="", messages=[], tools=[tool])
    cfg = AgentLoopConfig(
        convert_to_llm=identity_convert,
        safety=AgentSafetyConfig(
            max_iterations=None,
            max_wall_clock_seconds=0.01,
            max_consecutive_llm_errors=None,
            max_consecutive_tool_errors=None,
        ),
    )
    events = [ev async for ev in agent_loop([_user("go")], ctx, cfg, slow_stream)]
    terminated = [e for e in events if e["type"] == "agent_terminated"]
    assert len(terminated) == 1
    assert terminated[0]["reason"] == "max_wall_clock"


@pytest.mark.anyio
async def test_consecutive_tool_errors_terminate():
    """N back-to-back tool failures trip the guard."""
    script = ScriptedStreamFn([tool_call_turn("flaky", {})] * 10)

    events = await run_scenario(
        script,
        safety=AgentSafetyConfig(
            max_iterations=None,
            max_wall_clock_seconds=None,
            max_consecutive_llm_errors=None,
            max_consecutive_tool_errors=2,
        ),
        tools=[failing_tool("flaky")],
    )

    terminated = [e for e in events if e["type"] == "agent_terminated"]
    assert len(terminated) == 1
    assert terminated[0]["reason"] == "consecutive_tool_errors"
    assert terminated[0]["details"]["observed"] == 2
    assert script.call_count == 2


@pytest.mark.anyio
async def test_consecutive_tool_errors_reset_on_success():
    """A successful tool call resets the counter.

    Sequence: bad → ok (resets) → bad → done.
    Counter never reaches 2, so no termination.
    """
    script = ScriptedStreamFn(
        [
            tool_call_turn("bad", {}, "tc-0"),
            tool_call_turn("ok", {}, "tc-1"),
            tool_call_turn("bad", {}, "tc-2"),
            text_turn("done"),
        ]
    )

    events = await run_scenario(
        script,
        safety=AgentSafetyConfig(
            max_iterations=10,
            max_wall_clock_seconds=None,
            max_consecutive_llm_errors=None,
            max_consecutive_tool_errors=2,
        ),
        tools=[echo_tool("ok"), failing_tool("bad")],
    )

    terminated = [e for e in events if e["type"] == "agent_terminated"]
    assert terminated == []
    assert script.call_count == 4


@pytest.mark.anyio
async def test_llm_retry_recovers_from_transient_error():
    """First stream raises, second succeeds — loop should not terminate."""
    script = ScriptedStreamFn([error_turn(), text_turn("hello")])

    events = await run_scenario(
        script,
        safety=AgentSafetyConfig(
            max_iterations=10,
            max_wall_clock_seconds=None,
            max_consecutive_llm_errors=3,
            max_consecutive_tool_errors=None,
            llm_retry_backoff_seconds=0,
        ),
    )

    terminated = [e for e in events if e["type"] == "agent_terminated"]
    assert terminated == []
    text_events = [e for e in events if e["type"] == "text_delta"]
    assert any(e["text"] == "hello" for e in text_events)
    assert script.call_count == 2


@pytest.mark.anyio
async def test_llm_retry_exhausted_terminates():
    """Persistent provider error eventually bails after the budget."""
    script = ScriptedStreamFn([error_turn()] * 10)

    events = await run_scenario(
        script,
        safety=AgentSafetyConfig(
            max_iterations=10,
            max_wall_clock_seconds=None,
            max_consecutive_llm_errors=2,
            max_consecutive_tool_errors=None,
            llm_retry_backoff_seconds=0,
        ),
    )

    terminated = [e for e in events if e["type"] == "agent_terminated"]
    assert len(terminated) == 1
    assert terminated[0]["reason"] == "consecutive_llm_errors"
    assert terminated[0]["details"]["observed"] == 2
    assert "provider unavailable" in terminated[0]["details"]["last_error"]
    assert script.call_count == 2


@pytest.mark.anyio
async def test_safety_disabled_preserves_unbounded_behaviour():
    """``AgentSafetyConfig.disabled()`` should leave normal turns alone."""
    script = ScriptedStreamFn([text_turn("hello")])
    events = await run_scenario(script, safety=AgentSafetyConfig.disabled())
    terminated = [e for e in events if e["type"] == "agent_terminated"]
    assert terminated == []
    assert any(e["type"] == "agent_end" for e in events)


@pytest.mark.anyio
async def test_default_safety_does_not_break_short_turns():
    """A normal one-turn chat completes cleanly with default safety."""
    script = ScriptedStreamFn([text_turn("hi back")])
    events = await run_scenario(script)
    terminated = [e for e in events if e["type"] == "agent_terminated"]
    assert terminated == []
    assert any(e["type"] == "agent_end" for e in events)
