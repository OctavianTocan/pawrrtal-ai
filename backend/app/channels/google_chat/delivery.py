"""Progressive streaming delivery for the Google Chat channel.

Mirrors the Telegram channel's debounced-edit model (``channel.py`` +
``dispatch.py`` there): instead of a single final patch, the placeholder
message is patched repeatedly as the turn streams, so the user watches
the answer — and, at higher verbosity, the tool calls and thinking —
build in place.

Google Chat exposes no streaming/typing API; the only progressive
mechanism is repeated ``messages.patch``. We debounce to at most one
patch per :data:`_MIN_PATCH_INTERVAL_S`, and only when the rendered text
actually changed, to stay well within the Chat write quota for a single
user. The first event always patches immediately (so the user sees
movement fast), and :meth:`StreamingDelivery.finalize` always writes the
final text.

Verbosity mirrors Telegram's ``/verbose`` levels:

- ``0`` quiet — answer only.
- ``1`` normal — answer plus a compact tool-call trace (the default).
- ``2`` detailed — also surfaces the model's thinking.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from app.providers.base import StreamEvent

from .client import update_message
from .messages import format_for_chat

logger = logging.getLogger(__name__)

VERBOSE_QUIET = 0
VERBOSE_TOOLS = 1
VERBOSE_THINKING = 2
DEFAULT_VERBOSE_LEVEL = VERBOSE_TOOLS

# Debounce floor between progressive patches. Chat patches are heavier
# than Telegram edits, so this is a touch higher than Telegram's 3s/40-char
# pair; the final patch is always sent regardless.
_MIN_PATCH_INTERVAL_S = 1.5

_ERROR_PREFIX = "❌ "
_TERMINATED_PREFIX = "⚠️ "
_EMPTY_RESPONSE_FALLBACK = "⚠️ The agent finished without producing a reply. Please try again."

_MILLIS_PER_SECOND = 1000


@dataclass
class _ToolLine:
    """One row in the streamed tool-call trace."""

    name: str
    started_at: float
    status: str = "running"  # running | done | error
    elapsed_s: float | None = None


@dataclass
class StreamingDelivery:
    """Accumulate stream events and patch one Chat message in place.

    One instance per turn. ``message_name`` is the placeholder the ingress
    pre-created; every patch targets that resource name.
    """

    message_name: str
    verbose_level: int = DEFAULT_VERBOSE_LEVEL
    _answer: str = ""
    _thinking: str = ""
    _last_thinking_block: int | None = None
    _tools: dict[str, _ToolLine] = field(default_factory=dict)
    _tool_order: list[str] = field(default_factory=list)
    _error_text: str | None = None
    _terminated_text: str | None = None
    _last_patch_at: float = 0.0
    _last_rendered: str = ""

    async def on_event(self, event: StreamEvent) -> None:
        """Fold one stream event into state and patch if the debounce allows."""
        if self._accumulate(event):
            await self._maybe_patch()

    async def finalize(self) -> None:
        """Write the final rendered text, bypassing the debounce."""
        rendered = self.render(streaming=False)
        if rendered == self._last_rendered:
            return
        await update_message(message_name=self.message_name, text=rendered)

    def _accumulate(self, event: StreamEvent) -> bool:
        """Update state for one event; return whether a re-render is worthwhile."""
        etype = event.get("type")
        if etype == "delta":
            self._answer += event.get("content") or ""
        elif etype == "thinking":
            self._accumulate_thinking(event)
        elif etype == "tool_use":
            self._start_tool(event)
        elif etype == "tool_result":
            self._finish_tool(event)
        elif etype == "error":
            self._error_text = str(event.get("content") or "Something went wrong.")
        elif etype == "agent_terminated":
            self._terminated_text = str(event.get("content") or "")
        else:
            return False
        return True

    def _accumulate_thinking(self, event: StreamEvent) -> None:
        block = event.get("block_index")
        if self._thinking and block is not None and block != self._last_thinking_block:
            self._thinking += "\n\n"
        if block is not None:
            self._last_thinking_block = block
        self._thinking += event.get("content") or ""

    def _start_tool(self, event: StreamEvent) -> None:
        tid = str(event.get("tool_use_id") or f"t{len(self._tool_order)}")
        if tid not in self._tools:
            self._tool_order.append(tid)
        self._tools[tid] = _ToolLine(
            name=str(event.get("name") or "tool"),
            started_at=time.monotonic(),
        )

    def _finish_tool(self, event: StreamEvent) -> None:
        line = self._tools.get(str(event.get("tool_use_id") or ""))
        if line is None:
            return
        line.status = "error" if event.get("is_error") else "done"
        line.elapsed_s = time.monotonic() - line.started_at

    async def _maybe_patch(self) -> None:
        now = time.monotonic()
        if now - self._last_patch_at < _MIN_PATCH_INTERVAL_S:
            return
        rendered = self.render(streaming=True)
        if not rendered or rendered == self._last_rendered:
            return
        self._last_patch_at = now
        self._last_rendered = rendered
        await update_message(message_name=self.message_name, text=rendered)

    def render(self, *, streaming: bool) -> str:
        """Compose the message text from the accumulated state.

        During streaming an empty render means "leave the placeholder as
        is" (nothing renderable yet); the final render substitutes the
        empty-turn fallback so the placeholder never sits on "Working…".
        """
        if self._error_text is not None:
            return f"{_ERROR_PREFIX}{self._error_text}"
        parts: list[str] = []
        if self.verbose_level >= VERBOSE_THINKING and self._thinking.strip():
            parts.append(f"💭 _Thinking_\n{self._thinking.strip()}")
        if self.verbose_level >= VERBOSE_TOOLS and self._tools:
            parts.append(self._render_tools())
        if self._answer.strip():
            parts.append(format_for_chat(self._answer))
        body = "\n\n".join(part for part in parts if part)
        if streaming:
            return body
        return self._finalize_body(body)

    def _finalize_body(self, body: str) -> str:
        if self._terminated_text:
            body = f"{_TERMINATED_PREFIX}{self._terminated_text}\n\n{body}".strip()
        return body if body.strip() else _EMPTY_RESPONSE_FALLBACK

    def _render_tools(self) -> str:
        lines = ["🔧 *Tools*"]
        for tid in self._tool_order:
            line = self._tools[tid]
            lines.append(f"• {line.name} {_tool_status_suffix(line)}")
        return "\n".join(lines)


def _tool_status_suffix(line: _ToolLine) -> str:
    if line.status == "running":
        return "…"
    glyph = "⚠️" if line.status == "error" else "✓"
    return f"{glyph} ({_fmt_elapsed(line.elapsed_s)})"


def _fmt_elapsed(elapsed_s: float | None) -> str:
    if elapsed_s is None:
        return "…"
    if elapsed_s < 1:
        return f"{int(elapsed_s * _MILLIS_PER_SECOND)}ms"
    return f"{elapsed_s:.1f}s"
