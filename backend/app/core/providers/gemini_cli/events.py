"""Pure helpers that translate ACP session updates into Pawrrtal events.

Extracted from :mod:`app.core.providers.gemini_cli.client` so the
:class:`.client.PawrrtalAcpClient` module stays under the project's
500-line file budget once structured stream logging joined it. All
functions here are pure (no I/O, no side effects beyond ``logger``
calls) and are unit-tested directly via ``test_gemini_cli_provider``.

The split is by concern, not implementation detail:

* ``client.py`` owns the long-lived stateful ACP client class plus the
  one-call helpers it uses directly during request handling
  (``pick_allow_option``).
* This module owns the format-translation surface: each ACP
  ``session/update`` variant in, one Pawrrtal :class:`StreamEvent`
  out (or ``None`` for variants we intentionally drop), plus the
  structured operator-log formatter that fires alongside every update.
"""

from __future__ import annotations

import logging
from typing import Any

from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    AvailableCommandsUpdate,
    ConfigOptionUpdate,
    CurrentModeUpdate,
    EmbeddedResourceContentBlock,
    FileEditToolCallContent,
    ImageContentBlock,
    ResourceContentBlock,
    SessionInfoUpdate,
    TerminalToolCallContent,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    UsageUpdate,
    UserMessageChunk,
)

from app.core.providers.base import StreamEvent

logger = logging.getLogger(__name__)

_LOG_SNIPPET_CHARS = 240


def text_from_content_block(block: object) -> str:
    """Extract text content from any ACP content block, best-effort.

    Returns the empty string for blocks that carry no displayable text
    (audio, binary resources). Used to fold Gemini's streamed
    ``AgentMessageChunk`` payloads into the ``StreamEvent(type="delta")``
    string the chat aggregator + SSE encoder expect.
    """
    if isinstance(block, TextContentBlock):
        return block.text
    if isinstance(block, ImageContentBlock):
        return ""
    if isinstance(block, ResourceContentBlock):
        return block.name or block.uri or ""
    if isinstance(block, EmbeddedResourceContentBlock):
        resource = block.resource
        text_attr = getattr(resource, "text", None)
        return text_attr if isinstance(text_attr, str) else ""
    return ""


def text_from_tool_content_item(item: object) -> str:
    """Render one tool-call content variant as the text we surface to the UI."""
    if isinstance(item, FileEditToolCallContent):
        return f"diff: {item.path}"
    if isinstance(item, TerminalToolCallContent):
        return f"terminal: {item.terminal_id}"
    # Fall through via duck-typing rather than a third isinstance arm so
    # forward-compat ACP schema variants don't silently produce empty
    # output — anything carrying a ``.content`` attribute gets best-effort
    # text extraction.
    inner = getattr(item, "content", None)
    if inner is not None:
        return text_from_content_block(inner)
    return ""


# Editor-UI hint update types we intentionally drop. They have no
# chat-aggregator counterpart in Pawrrtal — add a branch in
# :func:`_stream_event_for_update` when Pawrrtal grows a UI surface
# for any of them.
_DROPPED_UPDATE_TYPES: tuple[type, ...] = (
    AgentPlanUpdate,
    AvailableCommandsUpdate,
    CurrentModeUpdate,
    ConfigOptionUpdate,
    SessionInfoUpdate,
    UserMessageChunk,
)


def _stream_event_for_update(
    update: object,
    display_by_name: dict[str, Any] | None = None,
) -> StreamEvent | None:
    """Map one ACP session-update variant to a Pawrrtal StreamEvent.

    Unknown variants are logged at DEBUG so a future ACP-SDK addition
    becomes debuggable rather than silently lost.
    """
    if isinstance(update, AgentMessageChunk):
        return _delta_or_none("delta", text_from_content_block(update.content))
    if isinstance(update, AgentThoughtChunk):
        return _delta_or_none("thinking", text_from_content_block(update.content))
    if isinstance(update, ToolCallStart):
        return _tool_start_event(update, display_by_name)
    if isinstance(update, ToolCallProgress):
        return _tool_progress_event(update)
    if isinstance(update, UsageUpdate):
        return _usage_event(update)
    if not isinstance(update, _DROPPED_UPDATE_TYPES):
        logger.debug("GEMINI_CLI_UPDATE_DROPPED type=%s", type(update).__name__)
    return None


def _log_session_update(session_id: str, update: object) -> None:
    """Emit a structured operator log for every Gemini CLI ACP update."""
    if isinstance(update, AgentMessageChunk):
        text = text_from_content_block(update.content)
        logger.info(
            "GEMINI_CLI_UPDATE_AGENT_MESSAGE session_id=%s chars=%d snippet=%r",
            session_id,
            len(text),
            _snippet(text),
        )
        return
    if isinstance(update, AgentThoughtChunk):
        text = text_from_content_block(update.content)
        logger.info(
            "GEMINI_CLI_UPDATE_THOUGHT session_id=%s chars=%d snippet=%r",
            session_id,
            len(text),
            _snippet(text),
        )
        return
    if isinstance(update, ToolCallStart):
        raw_input = update.raw_input if isinstance(update.raw_input, dict) else {}
        logger.info(
            "GEMINI_CLI_UPDATE_TOOL_START session_id=%s tool_call_id=%s kind=%s title=%s input_keys=%s",
            session_id,
            update.tool_call_id,
            update.kind,
            update.title,
            sorted(raw_input.keys()),
        )
        return
    if isinstance(update, ToolCallProgress):
        content_count = len(update.content or [])
        logger.info(
            "GEMINI_CLI_UPDATE_TOOL_PROGRESS session_id=%s tool_call_id=%s status=%s content_items=%d",
            session_id,
            update.tool_call_id,
            update.status,
            content_count,
        )
        return
    if isinstance(update, UsageUpdate):
        cost = getattr(update.cost, "amount", None) if update.cost is not None else None
        logger.info(
            "GEMINI_CLI_UPDATE_USAGE session_id=%s used=%s size=%s cost=%s",
            session_id,
            getattr(update, "used", None),
            getattr(update, "size", None),
            cost,
        )
        return
    logger.info(
        "GEMINI_CLI_UPDATE_META session_id=%s type=%s",
        session_id,
        type(update).__name__,
    )


def _snippet(text: str) -> str:
    """Return a single-line, bounded log preview."""
    compact = " ".join(text.split())
    if len(compact) <= _LOG_SNIPPET_CHARS:
        return compact
    return f"{compact[:_LOG_SNIPPET_CHARS]}..."


def _delta_or_none(event_type: str, text: str) -> StreamEvent | None:
    """Build a ``delta`` / ``thinking`` event, or ``None`` if empty."""
    return StreamEvent(type=event_type, content=text) if text else None


def _tool_start_event(
    update: ToolCallStart,
    display_by_name: dict[str, Any] | None = None,
) -> StreamEvent:
    """Translate a ``tool_call`` notification to ``StreamEvent(type=tool_use)``."""
    raw_input = update.raw_input if isinstance(update.raw_input, dict) else {}
    name = update.kind or update.title or "tool"
    event = StreamEvent(
        type="tool_use",
        name=name,
        input=raw_input,
        tool_use_id=update.tool_call_id,
    )
    if display_by_name is not None and name in display_by_name:
        event["display"] = display_by_name[name]
    return event


def _tool_progress_event(update: ToolCallProgress) -> StreamEvent | None:
    """Translate a ``tool_call_update`` notification.

    Only terminal statuses (``completed`` / ``failed``) become user-visible
    ``tool_result`` events; intermediate progress is dropped since the
    chat aggregator already shows a spinner from the ``tool_use`` event.
    """
    if update.status not in {"completed", "failed"}:
        return None
    pieces: list[str] = []
    for item in update.content or []:
        text = text_from_tool_content_item(item)
        if text:
            pieces.append(text)
    body = "\n".join(pieces)
    if update.status == "failed" and not body:
        body = "<tool failed>"
    return StreamEvent(
        type="tool_result",
        content=body,
        tool_use_id=update.tool_call_id,
    )


def _usage_event(update: UsageUpdate) -> StreamEvent | None:
    """Translate a ``usage`` notification into ``StreamEvent(type=usage)``.

    ACP's :class:`UsageUpdate` reports the *current* context window
    state (``size`` total, ``used`` consumed) and an optional
    :class:`Cost` (``amount`` + ``currency``). ``amount`` is cumulative
    per session, not per turn — the chat aggregator therefore treats
    successive usage events as monotonically-increasing totals.
    """
    cost_blob = getattr(update, "cost", None)
    if cost_blob is None:
        return None
    cost_amount = getattr(cost_blob, "amount", None)
    if cost_amount is None:
        return None
    return StreamEvent(type="usage", cost_usd=float(cost_amount))


__all__ = [
    "text_from_content_block",
    "text_from_tool_content_item",
]
