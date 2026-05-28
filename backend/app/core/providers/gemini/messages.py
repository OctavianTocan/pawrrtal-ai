"""Gemini message / tool-declaration / chunk helpers.

Split out of ``gemini_provider`` to keep that module under the
project's 500-line file budget. These are pure conversion functions
between Pawrrtal's :class:`~app.core.agent_loop.types.AgentMessage`
shape and the google-genai SDK's ``Content`` / ``Part`` types.
Nothing here owns I/O or SDK clients; everything is deterministic
given its inputs.
"""

from __future__ import annotations

import base64
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google.genai import types as gtypes

from app.core.agent_loop.types import (
    AgentMessage,
    AgentTool,
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    LLMThinkingDeltaEvent,
    LLMToolCallEvent,
    TextContent,
    ToolCallContent,
    ToolResultMessage,
    UserMessage,
)
from app.core.config import settings
from app.core.keys import resolve_api_key

from .replay import function_call_content_for, replay_content_for

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


def _user_parts(
    msg: UserMessage,
    is_last_user: bool,
    images: list[dict[str, str]] | None = None,
) -> list[gtypes.Part]:
    """Helper to convert a user message and optional images into Gemini parts."""
    parts: list[gtypes.Part] = []
    text = msg["content"]
    if text.strip():
        parts.append(gtypes.Part.from_text(text=text))

    if is_last_user and images:
        for img in images:
            if "data" in img:
                media_type = img.get("media_type", "image/png")
                try:
                    raw_bytes = base64.b64decode(img["data"])
                    parts.append(gtypes.Part.from_bytes(data=raw_bytes, mime_type=media_type))
                except Exception:
                    logger.exception("Failed to decode base64 image")
    return parts


def build_gemini_contents(
    messages: list[AgentMessage],
    images: list[dict[str, str]] | None = None,
) -> list[gtypes.Content]:
    """Convert AgentMessages to Gemini Contents, oldest-first.

    Args:
        messages: The list of AgentMessages to convert.
        images: Optional list of base64 multimodal image inputs.
            Appended to the last user message in the list.

    Returns:
        The list of Gemini Contents.
    """
    # Every branch below appends a ``Content`` subclass (``UserContent``,
    # ``ModelContent``, or a ``replay_content_for`` result), so narrow the
    # return type to ``list[Content]`` instead of the broader
    # ``ContentUnion``. The SDK accepts either at the ``contents=`` call.
    contents: list[gtypes.Content] = []

    last_user_idx = -1
    for idx, msg in enumerate(messages):
        if msg["role"] == "user":
            last_user_idx = idx

    for idx, msg in enumerate(messages):
        if msg["role"] == "user":
            parts = _user_parts(msg, idx == last_user_idx, images)
            if parts:
                contents.append(gtypes.UserContent(parts=parts))
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


@dataclass
class _GeminiStreamState:
    """Mutable per-request scratch space for the Gemini StreamFn.

    Lives at module scope so the chunk-level helper can mutate it in
    place without inheriting the streaming for-loop's nesting depth.
    """

    full_text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # Native ``ModelContent`` from whichever chunk produced the
    # function_call parts (Gemini delivers function calls in a single
    # chunk). Forwarded as ``LLMDoneEvent.provider_state["gemini"]
    # ["model_content"]`` so the next turn's request can replay
    # ``thought_signature`` bytes.
    function_call_content: gtypes.Content | None = None
    # Latest ``usage_metadata`` snapshot from this request. Gemini
    # emits cumulative counts on each chunk and a final snapshot on
    # the terminal chunk; we just keep overwriting and absorb the
    # last value into ``usage_sink`` at end-of-stream.
    last_usage_metadata: Any | None = None
    # Monotonic counter for Gemini's per-Part thinking blocks (#353).
    # Each ``Part(thought=True)`` is its own block on the wire, and
    # downstream renderers need that boundary information to insert
    # paragraph breaks between blocks without guessing from
    # whitespace heuristics. Starts at 0 and increments once per
    # emitted thinking part.
    thinking_block_index: int = 0


def _events_from_chunk(chunk: Any, state: _GeminiStreamState) -> Iterator[LLMEvent]:
    """Yield events for one Gemini chunk and mutate ``state`` in place.

    Returns a generator so the caller can ``for event in _events_from_chunk(...)``
    one level shallower than inlining the body would force. Kept as a
    sync generator to stay flat — the outer ``async for chunk`` already
    awaits the SDK iterator.
    """
    # Track the latest ``usage_metadata`` — Gemini reports it
    # cumulatively per chunk, so the final non-None value is the
    # per-request total we want to bill.
    chunk_usage = getattr(chunk, "usage_metadata", None)
    if chunk_usage is not None:
        state.last_usage_metadata = chunk_usage
    # Split parts into thoughts (``part.thought is True``) and regular
    # text. ``chunk.text`` is a convenience accessor that concatenates
    # all text parts regardless of the thought flag, so we walk parts
    # explicitly to keep the two streams separate downstream.
    # ``split_chunk_text`` returns thinking parts as a list so we can
    # stamp each block with its own ``block_index`` (#353).
    thinking_parts, response_text = split_chunk_text(chunk)
    for thinking_text in thinking_parts:
        yield LLMThinkingDeltaEvent(
            type="thinking_delta",
            text=thinking_text,
            block_index=state.thinking_block_index,
        )
        state.thinking_block_index += 1
    if response_text:
        yield LLMTextDeltaEvent(type="text_delta", text=response_text)
        state.full_text += response_text

    chunk_tool_calls = tool_calls_from_chunk(chunk, len(state.tool_calls))
    if not chunk_tool_calls:
        return
    # Capture the original Gemini ``ModelContent`` so follow-up turns
    # can replay ``thought_signature`` bytes verbatim. Only the first
    # function-call chunk is preserved — Gemini emits function calls
    # in a single chunk so this is sufficient.
    if state.function_call_content is None:
        state.function_call_content = function_call_content_for(chunk)
    for tool_call in chunk_tool_calls:
        yield LLMToolCallEvent(
            type="tool_call",
            tool_call_id=tool_call["tool_call_id"],
            name=tool_call["name"],
            arguments=tool_call["arguments"],
        )
        state.tool_calls.append(tool_call)


def _build_done_event(state: _GeminiStreamState) -> LLMDoneEvent:
    """Build the terminal ``LLMDoneEvent`` from accumulated stream state.

    When the turn made any tool calls, forward the original Gemini
    ``ModelContent`` as opaque ``provider_state`` so the next iteration's
    request body replays the exact function_call parts (preserving
    ``thought_signature`` bytes that Gemini-3 / Vertex require).
    Pure-text turns omit the field — there is nothing for the next turn
    to replay.
    """
    stop_reason = "tool_use" if state.tool_calls else "stop"
    content: list[TextContent | ToolCallContent] = []
    if state.full_text:
        content.append(TextContent(type="text", text=state.full_text))
    content.extend(
        ToolCallContent(
            type="toolCall",
            tool_call_id=tc["tool_call_id"],
            name=tc["name"],
            arguments=tc["arguments"],
        )
        for tc in state.tool_calls
    )
    done_event: LLMDoneEvent = LLMDoneEvent(
        type="done",
        stop_reason=stop_reason,
        content=content,
    )
    if state.function_call_content is not None:
        done_event["provider_state"] = {"gemini": {"model_content": state.function_call_content}}
    return done_event


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
