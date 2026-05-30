"""xai-sdk streaming helpers — translate ``Chunk`` / ``Response`` → LLMEvents.

Pulled out of ``xai_provider`` so the provider module stays under the
500-line file budget.  All helpers are pure shape translation; the live
gRPC client lives in ``xai_provider``.

xai-sdk does the hard work for us: ``chat.stream()`` yields
``(response, chunk)`` tuples where ``chunk`` carries the latest deltas
and ``response`` carries the running-total accumulation, exposed via
typed accessors (``content``, ``reasoning_content``, ``tool_calls``,
``usage``, ``cost_usd``, ``finish_reason``).  See:
https://github.com/xai-org/xai-sdk-python/blob/main/src/xai_sdk/chat.py
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from xai_sdk.chat import Chunk, Response

from app.agents.types import (
    LLMDoneEvent,
    LLMToolCallEvent,
    TextContent,
    ToolCallContent,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChunkDeltas:
    """The user-visible deltas extracted from one streaming chunk.

    ``text`` is the regular assistant content delta; ``thinking`` is the
    reasoning-trace delta (xAI's ``reasoning_content`` field on grok-4.3
    reasoning turns).  Either or both may be ``None`` when the chunk
    only contributed tool-call payloads or terminal usage metadata.
    """

    text: str | None = None
    thinking: str | None = None


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """Per-request usage snapshot read off the SDK's terminal :class:`Response`.

    Mirrors the shape Pawrrtal's chat aggregator expects on
    ``StreamEvent(type="usage")`` so :class:`XaiLLM.stream` can yield
    it without further translation.  ``cost_usd`` comes from the SDK's
    ``Response.cost_usd`` property (server-reported, authoritative).
    """

    input_tokens: int
    output_tokens: int
    cost_usd: float


def deltas_from_chunk(chunk: Chunk) -> ChunkDeltas:
    """Pull the text / reasoning deltas off one streaming chunk.

    Both fields can be empty strings when the chunk only carries
    tool-call payloads or finish-reason metadata; we normalise empty
    strings to ``None`` so the caller can branch on truthiness.
    """
    text = chunk.content or None
    thinking = chunk.reasoning_content or None
    return ChunkDeltas(text=text, thinking=thinking)


def tool_call_events_from_response(response: Response) -> list[LLMToolCallEvent]:
    """Translate the final ``Response.tool_calls`` into loop-shaped events.

    Reading from the accumulated :class:`Response` (rather than from
    streamed chunks) sidesteps the question of whether xAI ships each
    tool call in a single chunk or spread across several — the SDK
    accumulates either way, and emitting once at end-of-stream is the
    only point at which we know we have the complete list.
    """
    events: list[LLMToolCallEvent] = []
    for ordinal, call in enumerate(response.tool_calls):
        events.append(
            LLMToolCallEvent(
                type="tool_call",
                tool_call_id=_stable_tool_call_id(call, ordinal),
                name=call.function.name,
                arguments=_parse_arguments(call.function.arguments, call.function.name),
            )
        )
    return events


def done_event_from_response(response: Response) -> LLMDoneEvent:
    """Assemble the terminal ``LLMDoneEvent`` from the accumulated response.

    The loop uses ``stop_reason`` purely as a string discriminator
    (``"tool_use"`` vs ``"stop"`` vs ``"error"``) — see
    ``app.agents.loop._should_stop``.  We map xAI's
    ``REASON_TOOL_CALLS`` to ``"tool_use"`` so a tool-using turn
    triggers the loop's tool-dispatch path, and everything else falls
    through to ``"stop"``.
    """
    content: list[TextContent | ToolCallContent] = []
    if response.content:
        content.append(TextContent(type="text", text=response.content))
    for ordinal, call in enumerate(response.tool_calls):
        content.append(
            ToolCallContent(
                type="toolCall",
                tool_call_id=_stable_tool_call_id(call, ordinal),
                name=call.function.name,
                arguments=_parse_arguments(call.function.arguments, call.function.name),
            )
        )
    finish = (response.finish_reason or "").upper()
    stop_reason = "tool_use" if response.tool_calls or finish == "REASON_TOOL_CALLS" else "stop"
    return LLMDoneEvent(type="done", stop_reason=stop_reason, content=content)


def usage_record_from_response(response: Response) -> UsageRecord | None:
    """Read token + cost totals off the SDK's accumulated response.

    Returns ``None`` when the server reported nothing useful (token
    counts all zero and cost missing) — the chat aggregator then
    treats the turn as a free no-op rather than logging a zero-cost
    ledger row.  ``response.cost_usd`` is the authoritative
    server-reported figure (the SDK does the ``cost_in_usd_ticks``
    conversion for us via :mod:`xai_sdk.cost`), so we don't carry
    the constant locally.
    """
    usage = response.usage
    input_tokens = int(getattr(usage, "prompt_tokens", 0))
    output_tokens = int(getattr(usage, "completion_tokens", 0))
    cost = response.cost_usd
    if input_tokens == 0 and output_tokens == 0 and cost is None:
        return None
    return UsageRecord(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=float(cost) if cost is not None else 0.0,
    )


class UsageAccumulator:
    """Per-request usage totals summed across every StreamFn invocation.

    The agent loop calls the StreamFn once per assistant turn (LLM →
    tool → LLM round-trip), so a single user prompt can drive several
    chat-completions requests.  Each request finishes with its own
    :class:`Response` that carries usage; we sum them so the chat
    aggregator sees the total for the whole turn (same shape Claude
    emits via ``_build_usage_event``).

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

    def absorb(self, record: UsageRecord | None) -> None:
        """Fold a per-request :class:`UsageRecord` into the running totals."""
        if record is None:
            return
        self.saw_any = True
        self.input_tokens += record.input_tokens
        self.output_tokens += record.output_tokens
        self.cost_usd += record.cost_usd


def _stable_tool_call_id(call: Any, ordinal: int) -> str:
    """Return the server-provided tool_call_id, or synthesise a stable one.

    xai-sdk always populates ``call.id``, but synthesising a fallback
    keeps the helper robust if a future SDK version emits empty ids
    on partial / dropped streams.
    """
    server_id = getattr(call, "id", "") or ""
    if server_id:
        return server_id
    name = getattr(call.function, "name", "") or "unknown"
    return f"call-{name}-{ordinal}-{uuid.uuid4().hex[:8]}"


def _parse_arguments(raw: str, name: str) -> dict[str, Any]:
    """Parse a tool call's ``arguments`` JSON string into a dict.

    xai-sdk ships ``arguments`` as a JSON string for OpenAI
    compatibility.  An empty / missing arguments object is legitimate
    for tools that take no parameters, so ``""`` becomes ``{}``.
    Malformed JSON is logged at WARNING and surfaced as an empty dict
    — the agent loop will dispatch the tool and surface the resulting
    error, which is more informative than crashing the stream.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "xai_provider: tool '%s' returned non-JSON arguments (%s); falling back to {}",
            name,
            exc,
        )
        return {}
    return parsed if isinstance(parsed, dict) else {}
