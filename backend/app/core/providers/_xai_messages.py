"""xAI request-shape helpers — AgentMessage → OpenAI ``messages`` / ``tools``.

Split out of ``xai_provider`` so that module stays under the 500-line
file budget (``scripts/check-file-lines.mjs``).  All helpers are pure
shape translation — no I/O, no SDK calls.  The public surface is
:func:`build_xai_messages` and :func:`build_xai_tool_declarations`;
their leading underscore-stripped names match how Gemini's equivalents
live in ``_gemini_replay`` / ``gemini_provider``.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.agent_loop.types import (
    AgentMessage,
    AgentTool,
    TextContent,
    ToolCallContent,
    ToolResultMessage,
)


def build_xai_tool_declarations(tools: list[AgentTool]) -> list[dict[str, Any]] | None:
    """Convert :class:`AgentTool` instances to OpenAI ``tools`` entries.

    Returns ``None`` (not ``[]``) when there are no tools so the caller
    can skip the parameter entirely — some OpenAI-compat servers reject
    an empty list and we want xAI to take its default no-tool path.
    """
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def _assistant_content_for_request(
    content: list[TextContent | ToolCallContent],
) -> tuple[str, list[dict[str, Any]]]:
    """Split an assistant message's blocks into the OpenAI request shape.

    OpenAI separates an assistant turn's text (``content`` string) from
    its tool calls (``tool_calls`` array).  The agent loop carries both
    in one ``content`` list, so we partition them here.
    """
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in content:
        if block["type"] == "text":
            text_parts.append(block["text"])
            continue
        tool_calls.append(
            {
                "id": block["tool_call_id"],
                "type": "function",
                "function": {
                    "name": block["name"],
                    "arguments": json.dumps(block["arguments"]),
                },
            }
        )
    return "".join(text_parts), tool_calls


def _tool_result_message(msg: ToolResultMessage) -> dict[str, Any]:
    """Render a tool result into OpenAI's ``role="tool"`` shape."""
    text: str = "\n".join(block["text"] for block in msg["content"])
    return {
        "role": "tool",
        "tool_call_id": msg["tool_call_id"],
        "content": text,
    }


def build_xai_messages(
    messages: list[AgentMessage],
    system_prompt: str,
) -> list[dict[str, Any]]:
    """Convert AgentMessages to OpenAI ``messages`` entries, oldest-first.

    The system prompt is prepended as a ``role="system"`` turn — xAI
    follows OpenAI's convention here rather than Gemini's separate
    ``system_instruction`` field.
    """
    out: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        if msg["role"] == "user":
            text = msg["content"]
            if text.strip():
                out.append({"role": "user", "content": text})
            continue
        if msg["role"] == "assistant":
            text, tool_calls = _assistant_content_for_request(msg["content"])
            entry: dict[str, Any] = {"role": "assistant"}
            # OpenAI rejects an entirely empty assistant turn (no content
            # AND no tool_calls) so we ensure at least one field carries
            # a non-falsey value.
            entry["content"] = text or None
            if tool_calls:
                entry["tool_calls"] = tool_calls
            out.append(entry)
            continue
        out.append(_tool_result_message(msg))
    return out
