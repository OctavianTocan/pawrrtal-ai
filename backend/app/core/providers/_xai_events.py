"""xAI AgentEvent → StreamEvent translation helper.

Split out of ``xai_provider`` to keep that module under the 500-line
file budget.  Pure translation — no I/O, no OpenAI SDK references.

The translation rules mirror Gemini's (``_gemini_events.py``): the
agent loop is provider-neutral so every provider's adapter funnels the
same AgentEvent vocabulary into the same StreamEvent shape.  Reusing
the rules keeps SSE payloads identical regardless of which model
served the turn.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.agent_loop.types import AgentMessage

from .base import StreamEvent

logger = logging.getLogger(__name__)


def identity_convert(messages: list[AgentMessage]) -> list[AgentMessage]:
    """Pass through messages the LLM understands; filter UI-only types."""
    return [m for m in messages if m["role"] in {"user", "assistant", "toolResult"}]


def agent_event_to_stream_event(event: Any) -> StreamEvent | None:
    """Translate one ``AgentEvent`` from the loop into a frontend ``StreamEvent``.

    Returns ``None`` for events that don't carry user-facing payload
    (``agent_start`` / ``agent_end`` / ``message_*`` / ``turn_*`` /
    ``tool_call_start``) — the chat router emits the ``[DONE]`` sentinel
    itself when the loop completes.
    """
    event_type = event["type"]
    if event_type == "text_delta":
        return StreamEvent(type="delta", content=event["text"])
    if event_type == "thinking_delta":
        return StreamEvent(type="thinking", content=event["text"])
    if event_type == "tool_call_end":
        return StreamEvent(
            type="tool_use",
            name=event["name"],
            input=event["arguments"],
            tool_use_id=event["tool_call_id"],
            display=event.get("display"),
        )
    if event_type == "tool_result":
        return StreamEvent(
            type="tool_result",
            content=event["content"],
            tool_use_id=event["tool_call_id"],
        )
    if event_type == "agent_terminated":
        logger.warning(
            "AGENT_TERMINATED reason=%s details=%s",
            event["reason"],
            event["details"],
        )
        return StreamEvent(type="agent_terminated", content=event["message"])
    return None
