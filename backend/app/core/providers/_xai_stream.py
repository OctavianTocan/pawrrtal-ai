"""xAI streaming-chunk accumulation helpers.

Split out of ``xai_provider`` so that module stays under the 500-line
file budget (``scripts/check-file-lines.mjs``).  The OpenAI / xAI
chat-completions stream emits tool calls across many partial deltas,
so the StreamFn closure needs running state per call — that state and
its finalisation live here.  No I/O, no SDK constructor calls.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.core.agent_loop.types import (
    LLMDoneEvent,
    TextContent,
    ToolCallContent,
)

logger = logging.getLogger(__name__)

# Finish reason emitted by xAI / OpenAI-compatible endpoints when the
# model produced one or more tool calls.  Mirrors OpenAI's vocabulary.
FINISH_REASON_TOOL_CALLS = "tool_calls"


class ToolCallAccumulator:
    """Reassembles a single OpenAI tool-call from its streamed delta fragments.

    xAI's chat-completions stream emits each tool call across many
    chunks: the first one sets ``id`` + ``function.name``, later ones
    append slices of ``function.arguments``.  The accumulator collects
    them per ``index`` so we can yield a complete
    :class:`LLMToolCallEvent` once the stream ends.
    """

    __slots__ = ("arguments", "id", "name")

    def __init__(self) -> None:
        self.id: str = ""
        self.name: str = ""
        self.arguments: str = ""

    def apply(self, delta: Any) -> None:
        """Merge one OpenAI ``ChoiceDeltaToolCall`` fragment into the buffer."""
        if delta.id:
            self.id = delta.id
        fn = getattr(delta, "function", None)
        if fn is None:
            return
        if fn.name:
            self.name = fn.name
        if fn.arguments:
            self.arguments += fn.arguments


def parse_tool_arguments(raw: str, name: str) -> dict[str, Any]:
    """Parse the accumulated tool-arguments JSON, tolerating empty strings.

    xAI streams ``arguments`` as raw JSON.  An empty / missing
    arguments object is legitimate for tools that take no parameters,
    so we treat ``""`` as ``{}``.  Malformed JSON is surfaced as an
    empty dict with a WARNING — the agent loop will still dispatch the
    tool, and the resulting error is more informative than a stream-
    level exception.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "xai_provider: tool '%s' returned non-JSON arguments (%s); falling back to empty dict",
            name,
            exc,
        )
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _build_tool_call_id(name: str, fallback_id: str, ordinal: int) -> str:
    """Return a stable tool_call_id even when the provider omitted ``id``."""
    if fallback_id:
        return fallback_id
    return f"call-{name}-{ordinal}-{uuid.uuid4().hex[:8]}"


class ChunkAggregate:
    """Cross-chunk streaming state for one ``chat.completions`` call.

    Pulled out of the StreamFn closure so the outer factory stays under
    the ruff complexity cap.  The aggregate owns the running text, the
    per-index :class:`ToolCallAccumulator` map, and the most recent
    ``finish_reason`` observed on the stream.
    """

    __slots__ = ("finish_reason", "full_text", "tool_buffers")

    def __init__(self) -> None:
        self.full_text: str = ""
        self.tool_buffers: dict[int, ToolCallAccumulator] = {}
        self.finish_reason: str | None = None


def absorb_chunk(chunk: Any, aggregate: ChunkAggregate) -> str | None:
    """Update *aggregate* with one streaming chunk.

    Returns any text delta to forward upstream, or ``None`` when the
    chunk only contributed to tool-call accumulation.  Extracted from
    the StreamFn closure so the factory stays inside the ruff complexity
    cap; the branch shape mirrors the OpenAI SDK's
    :class:`ChatCompletionChunk` shape exactly.
    """
    if not chunk.choices:
        return None
    choice = chunk.choices[0]
    delta = choice.delta
    if delta is None:
        return None
    text_delta: str | None = None
    if delta.content:
        text_delta = delta.content
        aggregate.full_text += delta.content
    for tc_delta in getattr(delta, "tool_calls", None) or []:
        idx = getattr(tc_delta, "index", 0) or 0
        buffer = aggregate.tool_buffers.get(idx)
        if buffer is None:
            buffer = ToolCallAccumulator()
            aggregate.tool_buffers[idx] = buffer
        buffer.apply(tc_delta)
    if choice.finish_reason:
        aggregate.finish_reason = choice.finish_reason
    return text_delta


def finalize_tool_calls(aggregate: ChunkAggregate) -> list[dict[str, Any]]:
    """Drain buffered tool calls into ordered, JSON-decoded records.

    Skips fragments that never carried a function name (treated as a
    streaming bug on the upstream side and logged) and returns one
    entry per dispatched tool call in the order the model produced them.
    """
    completed: list[dict[str, Any]] = []
    for ordinal, idx in enumerate(sorted(aggregate.tool_buffers.keys())):
        buffer = aggregate.tool_buffers[idx]
        if not buffer.name:
            logger.warning(
                "xai_provider: dropping tool_call index=%d with empty name (id=%r)",
                idx,
                buffer.id,
            )
            continue
        tool_call_id = _build_tool_call_id(buffer.name, buffer.id, ordinal)
        arguments = parse_tool_arguments(buffer.arguments, buffer.name)
        completed.append(
            {"tool_call_id": tool_call_id, "name": buffer.name, "arguments": arguments}
        )
    return completed


def done_event_for(
    aggregate: ChunkAggregate,
    completed_tool_calls: list[dict[str, Any]],
) -> LLMDoneEvent:
    """Assemble the terminal ``LLMDoneEvent`` from the streamed turn."""
    stop_reason = (
        "tool_use"
        if completed_tool_calls or aggregate.finish_reason == FINISH_REASON_TOOL_CALLS
        else "stop"
    )
    content: list[TextContent | ToolCallContent] = []
    if aggregate.full_text:
        content.append(TextContent(type="text", text=aggregate.full_text))
    content.extend(
        ToolCallContent(
            type="toolCall",
            tool_call_id=tc["tool_call_id"],
            name=tc["name"],
            arguments=tc["arguments"],
        )
        for tc in completed_tool_calls
    )
    return LLMDoneEvent(type="done", stop_reason=stop_reason, content=content)
