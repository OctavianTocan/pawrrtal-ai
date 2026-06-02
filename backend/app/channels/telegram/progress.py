"""Multi-state progress renderers for Telegram streaming turns.

Centralises all the transient progress HTML snippets that appear while
the agent is computing a reply. Every function returns a Telegram HTML
string; callers route to ``safe_edit_html`` (legacy) or
``safe_send_draft`` (draft streaming) as appropriate.

State machine (used by the content-preview placeholder logic):
  INITIAL  → ``render_initial()``
  STARTING → ``render_starting(model, tool_count)``    (first event, model known)
  WORKING  → ``render_working(preview)``               (first text delta)
  Tool path uses ``render_tools_in_flight`` + ``render_tool_success``
  / ``render_tool_error`` rather than the WORKING state.
"""

from __future__ import annotations

import html
from enum import StrEnum

# ---------------------------------------------------------------------------
# Progress state machine
# ---------------------------------------------------------------------------


class ProgressState(StrEnum):
    """States for the content-preview-in-placeholder state machine."""

    INITIAL = "initial"
    STARTING = "starting"
    WORKING = "working"
    TOOLS_RUNNING = "tools_running"
    THINKING = "thinking"


# Maximum characters of preview text shown inside ``render_working``.
PREVIEW_MAX_CHARS = 150


# ---------------------------------------------------------------------------
# Static progress renderers
# ---------------------------------------------------------------------------


def render_initial() -> str:
    """Return the initial placeholder HTML shown before any event arrives."""
    return "🤔 Processing your request..."


def render_transient_status(status: str) -> str:
    """Return HTML for a short-lived provider progress status."""
    text = html.escape(status.strip() or "Working")
    return f"🤔 <b>{text}</b>"


def render_starting(model: str, tool_count: int) -> str:
    """Return HTML for the 'starting' state — model known, first event received.

    Args:
        model: Human-readable model identifier (will be HTML-escaped).
        tool_count: Number of tools available this turn (may be 0).

    Returns:
        Telegram HTML string.
    """
    esc_model = html.escape(str(model))
    tools_clause = f" with {tool_count} tool{'s' if tool_count != 1 else ''} available"
    if tool_count == 0:
        tools_clause = ""
    return f"🚀 <b>Starting {esc_model}</b>{html.escape(tools_clause)}"


def render_working(preview: str) -> str:
    """Return HTML for the 'working' state — text delta preview.

    Truncates the preview to ``PREVIEW_MAX_CHARS`` chars and appends
    an ellipsis when truncated. HTML-escapes all user/model content.

    Args:
        preview: Accumulated text delta so far.

    Returns:
        Telegram HTML string.
    """
    text = preview.strip()
    if len(text) > PREVIEW_MAX_CHARS:
        text = text[:PREVIEW_MAX_CHARS] + "…"
    esc_preview = html.escape(text)
    return f"🤖 <b>Working...</b>\n\n<i>{esc_preview}</i>"


def render_tools_in_flight(tool_names: list[str]) -> str:
    """Return HTML for the 'tools running' state — list of tool names.

    Args:
        tool_names: Display names (already formatted) for in-flight tools.

    Returns:
        Telegram HTML string.
    """
    if not tool_names:
        return "🔧 <b>Using tools...</b>"
    esc_names = "\n".join(f"  {html.escape(n)}" for n in tool_names)
    return f"🔧 <b>Using tools:</b>\n{esc_names}"


MAX_TOOL_TRACE_CHARS = 3600


def render_bounded_tools_block(header: str, lines: list[str]) -> str:
    """Join complete Telegram HTML fragments without cutting tags."""
    output = header
    for line in lines:
        candidate = f"{output}\n\n{line}"
        if len(candidate) > MAX_TOOL_TRACE_CHARS:
            continue
        output = candidate
    return output


TOOL_RESULT_PREVIEW_MAX_CHARS = 700


def render_tool_success(
    tool_display: str,
    elapsed_ms: int,
    result_preview: str | None = None,
) -> str:
    """Return HTML for a completed tool call — success path.

    Args:
        tool_display: Display text for this tool call (already formatted,
            may include icon + label; will NOT be re-escaped here since
            ``format_tool_use`` in ``telegram_delivery.py`` already produces
            display-safe text).
        elapsed_ms: Wall-clock duration of the tool call in milliseconds.
        result_preview: Optional compact stdout/result preview to show under
            the completed tool row.

    Returns:
        Telegram HTML string for one tool line.
    """
    esc = html.escape(tool_display)
    line = f"✅ <b>{esc}</b> ({elapsed_ms}ms)"
    preview = (result_preview or "").strip()
    if not preview:
        return line
    if len(preview) > TOOL_RESULT_PREVIEW_MAX_CHARS:
        preview = preview[:TOOL_RESULT_PREVIEW_MAX_CHARS].rstrip()
    esc_preview = html.escape(preview)
    return f"{line}\n\n<code>{esc_preview}</code>"


TOOL_PROGRESS_PREVIEW_MAX_CHARS = 500


def render_tool_progress(tool_display: str, result_preview: str) -> str:
    """Return HTML for a still-running tool with a compact progress preview."""
    esc = html.escape(tool_display)
    preview = result_preview.strip()
    if len(preview) > TOOL_PROGRESS_PREVIEW_MAX_CHARS:
        preview = preview[:TOOL_PROGRESS_PREVIEW_MAX_CHARS].rstrip()
    esc_preview = html.escape(preview)
    if not esc_preview:
        return f"⏳ <b>{esc}</b>"
    return f"⏳ <b>{esc}</b>\n\n<code>{esc_preview}</code>"


# Maximum characters of error text shown in a tool error card.
TOOL_ERROR_MAX_CHARS = 200


def render_tool_error(tool_display: str, error_message: str) -> str:
    """Return HTML for a failed tool call — error path.

    Args:
        tool_display: Display text for this tool call (will be HTML-escaped).
        error_message: Error detail (will be HTML-escaped and truncated).

    Returns:
        Telegram HTML string for one tool line.
    """
    esc_tool = html.escape(tool_display)
    msg = error_message.strip()
    if len(msg) > TOOL_ERROR_MAX_CHARS:
        msg = msg[:TOOL_ERROR_MAX_CHARS] + "…"
    esc_msg = html.escape(msg)
    return f"❌ <b>{esc_tool}</b>\n\n<i>{esc_msg}</i>"


def render_thinking_in_progress() -> str:
    """Return HTML for the 'thinking' state placeholder."""
    return "💭 <b>Thinking...</b>"
