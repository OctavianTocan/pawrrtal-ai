"""Gemini message / tool-declaration / chunk helpers.

Split out of ``gemini_provider`` to keep that module under the
project's 500-line file budget. These are pure conversion functions
between Pawrrtal's :class:`~app.core.agent_loop.types.AgentMessage`
shape and the google-genai SDK's ``Content`` / ``Part`` types.
Nothing here owns I/O or SDK clients; everything is deterministic
given its inputs.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from google.genai import types as gtypes

from app.core.agent_loop.types import (
    AgentMessage,
    AgentTool,
    TextContent,
    ToolCallContent,
    ToolResultMessage,
)
from app.core.config import settings
from app.core.keys import resolve_api_key

from ._gemini_replay import replay_content_for

logger = logging.getLogger(__name__)


def build_gemini_tool_declarations(
    tools: list[AgentTool],
) -> list[gtypes.Tool] | None:
    """Convert AgentTools to Gemini FunctionDeclarations."""
    if not tools:
        return None
    declarations = [
        gtypes.FunctionDeclaration(
            name=t.name,
            description=t.description,
            parameters_json_schema=t.parameters,
        )
        for t in tools
    ]
    return [gtypes.Tool(function_declarations=declarations)]


def _assistant_parts(content: list[TextContent | ToolCallContent]) -> list[gtypes.Part]:
    """Convert one assistant message's text/tool-call blocks to Gemini parts."""
    parts: list[gtypes.Part] = []

    for block in content:
        if block["type"] == "text":
            text = block["text"]
            if text.strip():
                parts.append(gtypes.Part.from_text(text=text))
            continue

        parts.append(
            gtypes.Part.from_function_call(
                name=block["name"],
                args=block["arguments"],
            )
        )

    return parts


def _tool_result_content(msg: ToolResultMessage) -> gtypes.Content:
    """Convert a loop tool result to Gemini's function-response content."""
    text: str = "\n".join(block["text"] for block in msg["content"])
    response_key: str = "error" if msg["is_error"] else "result"
    return gtypes.UserContent(
        parts=[
            gtypes.Part.from_function_response(
                name=msg["name"],
                response={response_key: text},
            )
        ]
    )


def build_gemini_contents(messages: list[AgentMessage]) -> list[gtypes.ContentUnion]:
    """Convert AgentMessages to Gemini Contents, oldest-first.

    Args:
        messages: The list of AgentMessages to convert.

    Returns:
        The list of Gemini Contents.
    """
    # ``ContentUnion`` matches the SDK's overloaded ``contents=`` param —
    # ``list[Content]`` alone is rejected by mypy even though it works at
    # runtime. See ``app/core/gemini_utils.py`` for the same workaround.
    contents: list[gtypes.ContentUnion] = []

    for msg in messages:
        if msg["role"] == "user":
            text = msg["content"]
            if text.strip():
                contents.append(gtypes.UserContent(parts=[gtypes.Part.from_text(text=text)]))
            continue
        if msg["role"] == "assistant":
            # When the assistant message carries the original Gemini
            # ``ModelContent`` (saved on the producing turn), replay it
            # verbatim.  This preserves ``thought_signature`` bytes that
            # Vertex / Gemini-3 require for follow-up tool turns:
            # https://ai.google.dev/gemini-api/docs/thought-signatures
            replay = replay_content_for(msg)
            if replay is not None:
                contents.append(replay)
                continue
            parts = _assistant_parts(msg["content"])
            if parts:
                contents.append(gtypes.ModelContent(parts=parts))
            continue
        contents.append(_tool_result_content(msg))

    return contents


def resolve_gemini_api_key(workspace_root: Path | None) -> str:
    """Resolve the Gemini API key for this request."""
    if workspace_root is not None:
        return resolve_api_key(workspace_root, "GEMINI_API_KEY") or ""
    return settings.google_api_key


def split_chunk_text(chunk: Any) -> tuple[list[str], str]:
    """Return ``(thinking_parts, response_text)`` for a streaming chunk.

    Gemini's thinking-capable models emit ``Part`` objects with a
    ``thought=True`` flag for chain-of-thought content; regular response
    text uses ``thought=False`` (or ``None``).  The ``chunk.text``
    convenience accessor concatenates *all* text parts regardless of the
    flag, so consumers that need to render the two streams separately
    must walk parts explicitly.

    Each distinct ``Part(thought=True)`` is returned as its own list
    entry so the caller can assign a separate ``block_index`` per
    block (#353). The caller pairs each part with an incrementing
    counter and emits one :class:`LLMThinkingDeltaEvent` per part with
    that index — the channel renderer then knows where Gemini intended
    a paragraph break without relying on whitespace heuristics (#351).
    Response parts are concatenated verbatim; they carry their own
    model-owned whitespace.

    Non-thinking models simply never set ``thought=True``, so the
    thinking list stays empty and the response string is identical to
    ``chunk.text``.
    """
    thinking_parts: list[str] = []
    response_parts: list[str] = []
    for candidate in chunk.candidates or []:
        if not candidate.content or not candidate.content.parts:
            continue
        for part in candidate.content.parts:
            text = getattr(part, "text", None)
            if not text:
                continue
            if getattr(part, "thought", False):
                thinking_parts.append(text)
            else:
                response_parts.append(text)
    return thinking_parts, "".join(response_parts)


def tool_calls_from_chunk(chunk: Any, start_index: int) -> list[dict[str, Any]]:
    """Extract Gemini function-call parts from a streaming chunk.

    Only the name + args are surfaced to the agent loop; the enclosing
    ``ModelContent`` (with its ``thought_signature`` bytes) is captured
    separately by :func:`~._gemini_replay.function_call_content_for`
    and forwarded as opaque ``provider_state`` on the terminal
    ``LLMDoneEvent``.
    """
    calls: list[dict[str, Any]] = []
    for candidate in chunk.candidates or []:
        if not candidate.content or not candidate.content.parts:
            continue
        for part in candidate.content.parts:
            if not part.function_call:
                continue
            fc = part.function_call
            fn_name = fc.name or ""
            # uuid suffix keeps tool_call_ids unique across loop iterations
            # (start_index resets each StreamFn call). Gemini matches calls
            # to responses by ordinal position, so the suffix is invisible.
            tool_call_id = f"call-{fn_name}-{start_index + len(calls)}-{uuid.uuid4().hex[:8]}"
            calls.append(
                {
                    "tool_call_id": tool_call_id,
                    "name": fn_name,
                    "arguments": dict(fc.args) if fc.args else {},
                }
            )
    return calls
