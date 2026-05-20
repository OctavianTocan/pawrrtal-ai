"""LLM-event translation + per-turn message preparation for the agent loop.

Extracted from :mod:`app.core.agent_loop.loop` so the translation of one
provider :data:`LLMEvent` into one or more :data:`AgentEvent` items, the
opaque ``provider_state`` carry, and the pre-turn context-transform live
in one place that the main loop can read at a glance.

All names beginning with an underscore are package-internal — call them
only from sibling modules inside :mod:`app.core.agent_loop` (see
``.claude/rules/clean-code/python-module-privacy.md``).
"""

from __future__ import annotations

from typing import Any

from app.core.agent_loop.display import (
    ToolDisplay,
    render_display_from_map,
)
from app.core.agent_loop.types import (
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    LLMEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)


async def _prepare_llm_messages(
    messages: list[AgentMessage],
    config: AgentLoopConfig,
) -> list[AgentMessage]:
    """Apply context transform (if any) and convert to LLM format."""
    transformed = messages
    if config.transform_context is not None:
        transformed = await config.transform_context(list(messages))
    return config.convert_to_llm(transformed)


def _consume_llm_event(
    llm_event: LLMEvent,
    events: list[AgentEvent],
    display_by_name: dict[str, ToolDisplay] | None = None,
) -> dict[str, Any] | None:
    """Translate one LLMEvent into AgentEvents and append to ``events``.

    Returns the payload for the terminal ``done`` event
    (``{content, stop_reason}``) when the consumed event was that
    terminator; otherwise ``None``.  Returning instead of using a
    mutable out-param keeps the caller's loop body flat enough to fit
    inside the project nesting-depth budget.
    """
    if llm_event["type"] == "text_delta":
        events.append(TextDeltaEvent(type="text_delta", text=llm_event["text"]))
        return None
    if llm_event["type"] == "thinking_delta":
        events.append(ThinkingDeltaEvent(type="thinking_delta", text=llm_event["text"]))
        return None
    if llm_event["type"] == "tool_call":
        display = render_display_from_map(
            display_by_name or {},
            llm_event["name"],
            llm_event["arguments"],
        )
        events.append(
            ToolCallStartEvent(
                type="tool_call_start",
                tool_call_id=llm_event["tool_call_id"],
                name=llm_event["name"],
            )
        )
        events.append(
            ToolCallEndEvent(
                type="tool_call_end",
                tool_call_id=llm_event["tool_call_id"],
                name=llm_event["name"],
                arguments=llm_event["arguments"],
                display=display,
            )
        )
        return None
    if llm_event["type"] == "done":
        result: dict[str, Any] = {
            "content": llm_event["content"],
            "stop_reason": llm_event["stop_reason"],
        }
        # Forward opaque provider replay state if the StreamFn populated
        # it.  ``provider_state`` is a ``total=False`` field on
        # ``LLMDoneEvent`` so we read it with ``.get`` and only copy it
        # forward when the provider actually returned one.  See
        # ``_stream_with_retry`` for the per-turn capture.
        provider_state = llm_event.get("provider_state")
        if provider_state is not None:
            result["provider_state"] = provider_state
        return result
    return None


def _carry_provider_state(
    done: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the provider_state from ``done`` if present, else keep ``current``.

    Extracted out of :func:`app.core.agent_loop.stream_retry._stream_with_retry`
    so the streaming loop's body stays under the project nesting-depth
    budget.  The loop never inspects the contents — providers own the
    keyspace; we just forward the slot.
    """
    if done is not None and "provider_state" in done:
        state = done["provider_state"]
        # ``done`` is a TypedDict-shaped dict — narrow the dynamic value
        # back to the declared return type so mypy doesn't infer ``Any``.
        return state if isinstance(state, dict) else None
    return current
