"""Emoji glyph map for tool names — surfaced inline in Telegram streams.

Ported from claude-code-telegram (``src/bot/orchestrator.py:_TOOL_ICONS``)
and extended for the Pawrrtal tool surface.  When the model invokes a
tool mid-turn, the Telegram channel injects a one-line glyph + tool
name into the live edit stream so the user sees what the agent is
doing in real time.

Used by:

* :class:`TelegramChannel.deliver` (PR 07) — appends a line per
  ``tool_use`` event.
* The verbose filter (PR 07) — at level 0 the glyph is suppressed
  entirely; at level 1 it shows the bare name; at level 2 it shows
  the redacted input shape too.
"""

from __future__ import annotations

# Default glyph when a tool isn't in the map.  Wrench reads as
# "something is happening" without committing to a category.
_DEFAULT_GLYPH = "\U0001f527"

# Map keyed on the bare tool name (without the Claude SDK
# ``mcp__pawrrtal__`` prefix — the bridge strips that before our
# permission gate sees the name, and the channel layer matches the
# same convention).  Mostly Claude-SDK names + the Pawrrtal-native
# tool factories that ship in the chat router.
_TOOL_ICONS: dict[str, str] = {
    # Claude SDK built-ins (only fired when sandbox / tool whitelist
    # is loosened — kept here so a deployment that opts into them
    # gets pretty glyphs without an extra edit).
    "Read": "\U0001f4d6",
    "Write": "✏️",
    "Edit": "✏️",
    "MultiEdit": "✏️",
    "Bash": "\U0001f4bb",
    "Glob": "\U0001f50d",
    "Grep": "\U0001f50d",
    "LS": "\U0001f4c2",
    "Task": "\U0001f9e0",
    "TaskOutput": "\U0001f9e0",
    "WebFetch": "\U0001f310",
    "WebSearch": "\U0001f310",
    "terminal": "\U0001f4bb",
    "search_files": "\U0001f50e",
    "NotebookRead": "\U0001f4d3",
    "NotebookEdit": "\U0001f4d3",
    "TodoRead": "☑️",
    "TodoWrite": "☑️",
    # Pawrrtal-native cross-provider tool factories (
    # ``app/core/tools/...``).  Each lands here when the chat router
    # composes them via ``build_agent_tools``.
    "workspace_read": "\U0001f4d6",
    "read_file": "\U0001f4d6",
    "workspace_write": "✏️",
    "workspace_list": "\U0001f4c2",
    "list_dir": "\U0001f4c2",
    "exa_search": "\U0001f310",
    "render_artifact": "\U0001f9e9",
    "image_gen": "\U0001f3a8",
    "send_message": "\U0001f4e8",
    "notion_cli": "\U0001f4d3",
}


def tool_icon(name: str) -> str:
    """Return the glyph for ``name`` or the default wrench."""
    return _TOOL_ICONS.get(name, _DEFAULT_GLYPH)
