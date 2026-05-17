"""Render a conversation as a programmatic JSON document.

Schema is stable — every key is documented in
``backend/app/core/exporters/__init__.py`` so external callers can
depend on the shape.  Produces a top-level object with ``conversation``
metadata + a ``messages`` array; each message keeps every field of
the persisted ``ChatMessage`` row.

Datetimes serialize to ISO-8601 with second precision so the
output is human-readable + parseable.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.models import ChatMessage, Conversation


def render_json(
    *,
    conversation: Conversation,
    messages: Sequence[ChatMessage],
) -> str:
    """Return a pretty-printed JSON export of the conversation."""
    payload: dict[str, Any] = {
        "conversation": _serialize_conversation(conversation),
        "messages": [_serialize_message(m) for m in messages],
    }
    return json.dumps(payload, indent=2, sort_keys=True, default=str)


def _serialize_conversation(conversation: Conversation) -> dict[str, Any]:
    return {
        "id": str(conversation.id),
        "user_id": str(conversation.user_id),
        "title": conversation.title,
        "model_id": conversation.model_id,
        "created_at": _iso(conversation.created_at),
        "updated_at": _iso(conversation.updated_at),
        "is_archived": conversation.is_archived,
        "is_flagged": conversation.is_flagged,
        "labels": list(conversation.labels or []),
        # TODO(pawrrtal-j8o1): re-add `"origin_channel": conversation.origin_channel`
        #   once the column is restored on the Conversation ORM model.
    }


def _serialize_message(message: ChatMessage) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "ordinal": message.ordinal,
        "role": message.role,
        "content": message.content,
        "thinking": message.thinking,
        "tool_calls": message.tool_calls,
        "timeline": message.timeline,
        "thinking_duration_seconds": message.thinking_duration_seconds,
        "assistant_status": message.assistant_status,
        "attachment": message.attachment,
        "attachment_mime": message.attachment_mime,
        "created_at": _iso(message.created_at),
        "updated_at": _iso(message.updated_at),
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="seconds")
