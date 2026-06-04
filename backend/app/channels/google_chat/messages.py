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
    event = _b64_to_json(data_b64)
    if event is None:
        logger.warning("GOOGLE_CHAT_BAD_EVENT_PAYLOAD ack_id=%s", ack_id)
    return ack_id, event


def _b64_to_json(data_b64: str) -> dict[str, Any] | None:
    """Decode a base64 Chat event payload to a JSON object.

    Pub/Sub delivers the event as standard base64, but Google Workspace
    add-on events have been observed URL-safe-encoded — so both alphabets
    are tried. Returns ``None`` when neither yields a JSON object.
    """
    padded = data_b64 + "=" * (-len(data_b64) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            event = json.loads(decoder(padded))
        except (binascii.Error, ValueError, json.JSONDecodeError):
            continue
        if isinstance(event, dict):
            return event
    return None


def event_type(event: dict[str, Any]) -> str:
    """Return the event ``type`` (e.g. ``"MESSAGE"``), or an empty string.

    Classic Chat Pub/Sub events carry an explicit ``type``. Google Workspace
    add-on events don't — the type is implied by which ``chat.*Payload`` is
    present, so a ``messagePayload`` maps to ``MESSAGE``.
    """
    explicit = event.get("type")
    if explicit:
        return str(explicit)
    if _addon_payload(event).get("message"):
        return MESSAGE_EVENT_TYPE
    return ""


def _addon_payload(event: dict[str, Any]) -> dict[str, Any]:
    """Return the add-on message/command payload dict, or ``{}``.

    Google Chat apps built as Google Workspace add-ons wrap the event as
    ``{"commonEventObject": ..., "chat": {"messagePayload": {...}}}`` rather
    than the classic flat ``{"type", "message", "space"}`` shape. Configured
    slash commands instead arrive under ``chat.appCommandPayload`` — which
    carries the same ``message``/``space`` shape — so both are accepted here.
    """
    chat = event.get("chat")
    if not isinstance(chat, dict):
        return {}
    payload = chat.get("messagePayload") or chat.get("appCommandPayload")
    return payload if isinstance(payload, dict) else {}


def _chat_user(event: dict[str, Any]) -> dict[str, Any]:
    """Return the add-on ``chat.user`` dict (the human who acted), or ``{}``."""
    chat = event.get("chat")
    user = chat.get("user") if isinstance(chat, dict) else None
    return user if isinstance(user, dict) else {}


def _message(event: dict[str, Any]) -> dict[str, Any]:
    # Add-on events nest the message under ``chat.messagePayload``; classic
    # events put it at the top level.
    message = _addon_payload(event).get("message") or event.get("message")
    return message if isinstance(message, dict) else {}


def _sender(event: dict[str, Any]) -> dict[str, Any]:
    sender = _message(event).get("sender")
    return sender if isinstance(sender, dict) else {}


def message_text(event: dict[str, Any]) -> str:
    """Return the user's message text, or an empty string."""
    return str(_message(event).get("text") or "")


def space_name(event: dict[str, Any]) -> str:
    """Return the ``spaces/{id}`` resource name the message belongs to.

    Classic events carry a top-level ``space``; add-on events nest it under
    the message payload.
    """
    for space in (event.get("space"), _addon_payload(event).get("space")):
        if isinstance(space, dict) and space.get("name"):
            return str(space["name"])
    return ""


def thread_name(event: dict[str, Any]) -> str | None:
    """Return the ``spaces/{id}/threads/{id}`` name, or ``None`` for a top-level message."""
    thread = _message(event).get("thread")
    name = thread.get("name") if isinstance(thread, dict) else None
    return str(name) if name else None


def sender_name(event: dict[str, Any]) -> str:
    """Return the sender's ``users/{id}`` resource name (stable identity).

    Command events may omit ``message.sender`` but always carry
    ``chat.user``, so that is the fallback.
    """
    name = _sender(event).get("name") or _chat_user(event).get("name")
    return str(name or "")


def sender_display(event: dict[str, Any]) -> str | None:
    """Return the sender's display name, if Chat supplied one."""
    display = _sender(event).get("displayName") or _chat_user(event).get("displayName")
    return str(display) if display else None


def sender_email(event: dict[str, Any]) -> str | None:
    """Return the sender's email, if Chat supplied one (used by ``/whoami``)."""
    email = _sender(event).get("email") or _chat_user(event).get("email")
    return str(email) if email else None


def parse_command(event: dict[str, Any]) -> tuple[str, str] | None:
    """Return ``(command, args)`` when the event is a slash command, else ``None``.

    Handles both configured slash commands (delivered under
    ``chat.appCommandPayload``, with the command and args available on the
    payload's ``message``) and plain ``/cmd ...`` text typed before any
    Console command config exists. Both expose the text via
    :func:`message_text`; ``argumentText`` (mentions stripped) is preferred
    for the argument string when Chat supplies it.
    """
    text = message_text(event).strip()
    if not text.startswith("/"):
        return None
    head, _, rest = text[1:].partition(" ")
    command = head.strip().lower()
    if not command:
        return None
    args = str(_message(event).get("argumentText") or rest).strip()
    return command, args


def format_for_chat(text: str) -> str:
    """Format agent markdown for Google Chat.

    Google Chat renders a subset of markdown (``*bold*``, ``_italic_``,
    inline ``code`` and fenced blocks, bullet lists) natively, so v1
    sends the agent's text through unchanged. A richer markdown→Chat
    converter (mirroring Telegram's ``html.py``) is the natural next
    step if formatting fidelity becomes an issue.
    """
    return text
