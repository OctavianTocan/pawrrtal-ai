"""Conversation exporters for ``GET /api/v1/conversations/{id}/export``.

Three formats — Markdown (the canonical "human-readable" target),
HTML (browser-friendly), JSON (programmatic).  All three render the
same source: the conversation row + every message in
``chat_messages``.

Each renderer is a pure function over the persisted shape so the
exporter has zero coupling to the live stream — a download from a
month-old conversation looks identical to one from this morning.
"""

from app.conversations.exports.html_export import render_html
from app.conversations.exports.json_export import render_json
from app.conversations.exports.markdown_export import render_markdown

__all__ = [
    "render_html",
    "render_json",
    "render_markdown",
]
