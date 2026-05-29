"""End-to-end smoke for ``ClaudeLLM.stream`` against the real SDK.

These tests verify the load-bearing behaviours that unit tests can't:

  1. The SDK actually launches and streams text deltas back.
  2. A custom :class:`AgentTool` round-trips through the bridge —
     declared, called by Claude, executed in-process, and the result
     reaches Claude on the next turn.

We deliberately avoid asserting model output content; the smoke is
\"can the pipe carry water\", not \"does Claude say the right thing\".
The cheapest available model (Haiku 4.5 at the time of this PR) is
used so a CI run on every relevant PR stays in cents.
"""

from __future__ import annotations

import uuid

import pytest

from app.agents.types import AgentTool
from app.providers.base import StreamEvent
from app.providers.claude import ClaudeLLM, ClaudeLLMConfig

# Mark every test in this module as anyio so we can ``await``
# inside.  AnyIO-style async tests align with the rest of the suite.
pytestmark = pytest.mark.anyio


async def _drain(
    provider: ClaudeLLM, prompt: str, *, tools: list[AgentTool] | None = None
) -> list[StreamEvent]:
    """Run one turn against the provider and collect every emitted event."""
    return [
        event
        async for event in provider.stream(
            prompt,
            conversation_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            tools=tools,
            # Override the default system prompt to keep the model's reply
            # short and predictable — costs less, lower variance.
            system_prompt=(
                "You are a smoke-test fixture.  Reply briefly and follow "
                "the user's instructions exactly."
            ),
        )
    ]


async def test_provider_streams_text_deltas_for_basic_prompt(
    claude_oauth_token: str, claude_model_id: str
) -> None:
    """Basic round-trip: send a prompt, get text deltas and a final result."""
    provider = ClaudeLLM(
        claude_model_id,
        config=ClaudeLLMConfig(oauth_token=claude_oauth_token),
    )
    events = await _drain(provider, "Reply with just the word 'pong'.")

    # Don't assert on token contents (stochastic).  Assert on the
    # event-shape contract: at least one delta or thinking event,
    # no error events.
    streamed_text = [e for e in events if e["type"] in {"delta", "thinking"}]
    assert streamed_text, f"expected at least one delta/thinking event, got {events}"
    errors = [e for e in events if e["type"] == "error"]
    assert errors == [], f"unexpected error events: {errors}"


async def test_agent_tool_round_trips_through_claude_bridge(
    claude_oauth_token: str, claude_model_id: str
) -> None:
    """A custom AgentTool, bridged into Claude's MCP surface, runs end-to-end.

    Verifies the bridge's load-bearing claim: an `AgentTool` declared
    in app code becomes a tool Claude can invoke, the handler runs
    in-process, and the result reaches Claude.
    """
    invocations: list[dict[str, object]] = []

    async def _execute(_call_id: str, **kwargs: object) -> str:
        # Record the invocation so the test can assert on it
        # post-stream.  Returning the kwargs back as text lets Claude
        # echo them and gives us a content-free way to verify the
        # round-trip without depending on model phrasing.
        invocations.append(dict(kwargs))
        message = kwargs.get("message", "<missing>")
        return f"echoed:{message}"

    echo_tool = AgentTool(
        name="echo_back",
        description=(
            "Test fixture.  Always call this tool exactly once with "
            "the user's message.  Then reply with one word: 'done'."
        ),
        parameters={
            "type": "object",
            "properties": {"message": {"type": "string", "description": "Verbatim user message."}},
            "required": ["message"],
        },
        execute=_execute,
    )

    provider = ClaudeLLM(
        claude_model_id,
        config=ClaudeLLMConfig(oauth_token=claude_oauth_token),
    )
    events = await _drain(provider, "ping for echo test", tools=[echo_tool])

    # Strong signal the bridge is wired correctly: our handler ran.
    assert invocations, (
        "echo_back.execute() was never called — bridge did not declare "
        f"the tool to Claude or did not dispatch back. Events: {events!r}"
    )

    # And a tool_result event made it back into the SSE stream so the
    # frontend can render it.  Don't assert on the body (Claude
    # picks the wording); just on the presence.
    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert tool_results, f"no tool_result events emitted; got types {[e['type'] for e in events]}"
