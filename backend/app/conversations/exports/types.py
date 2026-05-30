"""Structural protocols that conversation exporters consume.

The exporters render a conversation + its messages into Markdown / HTML
/ JSON.  They never need to write back to the database — they're pure
projections.  Defining the input shape as a :class:`typing.Protocol`
instead of taking the SQLAlchemy ORM classes directly lets the
exporters stay at the ``app.workspace`` layer without importing
``app.models``, which would violate the layered architecture contract
(``models`` lives below ``core`` in the sentrux / import-linter
ordering).

The ``app.models.Conversation`` and ``app.models.ChatMessage`` ORM
rows satisfy these Protocols structurally — every attribute matches —
so call sites in the API layer just pass the ORM rows directly. The
seam is type-only: at runtime nothing changes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol


class ConversationLike(Protocol):
    """The conversation-shaped subset of attributes exporters read.

    Mirrors the public surface of :class:`app.models.Conversation` that
    the exporters touch — title, identity, timestamps, optional model
    ID, plus the JSON-export-only fields (``user_id``, ``is_archived``,
    ``is_flagged``, ``labels``, ``origin_channel``). Adding a new
    exporter field means adding it here too.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    model_id: str | None
    is_archived: bool
    is_flagged: bool
    labels: list[str]
    origin_channel: str | None


class MessageLike(Protocol):
    """The message-shaped subset of attributes exporters read.

    Mirrors the public surface of :class:`app.models.ChatMessage` —
    role + body + the auxiliary fields the renderers fan out into
    (thinking text, tool calls, an optional attachment path) plus the
    JSON-export-only metadata (``id``, ``ordinal``, ``timeline``,
    ``thinking_duration_seconds``, ``assistant_status``,
    ``updated_at``).
    """

    id: uuid.UUID
    ordinal: int
    role: str
    created_at: datetime
    updated_at: datetime
    content: str
    thinking: str | None
    thinking_duration_seconds: int | None
    tool_calls: list[dict[str, Any]] | None
    timeline: list[dict[str, Any]] | None
    assistant_status: str | None
    attachment: str | None
    attachment_mime: str | None
