"""Inline-keyboard helpers for the interactive ``/status`` panel (#361).

The existing ``/status`` slash command (in :mod:`status`) builds one
monolithic Telegram reply with every diagnostic — gateway uptime,
model, verbose level, thinking level, conversation token/cost,
running state, etc. For users who only want one section (e.g. "is my
LCM caught up?") that's noisy and burns the conversation transcript.

This module owns the framework-free shape of the new interactive
variant: a small set of named panels (system / conversation / tools /
LCM / commands) each backed by a callback. The aiogram glue + the
per-panel formatters land in :mod:`status_picker_runtime` so this
module stays unit-testable without the optional ``[telegram]`` extra.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

STATUS_CALLBACK_PREFIX = "sts:"
_BUTTONS_PER_ROW = 2
_CALLBACK_PARTS = 2  # sts:<panel>


class StatusPanel(StrEnum):
    """Diagnostic panels the interactive status keyboard exposes.

    Each value is its own callback discriminator (``sts:<value>``) so
    the dispatcher only needs prefix matching. The order here is the
    display order in the keyboard.
    """

    SYSTEM = "sys"
    """Gateway uptime, default model, dev-mode flag, etc."""
    CONVERSATION = "cnv"
    """Per-conversation summary: model, verbose, thinking, run-state."""
    USAGE = "use"
    """Tokens + cost ledger for the current conversation."""
    TOOLS = "tls"
    """Tool inventory for the active model."""
    LCM = "lcm"
    """Long-context memory pull / push status."""
    COMMANDS = "cmd"
    """The slash-command surface the user can invoke."""


# Each panel's display label. Kept here so the picker module owns
# the entire user-facing copy and stays import-cycle-free relative
# to the runtime that actually renders the panel body.
_PANEL_LABELS: dict[StatusPanel, str] = {
    StatusPanel.SYSTEM: "🌐 System",
    StatusPanel.CONVERSATION: "💬 Conversation",
    StatusPanel.USAGE: "📊 Usage",
    StatusPanel.TOOLS: "🔧 Tools",
    StatusPanel.LCM: "🧠 LCM",
    StatusPanel.COMMANDS: "📋 Commands",
}


@dataclass(frozen=True)
class StatusButton:
    """One inline-keyboard button on the status picker."""

    text: str
    callback_data: str


@dataclass(frozen=True)
class StatusCallback:
    """Parsed callback payload for the status picker."""

    panel: StatusPanel


def build_status_keyboard() -> list[list[StatusButton]]:
    """Build the two-column status picker keyboard.

    Two columns mirrors the model picker's host screen — the buttons
    are short enough that two per row fits on phones without
    truncation. Order matches :class:`StatusPanel`'s declaration so
    rearranging the enum rearranges the keyboard.
    """
    rows: list[list[StatusButton]] = []
    current_row: list[StatusButton] = []
    for panel in StatusPanel:
        current_row.append(
            StatusButton(text=_PANEL_LABELS[panel], callback_data=_panel_callback(panel))
        )
        if len(current_row) == _BUTTONS_PER_ROW:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    return rows


def status_picker_header() -> str:
    """Render the header copy shown above the keyboard."""
    return "📊 Status\n\nPick a panel to inspect."


def parse_status_callback_data(data: str | None) -> StatusCallback | None:
    """Parse a ``sts:<panel>`` payload back into a :class:`StatusCallback`.

    Returns ``None`` for any malformed payload (wrong prefix, missing
    panel discriminator, unknown panel value) so callers can surface a
    stale-callback notice without raising.
    """
    if data is None or not data.startswith(STATUS_CALLBACK_PREFIX):
        return None
    parts = data.split(":", maxsplit=1)
    if len(parts) != _CALLBACK_PARTS:
        return None
    raw_panel = parts[1]
    try:
        panel = StatusPanel(raw_panel)
    except ValueError:
        return None
    return StatusCallback(panel=panel)


def panel_label(panel: StatusPanel) -> str:
    """Return the human-readable label for ``panel``.

    Useful from the runtime so the ack text on the callback
    (``callback.answer(...)``) reads as ``"System ✓"`` rather than
    the discriminator slug.
    """
    return _PANEL_LABELS[panel]


def _panel_callback(panel: StatusPanel) -> str:
    return f"{STATUS_CALLBACK_PREFIX}{panel.value}"


__all__ = [
    "STATUS_CALLBACK_PREFIX",
    "StatusButton",
    "StatusCallback",
    "StatusPanel",
    "build_status_keyboard",
    "panel_label",
    "parse_status_callback_data",
    "status_picker_header",
]
