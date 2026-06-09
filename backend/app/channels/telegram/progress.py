"""Multi-state progress renderers for Telegram streaming turns.

Centralises all the transient progress HTML snippets that appear while
the agent is computing a reply. Every function returns a Telegram HTML
string; callers route to ``safe_edit_html`` (legacy) or
``safe_send_draft`` (draft streaming) as appropriate.

State machine (used by the content-preview placeholder logic):
  INITIAL  → ``render_initial()``
  STARTING → ``render_starting(model, tool_count)``    (first event, model known)
  WORKING  → ``render_working(preview)``               (first text delta)
  Tool path uses Claude Code TUI-style ``⏺ Tool(detail)`` lines with
  optional ``⎿`` result previews rather than the WORKING state.
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
    """Return HTML for in-flight tool calls in Claude Code TUI style.

    Args:
        tool_names: Display names (already formatted) for in-flight tools.

    Returns:
        Telegram HTML string.
    """
    if not tool_names:
        return "⏺ Tool"
    return "\n".join(html.escape(n) for n in tool_names)


MAX_TOOL_TRACE_CHARS = 3600


def render_bounded_tools_block(header: str, lines: list[str]) -> str:
    """Join complete Telegram HTML fragments without cutting tags."""
    output = header
    for line in lines:
        candidate = f"{output}\n{line}" if output else line
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
            Kept for the call contract; Claude Cage-style rendering does
            not show timings in chat.
        result_preview: Optional compact stdout/result preview to show under
            the completed tool row.

    Returns:
        Telegram HTML string for one tool line.
    """
    del elapsed_ms
    line = html.escape(tool_display)
    preview = _format_tool_result_preview(result_preview or "")
    if not preview:
        return line
    return f"{line}\n{html.escape(preview)}"


TOOL_PROGRESS_PREVIEW_MAX_CHARS = 500


def render_tool_progress(tool_display: str, result_preview: str) -> str:
    """Return HTML for a still-running tool with a compact progress preview."""
    line = html.escape(tool_display)
    preview = _format_tool_result_preview(result_preview, max_chars=TOOL_PROGRESS_PREVIEW_MAX_CHARS)
    if not preview:
        return line
    return f"{line}\n{html.escape(preview)}"


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
    msg = error_message.strip()
    if len(msg) > TOOL_ERROR_MAX_CHARS:
        msg = msg[:TOOL_ERROR_MAX_CHARS] + "…"
    return f"{html.escape(tool_display)}\n  ⎿ ✗ {html.escape(msg)}"


def render_thinking_in_progress() -> str:
    """Return HTML for the 'thinking' state placeholder."""
    return "✻ thinking"


def _format_tool_result_preview(
    text: str, *, max_chars: int = TOOL_RESULT_PREVIEW_MAX_CHARS
) -> str:
    """Return Claude Code TUI-style one-line result preview."""
    stripped = text.strip()
    if not stripped:
        return ""
    first = stripped.splitlines()[0].strip()
    if len(first) > max_chars:
        first = f"{first[: max_chars - 1].rstrip()}…"
    extra_lines = stripped.count("\n")
    suffix = f"  (+{extra_lines} lines)" if extra_lines else ""
    return f"  ⎿ {first}{suffix}"
