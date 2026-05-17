"""Shared test harness for agent-loop scenario tests.

``ScriptedStreamFn`` replaces the real LLM at the ``StreamFn`` seam so tests
run through the genuine ``agent_loop``, safety layer, and tool-execution code
without any real API calls.

The pattern is sometimes called "reverse eval" or "mock-provider scenario
testing":

* You author a deterministic decision sequence (tool calls, text replies,
  errors) as a list of "turns".
* ``ScriptedStreamFn`` replays the sequence one turn per agent-loop call.
* The real harness (``agent_loop``, tool execution) runs against the
  scripted decisions.
* Assertions target what the harness *did*, not what the LLM *said*.

References
----------
* pytest-agentcontract  — contract-style fixture pattern
* langchain-replay      — recorded response replay
* Agentspan mock_run    — provider-level replay

Usage
-----
::

    from tests.agent_harness import (
        ScriptedStreamFn,
        echo_tool,
        error_turn,
        failing_tool,
        identity_convert,
        make_recording_stream_fn,
        parallel_tool_calls_turn,
        run_scenario,
        text_turn,
        tool_call_turn,
    )
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator

from app.core.agent_loop import (
    AgentContext,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    AgentSafetyConfig,
    AgentTool,
    UserMessage,
    agent_loop,
)
from app.core.agent_loop.types import (
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    LLMThinkingDeltaEvent,
    LLMToolCallEvent,
    PermissionAuditSinkFn,
    PermissionCheckFn,
    TextContent,
    ToolCallContent,
)

# ---------------------------------------------------------------------------
# Turn builders — each returns a list of LLMEvents for one LLM call
# ---------------------------------------------------------------------------


def text_turn(text: str) -> list[LLMEvent]:
    """LLM responds with plain text and stops.

    Args:
        text: The text the LLM replies with.

    Returns:
        A two-element list: a ``text_delta`` event and a ``done`` event.
    """
    return [
        LLMTextDeltaEvent(type="text_delta", text=text),
        LLMDoneEvent(
            type="done",
            stop_reason="stop",
            content=[TextContent(type="text", text=text)],
        ),
    ]


def thinking_then_text_turn(thinking: str, text: str) -> list[LLMEvent]:
    """LLM reasons out loud, then replies with plain text and stops.

    Mirrors what a thinking-capable model (Claude with extended thinking,
    Gemini with ``include_thoughts=True``, OpenAI o-series) emits during
    one turn — a stream of ``thinking_delta`` chunks followed by the
    user-visible ``text_delta``.  The thinking text never appears in
    the assistant message ``content`` (it's a presentation-only signal),
    matching production provider behaviour.

    Args:
        thinking: The internal reasoning the model surfaces.
        text: The final user-visible reply.

    Returns:
        A three-element list: a ``thinking_delta`` event, a ``text_delta``
        event, and a ``done`` event whose ``content`` only carries
        ``text``.
    """
    return [
        LLMThinkingDeltaEvent(type="thinking_delta", text=thinking),
        LLMTextDeltaEvent(type="text_delta", text=text),
        LLMDoneEvent(
            type="done",
            stop_reason="stop",
            content=[TextContent(type="text", text=text)],
        ),
    ]


def tool_call_turn(
    name: str,
    args: dict,
    turn_id: str = "tc-0",
) -> list[LLMEvent]:
    """LLM requests one tool call and stops with ``stop_reason='tool_use'``.

    Args:
        name: Tool name to call.
        args: Arguments dict passed to the tool.
        turn_id: Stable tool-call ID (defaults to ``'tc-0'``).

    Returns:
        A two-element list: a ``tool_call`` event and a ``done`` event.
    """
    return [
        LLMToolCallEvent(
            type="tool_call",
            tool_call_id=turn_id,
            name=name,
            arguments=args,
        ),
        LLMDoneEvent(
            type="done",
            stop_reason="tool_use",
            content=[
                ToolCallContent(
                    type="toolCall",
                    tool_call_id=turn_id,
                    name=name,
                    arguments=args,
                )
            ],
        ),
    ]


def error_turn() -> Exception:
    """Return an exception that simulates a transient provider failure.

    Assign the return value into a ``turns`` list; ``ScriptedStreamFn``
    will *raise* it (not yield it) when that index is reached.
    """
    return RuntimeError("provider unavailable")


def parallel_tool_calls_turn(
    calls: list[tuple[str, dict, str]],
) -> list[LLMEvent]:
    """LLM requests multiple tool calls in a single turn (parallel tool use).

    Args:
        calls: A list of ``(name, args, turn_id)`` triples, one per tool call.

    Returns:
        One ``tool_call`` event per call followed by a single ``done`` event
        with ``stop_reason='tool_use'``, mirroring what real providers emit
        when the model fans out to several tools in one turn.

    Example::

        turns = [
            parallel_tool_calls_turn([
                ("search", {"query": "x"}, "tc-0"),
                ("search", {"query": "y"}, "tc-1"),
            ]),
            text_turn("Done."),
        ]
    """
    events: list[LLMEvent] = [
        LLMToolCallEvent(
            type="tool_call",
            tool_call_id=turn_id,
            name=name,
            arguments=args,
        )
        for name, args, turn_id in calls
    ]
    events.append(
        LLMDoneEvent(
            type="done",
            stop_reason="tool_use",
            content=[
                ToolCallContent(
                    type="toolCall",
                    tool_call_id=turn_id,
                    name=name,
                    arguments=args,
                )
                for name, args, turn_id in calls
            ],
        )
    )
    return events


def make_recording_stream_fn(
    turns: list[list[LLMEvent] | Exception],
) -> ScriptedStreamFn:
    """Return a ``ScriptedStreamFn`` that also records messages passed per call.

    The returned script's ``messages_seen[N]`` contains the ``messages`` list
    that was passed to the Nth LLM call, allowing tests to assert on context
    accumulation without hand-rolling a recording generator.

    Args:
        turns: The scripted decision sequence (same as ``ScriptedStreamFn.turns``).

    Returns:
        A ``ScriptedStreamFn`` with ``messages_seen`` populated after each call.

    Example::

        script = make_recording_stream_fn([
            tool_call_turn("search", {"query": "x"}),
            text_turn("answer"),
        ])
        events = await run_scenario(script)
        # Verify the second LLM call sees the tool result in context.
        assert any(m["role"] == "toolResult" for m in script.messages_seen[1])
        assert script.call_count == 2
    """
    return ScriptedStreamFn(turns)


# ---------------------------------------------------------------------------
# ScriptedStreamFn
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class ScriptedStreamFn:
    """A deterministic ``StreamFn`` that replays a pre-written script of turns.

    Each element of ``turns`` is either:

    * ``list[LLMEvent]`` — events yielded for that LLM call, or
    * ``Exception``      — raised as if the provider failed that call.

    When the script is exhausted any additional calls yield an empty
    ``done/stop`` event so the loop exits cleanly rather than hanging.

    ``call_count`` is updated after every call; inspect it after
    ``run_scenario`` to confirm how many LLM calls were made.

    Example::

        script = ScriptedStreamFn([
            tool_call_turn("search", {"query": "python async"}),
            text_turn("Here's what I found…"),
        ])
        events = await run_scenario(script, tools=[search_tool])
        assert script.call_count == 2
    """

    turns: list[list[LLMEvent] | Exception]
    call_count: int = dataclasses.field(default=0, init=False)
    messages_seen: list[list[AgentMessage]] = dataclasses.field(default_factory=list, init=False)

    async def __call__(
        self,
        messages: list[AgentMessage],
        tools: list[AgentTool],
    ) -> AsyncIterator[LLMEvent]:
        self._record_messages(messages)
        idx = self.call_count
        self.call_count += 1
        if idx >= len(self.turns):
            # Script exhausted — yield a clean stop so the loop exits.
            yield LLMDoneEvent(
                type="done",
                stop_reason="stop",
                content=[TextContent(type="text", text="")],
            )
            return
        turn = self.turns[idx]
        if isinstance(turn, Exception):
            raise turn
        for event in turn:
            yield event

    def _record_messages(self, messages: list[AgentMessage]) -> None:
        """Internal: append a snapshot of messages to messages_seen."""
        self.messages_seen.append(list(messages))


# ---------------------------------------------------------------------------
# Pre-built AgentTools
# ---------------------------------------------------------------------------


def echo_tool(name: str = "echo") -> AgentTool:
    """AgentTool that echoes the ``value`` kwarg back to the caller.

    Args:
        name: Tool name (defaults to ``'echo'``).

    Returns:
        A ready-to-use ``AgentTool`` with a single ``value`` parameter.
    """

    async def execute(tool_call_id: str, **kwargs: object) -> str:
        return f"echoed: {kwargs.get('value', '')}"

    return AgentTool(
        name=name,
        description="Echo value back",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        execute=execute,
    )


def failing_tool(name: str = "fail") -> AgentTool:
    """AgentTool that always raises ``RuntimeError``.

    Args:
        name: Tool name (defaults to ``'fail'``).

    Returns:
        A ready-to-use ``AgentTool`` that always errors on execution.
    """

    async def execute(tool_call_id: str, **kwargs: object) -> str:
        raise RuntimeError(f"{name} always fails")

    return AgentTool(
        name=name,
        description="Always fails",
        parameters={"type": "object", "properties": {}},
        execute=execute,
    )


# ---------------------------------------------------------------------------
# Message converter
# ---------------------------------------------------------------------------


def identity_convert(messages: list[AgentMessage]) -> list[AgentMessage]:
    """Pass through user/assistant/toolResult messages unchanged.

    Args:
        messages: Raw message list from the agent loop.

    Returns:
        Filtered list containing only LLM-visible message types.
    """
    return [m for m in messages if m["role"] in {"user", "assistant", "toolResult"}]


# ---------------------------------------------------------------------------
# High-level runner
# ---------------------------------------------------------------------------


async def run_scenario(
    turns: list[list[LLMEvent] | Exception] | ScriptedStreamFn,
    tools: list[AgentTool] | None = None,
    question: str = "go",
    safety: AgentSafetyConfig | None = None,
    permission_check: PermissionCheckFn | None = None,
    permission_audit_sink: PermissionAuditSinkFn | None = None,
) -> list[AgentEvent]:
    """Run an agent-loop scenario end-to-end and return all emitted events.

    Builds a minimal ``AgentContext`` and ``AgentLoopConfig`` then collects
    every event from ``agent_loop`` into a list for assertion.

    Args:
        turns: Either a pre-built ``ScriptedStreamFn`` (when you need to inspect
            ``call_count`` after the run) or a raw list of turn events/exceptions
            (when you only care about the emitted events).
        tools: Tools available to the agent.  Defaults to an empty list.
        question: The user's question text.
        safety: Optional safety config; defaults to all-guards-disabled.
        permission_check: Optional cross-provider permission gate (PR 03b).
            Plumbed straight into ``AgentLoopConfig`` so loop-level denial
            tests run through the real seam, not a patch.
        permission_audit_sink: Optional async sink fired on every denial.

    Returns:
        All ``AgentEvent`` instances emitted by ``agent_loop``, in order.

    Example — checking ``call_count`` after the run::

        script = ScriptedStreamFn([tool_call_turn("ping", {})] * 5)
        events = await run_scenario(script, tools=[ping_tool])
        assert script.call_count == 5
    """
    stream_fn = turns if isinstance(turns, ScriptedStreamFn) else ScriptedStreamFn(turns)
    ctx = AgentContext(
        system_prompt="",
        messages=[],
        tools=list(tools or []),
    )
    cfg = AgentLoopConfig(
        convert_to_llm=identity_convert,
        safety=safety or AgentSafetyConfig.disabled(),
        permission_check=permission_check,
        permission_audit_sink=permission_audit_sink,
    )
    prompt = UserMessage(role="user", content=question)
    return [ev async for ev in agent_loop([prompt], ctx, cfg, stream_fn)]
