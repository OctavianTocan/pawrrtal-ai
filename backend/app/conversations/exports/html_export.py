"""Render a conversation as a minimal styled HTML document.

Self-contained — no external CSS or JS — so a download opens
correctly without any infrastructure.  HTML escaping is deliberate
on every untrusted field so a tool result containing ``<script>``
can't ride the export into the recipient's browser.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from html import escape
from typing import Any

from app.conversations.exports.types import ConversationLike, MessageLike

_STYLE = """
body { font-family: 'Inter', system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; color: #222; }
header { border-bottom: 1px solid #ccc; padding-bottom: 1rem; margin-bottom: 1rem; }
.message { border-left: 3px solid #ddd; padding: 0.5rem 1rem; margin: 1rem 0; }
.message.user { border-color: #4a90e2; }
.message.assistant { border-color: #9b59b6; }
.role { font-weight: 600; }
.timestamp { color: #888; font-size: 0.85rem; margin-left: 0.5rem; }
pre { background: #f6f8fa; padding: 0.75rem; border-radius: 6px; overflow-x: auto; }
.thinking { background: #fafafa; border: 1px dashed #ccc; padding: 0.5rem 0.75rem; margin-top: 0.5rem; font-size: 0.9rem; color: #555; }
.tool-call { font-family: monospace; font-size: 0.85rem; color: #444; }
""".strip()


def render_html(
    *,
    conversation: ConversationLike,
    messages: Sequence[MessageLike],
) -> str:
    """Return a self-contained HTML document for the conversation."""
    title = escape(conversation.title or "Conversation")
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head>',
        '<meta charset="utf-8">',
        f"<title>{title}</title>",
        f"<style>{_STYLE}</style>",
        "</head><body>",
        "<header>",
        f"<h1>{title}</h1>",
        f"<p>Conversation ID: <code>{escape(str(conversation.id))}</code></p>",
        f"<p>Created: {_fmt_dt(conversation.created_at)}</p>",
        f"<p>Updated: {_fmt_dt(conversation.updated_at)}</p>",
    ]
    if conversation.model_id:
        parts.append(f"<p>Model: <code>{escape(conversation.model_id)}</code></p>")
    parts.append(f"<p>Messages: {len(messages)}</p>")
    parts.append("</header>")
    parts.append("<main>")
    parts.extend(_render_message(message) for message in messages)
    parts.append("</main></body></html>")
    return "\n".join(parts)


def _render_message(message: MessageLike) -> str:
    """Render one message as an HTML block."""
    role = escape(message.role)
    label = "You" if message.role == "user" else "Assistant"
    body = escape(message.content or "")
    timestamp = _fmt_dt(message.created_at)
    blocks: list[str] = [
        f'<section class="message {role}">',
        f'<div class="role">{label}<span class="timestamp">{timestamp}</span></div>',
    ]
    if body:
        blocks.append(f"<pre>{body}</pre>")
    if message.thinking:
        blocks.append(
            f'<div class="thinking"><strong>Reasoning</strong><br>'
            f"<pre>{escape(message.thinking)}</pre></div>"
        )
    if message.tool_calls:
        blocks.append(_render_tool_calls(message.tool_calls))
    if message.attachment:
        mime = escape(message.attachment_mime or "application/octet-stream")
        blocks.append(f"<p>📎 Attachment: <code>{escape(message.attachment)}</code> ({mime})</p>")
    blocks.append("</section>")
    return "\n".join(blocks)


def _render_tool_calls(tool_calls: list[dict[str, Any]]) -> str:
    """Render the tool-call list as a bulleted block."""
    items: list[str] = []
    for call in tool_calls:
        name = escape(str(call.get("name", "tool")))
        status = escape(str(call.get("status", "pending")))
        items.append(f'<li class="tool-call">{name} — {status}</li>')
    return "<ul>" + "".join(items) + "</ul>"


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "(unknown)"
    return escape(value.isoformat(timespec="seconds"))
