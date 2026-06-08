"""OpenTelemetry GenAI attribute schema and payload renderers.

Constants and helpers for the Traceloop / OpenTelemetry GenAI span shape that
``app.infrastructure.observability.agent_trace`` emits. Private to the package;
the public surface lives in ``agent_trace.py`` / the package ``__init__``.

The constants here are the wire contract between Pawrrtal and any
OpenTelemetry-aware backend.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agents.types import (
        AgentMessage,
        AssistantMessage,
        TextContent,
        ToolCallContent,
        ToolResultMessage,
        UserMessage,
    )

_log = logging.getLogger(__name__)

# Tracer identity surfaced in trace backends. Bump when the
# attribute schema changes so operators can spot the version skew.
TRACER_NAME = "pawrrtal.agent_trace"
TRACER_VERSION = "1.0.0"

# Traceloop discriminates LLM / tool spans by these attribute values.
KIND_LLM = "llm"
KIND_TOOL = "tool"

# OpenTelemetry GenAI attribute names — the source of truth for
# every ``span.set_attribute`` call in the public module.
ATTR_TRACELOOP_KIND = "traceloop.span.kind"
ATTR_TRACELOOP_NAME = "traceloop.entity.name"
ATTR_TRACELOOP_INPUT = "traceloop.entity.input"
ATTR_TRACELOOP_OUTPUT = "traceloop.entity.output"
ATTR_OTEL_STATUS_MESSAGE = "otel.status.message"
ATTR_GENAI_OPERATION = "gen_ai.operation.name"
ATTR_GENAI_REQUEST_MODEL = "gen_ai.request.model"
ATTR_GENAI_RESPONSE_MODEL = "gen_ai.response.model"
ATTR_GENAI_INPUT_MESSAGES = "gen_ai.input.messages"
ATTR_GENAI_OUTPUT_MESSAGES = "gen_ai.output.messages"
ATTR_GENAI_SYSTEM_INSTRUCTIONS = "gen_ai.system_instructions"
ATTR_GENAI_FINISH_REASONS = "gen_ai.response.finish_reasons"
ATTR_GENAI_INPUT_TOKENS = "gen_ai.usage.input_tokens"
ATTR_GENAI_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
ATTR_GENAI_COST_USD = "gen_ai.usage.cost_usd"

# Pawrrtal-namespaced attributes for filtering spans by conversation,
# request, user, surface, and tool call.
ATTR_CONVERSATION_ID = "pawrrtal.conversation_id"
ATTR_USER_ID = "pawrrtal.user_id"
ATTR_SURFACE = "pawrrtal.surface"
ATTR_REQUEST_ID = "pawrrtal.request_id"
ATTR_TOOL_CALL_ID = "pawrrtal.tool_call_id"

# Latency attributes — Pawrrtal-namespaced rather than using OTel-GenAI
# names (the semantic-conventions spec doesn't pin a TTFT attribute yet,
# and our turn-level duration covers more than the LLM round-trip).
# ``duration_ms`` is redundant with the span's natural duration but is
# cheaper to query in log/metrics backends than computing
# end_time - start_time per span.
ATTR_PAWRRTAL_TURN_DURATION_MS = "pawrrtal.turn.duration_ms"
ATTR_PAWRRTAL_TURN_TTFT_MS = "pawrrtal.turn.ttft_ms"
ATTR_PAWRRTAL_LLM_DURATION_MS = "pawrrtal.llm.duration_ms"
ATTR_PAWRRTAL_LLM_TTFT_MS = "pawrrtal.llm.ttft_ms"

# Span event names.
EVENT_CONTENT_DELTA = "gen_ai.content.delta"
EVENT_THINKING_DELTA = "gen_ai.thinking.delta"
EVENT_ATTR_CONTENT_TEXT = "gen_ai.content.text"
EVENT_ATTR_THINKING_TEXT = "gen_ai.thinking.text"

# StreamEvent type literals we care about (subset of
# ``app.providers.base.StreamEvent``).  Centralised so the
# ``agent_event_hook`` dispatch table reads as a flat string map.
STREAM_TYPE_DELTA = "delta"
STREAM_TYPE_THINKING = "thinking"
STREAM_TYPE_TOOL_USE = "tool_use"
STREAM_TYPE_USAGE = "usage"
STREAM_TYPE_ERROR = "error"


def json_dumps(value: Any) -> str:
    """Serialize *value* for a JSON-parsed span attribute.

    Trace viewers may call ``JSON.parse`` on these strings; an
    unparseable string crashes its renderer for the affected span.
    The fallback shape preserves the *fact* of the failure (so a
    debugging operator sees it) without breaking the span.
    """
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        _log.debug("AGENT_TRACE_JSON_SERIALIZE_FAILED", exc_info=True)
        return json.dumps({"_unserializable": repr(value)})


def render_input_messages(messages: list[AgentMessage]) -> list[dict[str, Any]]:
    """Render agent-loop messages in the canonical ``gen_ai.input.messages`` shape.

    Trace viewers expect each message to be ``{"role": ..., "parts": [...]}``
    with part types ``"text"``, ``"tool_call"``, or ``"tool_result"``.
    Mapping here keeps the wire shape consistent across providers (the
    loop's TypedDict messages are already provider-neutral).
    """
    return [_render_message(msg) for msg in messages]


def _render_message(msg: AgentMessage) -> dict[str, Any]:
    """Render one ``AgentMessage`` as a ``{role, parts}`` dict.

    The discriminator (``msg["role"]``) is checked inline rather than
    via a captured local so pyright narrows the TypedDict union on
    each branch.  ``AgentMessage`` is an exhaustive ``UserMessage |
    AssistantMessage | ToolResultMessage`` union so the three checks
    are total — no sentinel fallthrough is needed.
    """
    if msg["role"] == "user":
        return _render_user(msg)
    if msg["role"] == "assistant":
        return _render_assistant(msg)
    return _render_tool_result(msg)


def _render_user(msg: UserMessage) -> dict[str, Any]:
    """Render a ``UserMessage`` as a single-text-part user turn."""
    return {
        "role": "user",
        "parts": [{"type": "text", "content": msg["content"]}],
    }


def _render_assistant(msg: AssistantMessage) -> dict[str, Any]:
    """Render an ``AssistantMessage`` (text + tool-call parts)."""
    return {"role": "assistant", "parts": _render_assistant_parts(msg["content"])}


def _render_tool_result(msg: ToolResultMessage) -> dict[str, Any]:
    """Render a ``ToolResultMessage`` as one tool-result part."""
    joined = "".join(c["text"] for c in msg["content"])
    return {
        "role": "tool",
        "parts": [
            {
                "type": "tool_result",
                "tool_use_id": msg["tool_call_id"],
                "content": joined,
            }
        ],
    }


def _render_assistant_parts(
    content: list[TextContent | ToolCallContent],
) -> list[dict[str, Any]]:
    """Translate an assistant ``content`` list into ``parts`` blocks."""
    parts: list[dict[str, Any]] = []
    for block in content:
        if block["type"] == "text":
            parts.append({"type": "text", "content": block["text"]})
        else:  # toolCall — the only other discriminant in the TypedDict union.
            parts.append(
                {
                    "type": "tool_call",
                    "id": block["tool_call_id"],
                    "name": block["name"],
                    "arguments": block["arguments"],
                }
            )
    return parts
