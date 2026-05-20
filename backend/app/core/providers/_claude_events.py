"""Translate Claude Agent SDK ``Message`` instances into ``StreamEvent`` dicts.

Pure projection: SDK message types in, ``StreamEvent`` dicts out.  Lives
in its own module so :mod:`app.core.providers.claude_provider` stays
under the project's 500-line file budget — the events surface is large
enough on its own (``AssistantMessage``, ``UserMessage``,
``ResultMessage``, ``RateLimitEvent``, ``SystemMessage``) that splitting
it pays for itself in readability too.

Dispatch is **table-based** rather than a chain of ``isinstance`` arms,
so each translator stays under the project's 3-level nesting budget
without paying for the indirection ``functools.singledispatch`` would
add.  All public names (the underscore-prefixed helpers below) are
re-exported from ``claude_provider`` so existing import sites and tests
keep working.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    RateLimitEvent,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from app.core.agent_loop.display import ToolDisplay, render_display_from_map

from .base import StreamEvent

logger = logging.getLogger(__name__)


def _events_from_message(
    message: Any,
    display_by_name: dict[str, ToolDisplay] | None = None,
) -> Iterator[StreamEvent]:
    """Translate a single Claude SDK ``Message`` into zero or more ``StreamEvent``s.

    Dispatches on the message type through ``_MESSAGE_HANDLERS`` so the
    body stays at one level of nesting; each handler is a module-level
    helper that owns its own surface.
    """
    if isinstance(message, AssistantMessage):
        yield from _events_from_assistant(message, display_by_name or {})
        return
    handler = _MESSAGE_HANDLERS.get(type(message))
    if handler is None:
        return
    yield from handler(message)


def _events_from_assistant(
    message: AssistantMessage,
    display_by_name: dict[str, ToolDisplay] | None = None,
) -> Iterator[StreamEvent]:
    """Project an assistant message's content blocks into ``StreamEvent``s."""
    for block in message.content:
        event = _event_from_block(block, display_by_name or {})
        if event is not None:
            yield event
    if message.error:
        yield _error_event(f"Assistant message reported an error: {message.error}")


def _events_from_user(message: UserMessage) -> Iterator[StreamEvent]:
    """``UserMessage`` in the live stream carries tool results.

    Surface the tool roundtrip so the frontend can render it; ignore
    plain echo blocks.
    """
    if not isinstance(message.content, list):
        return
    for block in message.content:
        if isinstance(block, ToolResultBlock):
            yield _tool_result_event(block)


def _events_from_result(message: ResultMessage) -> Iterator[StreamEvent]:
    """Surface SDK errors + emit a ``usage`` event for the cost ledger.

    PR 04: ``ResultMessage`` is the SDK's terminating envelope for one
    turn.  It carries ``total_cost_usd`` (Anthropic's authoritative
    spend) plus token counts (often nested under ``usage`` —
    historically these have moved between SDK versions, so we read
    defensively).  Emit one ``StreamEvent(type="usage")`` per turn so
    the chat aggregator can fold it into the cost-ledger row without
    knowing anything about Claude internals.
    """
    usage_event = _build_usage_event(message)
    if usage_event is not None:
        yield usage_event

    if not message.is_error:
        return
    # Log alongside yielding so the failure shows up in
    # ``backend/app.log`` too.  Previously the only signal was the
    # SSE error panel in the browser, which made tool failures like
    # ``error_max_turns`` invisible to anyone reading backend logs to
    # debug.  Logged at WARNING because the connection is still
    # alive — the chat surface recovers and the user can retry.
    logger.warning(
        "Claude SDK ResultMessage reported error: "
        "stop_reason=%r subtype=%r duration_ms=%s num_turns=%s",
        message.stop_reason,
        message.subtype,
        getattr(message, "duration_ms", None),
        getattr(message, "num_turns", None),
    )
    yield _error_event(
        "Claude SDK result reported an error. "
        f"stop_reason={message.stop_reason!r} subtype={message.subtype!r}"
    )


def _build_usage_event(message: ResultMessage) -> StreamEvent | None:
    """Pull token / cost numbers off a ``ResultMessage``.

    Returns ``None`` when the SDK didn't carry any usage data — happens
    on some error paths and on older CLI versions.  ``input_tokens`` and
    ``output_tokens`` default to 0 (rather than missing keys) so the
    chat aggregator can fold them in unconditionally.
    """
    cost_usd = getattr(message, "total_cost_usd", None)
    usage_blob = getattr(message, "usage", None)
    input_tokens = _read_token_count(usage_blob, "input_tokens")
    output_tokens = _read_token_count(usage_blob, "output_tokens")

    if cost_usd is None and input_tokens == 0 and output_tokens == 0:
        return None

    return StreamEvent(
        type="usage",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=float(cost_usd) if cost_usd is not None else 0.0,
    )


def _read_token_count(usage_blob: object, key: str) -> int:
    """Read a token count off the SDK's ``usage`` blob (dict or attr).

    The Claude SDK has flipped between exposing usage as a dataclass
    and as a plain dict across versions; tolerate both.
    """
    if usage_blob is None:
        return 0
    value = usage_blob.get(key, 0) if isinstance(usage_blob, dict) else getattr(usage_blob, key, 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _events_from_rate_limit(message: RateLimitEvent) -> Iterator[StreamEvent]:
    """Surface rejection-status rate limits as user-visible errors."""
    if message.rate_limit_info.status == "rejected":
        yield _error_event("Claude API rate limit reached. Please wait and retry.")


def _events_from_system(_message: SystemMessage) -> Iterator[StreamEvent]:
    """``SystemMessage`` carries CLI metadata; not user-visible by default."""
    return
    yield  # pragma: no cover — keeps the function a generator for the dispatch table


# ---------------------------------------------------------------------------
# Block-level translation
# ---------------------------------------------------------------------------


def _block_to_text(block: TextBlock) -> StreamEvent:
    return StreamEvent(type="delta", content=block.text)


def _block_to_thinking(block: ThinkingBlock) -> StreamEvent:
    return StreamEvent(type="thinking", content=block.thinking)


def _block_to_tool_use(
    block: ToolUseBlock,
    display_by_name: dict[str, ToolDisplay] | None = None,
) -> StreamEvent:
    return StreamEvent(
        type="tool_use",
        name=block.name,
        input=block.input,
        tool_use_id=block.id,
        display=render_display_from_map(display_by_name or {}, block.name, block.input),
    )


def _event_from_block(
    block: object,
    display_by_name: dict[str, ToolDisplay] | None = None,
) -> StreamEvent | None:
    """Dispatch a single content-block instance to its translator.

    Returns ``None`` for unknown block types so the caller can skip
    them without growing a branch.
    """
    if isinstance(block, ToolUseBlock):
        return _block_to_tool_use(block, display_by_name)
    handler = _BLOCK_HANDLERS.get(type(block))
    if handler is None:
        return None
    return handler(block)


def _tool_result_event(block: ToolResultBlock) -> StreamEvent:
    # ``ToolResultBlock.is_error`` is ``bool | None`` per the SDK; coerce to
    # bool with ``False`` as the default so the StreamEvent shape stays
    # consumable by the Telegram dispatcher without a None check.
    return StreamEvent(
        type="tool_result",
        tool_use_id=block.tool_use_id,
        content=_tool_result_to_text(block.content),
        is_error=bool(block.is_error),
    )


def _tool_result_to_text(content: object) -> str:
    """Render ``ToolResultBlock.content`` as plain text for the SSE event."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_render_content_item(item) for item in content)
    return str(content)


def _render_content_item(item: object) -> str:
    """Render a single element of a ``ToolResultBlock.content`` list."""
    if not isinstance(item, dict):
        return str(item)
    # Anthropic's tool-result format uses ``{"type": "text", "text": "..."}``.
    text = item.get("text")
    if item.get("type") == "text" and isinstance(text, str):
        return text
    return str(item)


def _error_event(message: str) -> StreamEvent:
    return StreamEvent(type="error", content=message)


# ---------------------------------------------------------------------------
# Dispatch tables (declared at the bottom so the handlers above are bound)
# ---------------------------------------------------------------------------

_MessageHandler = Callable[[Any], Iterator[StreamEvent]]
_BlockHandler = Callable[[Any], StreamEvent]

_MESSAGE_HANDLERS: dict[type, _MessageHandler] = {
    AssistantMessage: _events_from_assistant,
    UserMessage: _events_from_user,
    ResultMessage: _events_from_result,
    RateLimitEvent: _events_from_rate_limit,
    SystemMessage: _events_from_system,
}

_BLOCK_HANDLERS: dict[type, _BlockHandler] = {
    TextBlock: _block_to_text,
    ThinkingBlock: _block_to_thinking,
    ToolUseBlock: _block_to_tool_use,
    ToolResultBlock: _tool_result_event,
}
