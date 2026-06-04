"""Decode and read Google Chat events delivered over Pub/Sub.

Pure functions, no I/O: a Chat event arrives base64-encoded inside a
Pub/Sub ``receivedMessages`` envelope; these helpers decode it and read
the handful of fields the channel cares about. The inbound shape is
documented at https://developers.google.com/workspace/chat/quickstart/pub-sub.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# The only event type that should drive an agent turn. ADDED_TO_SPACE /
# REMOVED_FROM_SPACE and others are decoded but ignored by the ingress.
MESSAGE_EVENT_TYPE = "MESSAGE"


def decode_pubsub_message(received: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    """Return ``(ack_id, chat_event)`` for one ``receivedMessages`` entry.

    The Chat event is JSON, base64-encoded in ``message.data``. A
    malformed payload yields ``(ack_id, None)`` — the caller still
    acknowledges it (so Pub/Sub stops redelivering garbage) but skips
    processing.
    """
    ack_id = received.get("ackId")
    envelope = received.get("message")
    data_b64 = envelope.get("data") if isinstance(envelope, dict) else None
    if not isinstance(data_b64, str) or not data_b64:
        return ack_id, None
    try:
        raw = base64.b64decode(data_b64)
        event = json.loads(raw)
    except (binascii.Error, ValueError, json.JSONDecodeError):
        logger.warning("GOOGLE_CHAT_BAD_EVENT_PAYLOAD ack_id=%s", ack_id)
        return ack_id, None
    return ack_id, event if isinstance(event, dict) else None


def event_type(event: dict[str, Any]) -> str:
    """Return the event ``type`` (e.g. ``"MESSAGE"``), or an empty string."""
    return str(event.get("type") or "")


def _message(event: dict[str, Any]) -> dict[str, Any]:
    message = event.get("message")
    return message if isinstance(message, dict) else {}


def _sender(event: dict[str, Any]) -> dict[str, Any]:
    sender = _message(event).get("sender")
    return sender if isinstance(sender, dict) else {}


def message_text(event: dict[str, Any]) -> str:
    """Return the user's message text, or an empty string."""
    return str(_message(event).get("text") or "")


def space_name(event: dict[str, Any]) -> str:
    """Return the ``spaces/{id}`` resource name the message belongs to."""
    space = event.get("space")
    name = space.get("name") if isinstance(space, dict) else None
    return str(name or "")


def thread_name(event: dict[str, Any]) -> str | None:
    """Return the ``spaces/{id}/threads/{id}`` name, or ``None`` for a top-level message."""
    thread = _message(event).get("thread")
    name = thread.get("name") if isinstance(thread, dict) else None
    return str(name) if name else None


def sender_name(event: dict[str, Any]) -> str:
    """Return the sender's ``users/{id}`` resource name (stable identity)."""
    return str(_sender(event).get("name") or "")


def sender_display(event: dict[str, Any]) -> str | None:
    """Return the sender's display name, if Chat supplied one."""
    display = _sender(event).get("displayName")
    return str(display) if display else None


def format_for_chat(text: str) -> str:
    """Format agent markdown for Google Chat.

    Google Chat renders a subset of markdown (``*bold*``, ``_italic_``,
    inline ``code`` and fenced blocks, bullet lists) natively, so v1
    sends the agent's text through unchanged. A richer markdown→Chat
    converter (mirroring Telegram's ``html.py``) is the natural next
    step if formatting fidelity becomes an issue.
    """
    return text
