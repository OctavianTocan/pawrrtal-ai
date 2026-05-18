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
from dataclasses import dataclass
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

# xAI bills in "ticks" where ``1 tick = 1e-10 USD``.  Sourced from the
# official xai-sdk Python package's ``cost.py``:
# https://github.com/xai-org/xai-sdk-python/blob/main/src/xai_sdk/cost.py
# (citing
# https://github.com/xai-org/xai-proto/blob/0c0f5353aa7ab2a4ffea310f9d9364ed5c424af2/proto/xai/api/v1/usage.proto#L45).
# Field is opaque on the wire; keeping the constant here means future
# divisor changes are a single-line edit.
USD_PER_TICK = 1e-10


@dataclass(frozen=True, slots=True)
class ChunkDeltas:
    """The user-visible deltas extracted from a single streaming chunk.

    ``text`` is the regular assistant content delta; ``thinking`` is the
    reasoning-trace delta (xAI's ``reasoning_content`` field on grok-4.3
    reasoning turns).  Either or both may be ``None`` for a chunk that
    only contributed to tool-call accumulation or to ``finish_reason``.
    """

    text: str | None = None
    thinking: str | None = None


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


def absorb_chunk(chunk: Any, aggregate: ChunkAggregate) -> ChunkDeltas:
    """Update *aggregate* with one streaming chunk and report the user-visible deltas.

    Returns :class:`ChunkDeltas` carrying any text and / or
    ``reasoning_content`` delta to forward upstream.  Both fields are
    ``None`` when the chunk only contributed to tool-call accumulation
    or to ``finish_reason``.  Extracted from the StreamFn closure so
    the factory stays inside the ruff complexity cap; the branch shape
    mirrors the OpenAI SDK's :class:`ChatCompletionChunk` exactly, plus
    xAI's ``reasoning_content`` extra (allowed because
    :class:`ChoiceDelta` is configured with ``extra='allow'``).
    """
    if not chunk.choices:
        return ChunkDeltas()
    choice = chunk.choices[0]
    delta = choice.delta
    if delta is None:
        return ChunkDeltas()
    text_delta: str | None = None
    if delta.content:
        text_delta = delta.content
        aggregate.full_text += delta.content
    # xAI's grok-4.3 reasoning turn surfaces chain-of-thought in
    # ``reasoning_content`` on each delta.  The openai SDK preserves
    # unknown fields on :class:`ChoiceDelta` via ``extra='allow'`` so a
    # plain ``getattr`` is enough — no SDK upgrade required when xAI
    # changes their schema, and the field stays ``None`` for non-Grok
    # OpenAI-compat providers that never emit it.
    thinking_value = getattr(delta, "reasoning_content", None)
    thinking_delta = thinking_value if isinstance(thinking_value, str) and thinking_value else None
    for tc_delta in getattr(delta, "tool_calls", None) or []:
        idx = getattr(tc_delta, "index", 0) or 0
        buffer = aggregate.tool_buffers.get(idx)
        if buffer is None:
            buffer = ToolCallAccumulator()
            aggregate.tool_buffers[idx] = buffer
        buffer.apply(tc_delta)
    if choice.finish_reason:
        aggregate.finish_reason = choice.finish_reason
    return ChunkDeltas(text=text_delta, thinking=thinking_delta)


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


class UsageAccumulator:
    """Per-request usage totals summed across every StreamFn invocation.

    The agent loop calls the StreamFn once per assistant turn (LLM →
    tool → LLM round-trip), so a single user prompt can drive several
    chat-completions requests.  Each request returns its own ``usage``
    block on the terminal streaming chunk (when
    ``stream_options.include_usage=True``); we sum them so the chat
    aggregator sees the total for the whole turn, matching how Claude
    reports its per-turn cost.

    Mutable on purpose: the StreamFn closure owns one and writes into
    it from inside the stream; :class:`XaiLLM.stream` reads the totals
    after :func:`agent_loop` returns and emits the terminal
    ``StreamEvent(type="usage")``.
    """

    __slots__ = ("cost_usd", "input_tokens", "output_tokens", "saw_any")

    def __init__(self) -> None:
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cost_usd: float = 0.0
        self.saw_any: bool = False

    def absorb(self, chunk: Any) -> None:
        """Fold one chunk's ``usage`` block into the running totals.

        No-op when the chunk has no usage payload — only the final chunk
        of a ``stream_options.include_usage=True`` stream carries it.
        Reads ``prompt_tokens``/``completion_tokens`` (OpenAI naming)
        AND ``input_tokens``/``output_tokens`` (xAI naming) defensively
        because the two endpoints have historically disagreed on which
        names land in the REST envelope.
        """
        usage = getattr(chunk, "usage", None)
        if usage is None:
            return
        self.saw_any = True
        prompt = _read_usage_int(usage, "prompt_tokens", "input_tokens")
        completion = _read_usage_int(usage, "completion_tokens", "output_tokens")
        self.input_tokens += prompt
        self.output_tokens += completion
        ticks = _read_usage_int(usage, "cost_in_usd_ticks")
        if ticks > 0:
            self.cost_usd += ticks * USD_PER_TICK


def _read_usage_int(usage: Any, *names: str) -> int:
    """Read the first non-zero integer field from ``usage``.

    Tries each name in order using ``getattr`` (Pydantic models from
    the openai SDK preserve unknown xAI fields via ``extra='allow'``,
    so the xAI-specific names land on the model alongside the
    OpenAI-standard ones).  Returns 0 when none of the names are
    present or carry a usable integer.
    """
    for name in names:
        value = getattr(usage, name, None)
        if isinstance(value, int) and value > 0:
            return value
    return 0


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
