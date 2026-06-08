"""Provider-neutral AgentEvent to StreamEvent translation helpers."""

from __future__ import annotations

import logging
from typing import Any

from app.agents.types import AgentMessage
from app.providers.base import StreamEvent

logger = logging.getLogger(__name__)


def identity_convert(messages: list[AgentMessage]) -> list[AgentMessage]:
    """Pass through messages the LLM understands; filter UI-only types."""
    return [m for m in messages if m["role"] in {"user", "assistant", "toolResult"}]


def agent_event_to_stream_event(event: Any) -> StreamEvent | None:
    """Translate one generic ``AgentEvent`` into a provider stream event."""
    event_type = event["type"]
    if event_type == "text_delta":
        return StreamEvent(type="delta", content=event["text"])
    if event_type == "thinking_delta":
        thinking_event = StreamEvent(type="thinking", content=event["text"])
        block_index = event.get("block_index")
        if block_index is not None:
            thinking_event["block_index"] = block_index
        return thinking_event
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
