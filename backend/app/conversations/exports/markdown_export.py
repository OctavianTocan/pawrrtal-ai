"""Render a conversation as a single Markdown document.

Format mirrors CCT's session-export so a Pawrrtal export drops into
the same downstream tooling without per-row mapping.  Layout:

* Header — conversation ID, title, created/updated timestamps,
  message count
* One ``### {Role} — {timestamp}`` block per message, with
  optional thinking / tool_calls subsections (when present in the
  persisted row)
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.conversations.exports.types import ConversationLike, MessageLike

# Truncate long tool-call results to keep the export readable.
# Anything longer is replaced with the head + an ellipsis.
_TOOL_RESULT_PREVIEW_CHARS = 200


def render_markdown(
    *,
    conversation: ConversationLike,
    messages: Sequence[MessageLike],
) -> str:
    """Return a self-contained Markdown export of the conversation."""
    lines: list[str] = []
    lines.append(f"# {conversation.title or 'Conversation'}")
    lines.append("")
    lines.append(f"**Conversation ID:** `{conversation.id}`")
    lines.append(f"**Created:** {_fmt_dt(conversation.created_at)}")
    lines.append(f"**Updated:** {_fmt_dt(conversation.updated_at)}")
    if conversation.model_id:
        lines.append(f"**Model:** `{conversation.model_id}`")
    lines.append(f"**Message count:** {len(messages)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for message in messages:
        lines.extend(_render_message(message))
        lines.append("---")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_message(message: MessageLike) -> list[str]:
    """Render one message as a Markdown block."""
    role_label = "You" if message.role == "user" else "Assistant"
    timestamp = _fmt_dt(message.created_at)
    out: list[str] = [f"### {role_label} — {timestamp}", ""]
    body = (message.content or "").strip()
    if body:
        out.append(body)
        out.append("")
    if message.thinking:
        out.append("<details><summary>Reasoning</summary>")
        out.append("")
        out.append(message.thinking.strip())
        out.append("")
        out.append("</details>")
        out.append("")
    if message.tool_calls:
        out.extend(_render_tool_calls(message.tool_calls))
    if message.attachment:
        mime = message.attachment_mime or "application/octet-stream"
        out.append(f"📎 **Attachment:** `{message.attachment}` ({mime})")
        out.append("")
    return out


def _render_tool_calls(tool_calls: list[dict[str, Any]]) -> list[str]:
    """Render the tool-call list as a bulleted breakdown."""
    out: list[str] = ["**Tool calls**", ""]
    for call in tool_calls:
        name = call.get("name", "tool")
        status = call.get("status", "pending")
        out.append(f"- `{name}` — {status}")
        result = call.get("result")
        if result:
            preview = (
                result
                if len(result) <= _TOOL_RESULT_PREVIEW_CHARS
                else result[:_TOOL_RESULT_PREVIEW_CHARS] + "…"
            )
            out.append(f"  - result: {preview}")
    out.append("")
    return out


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "(unknown)"
    return value.isoformat(timespec="seconds")
