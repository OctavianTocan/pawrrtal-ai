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
    for decoder in (_strict_b64decode, base64.urlsafe_b64decode):
        try:
            event = json.loads(decoder(padded))
        except (binascii.Error, ValueError, json.JSONDecodeError):
            continue
        if isinstance(event, dict):
            return event
    return None


def _strict_b64decode(data: str) -> bytes:
    """Standard base64 decode that *rejects* URL-safe chars (``validate=True``).

    Strictness is deliberate: a URL-safe payload (containing ``-``/``_``) then
    raises here and falls through to the URL-safe decoder, instead of being
    silently mis-decoded into bytes that merely happen to fail ``json.loads``.
    """
    return base64.b64decode(data, validate=True)


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


def _button_clicked_payload(event: dict[str, Any]) -> dict[str, Any]:
    """Return the add-on ``chat.buttonClickedPayload`` dict, or ``{}``.

    Card-button clicks arrive under this key (not ``messagePayload`` /
    ``appCommandPayload``); it carries the clicked card's ``message`` and the
    ``space`` the click happened in.
    """
    chat = event.get("chat")
    payload = chat.get("buttonClickedPayload") if isinstance(chat, dict) else None
    return payload if isinstance(payload, dict) else {}


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
    """Return the ``spaces/{id}`` resource name the event belongs to.

    Classic events carry a top-level ``space``; add-on message/command events
    nest it under the payload; card-button clicks carry it under
    ``buttonClickedPayload`` — all three are checked so a click resolves its
    space too.
    """
    candidates = (
        event.get("space"),
        _addon_payload(event).get("space"),
        _button_clicked_payload(event).get("space"),
    )
    for space in candidates:
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


def invoked_function(event: dict[str, Any]) -> str:
    """Return the card-button action function name, or ``""`` for non-clicks.

    On a button click the add-on event carries the ``onClick.action.function``
    value at ``commonEventObject.invokedFunction`` (Chat-apps-only field).
    """
    common = event.get("commonEventObject")
    fn = common.get("invokedFunction") if isinstance(common, dict) else None
    return str(fn or "")


def invoked_parameters(event: dict[str, Any]) -> dict[str, str]:
    """Return the clicked button's action parameters as a flat ``{key: value}`` map.

    Note Chat delivers click parameters as a map here, even though they're
    *sent* as a list of ``{key, value}`` objects in the card.
    """
    common = event.get("commonEventObject")
    params = common.get("parameters") if isinstance(common, dict) else None
    if not isinstance(params, dict):
        return {}
    return {str(key): str(value) for key, value in params.items()}


def clicked_message_name(event: dict[str, Any]) -> str:
    """Return the ``spaces/*/messages/*`` name of the card the button is on.

    Lives at ``chat.buttonClickedPayload.message.name``; it's the resource a
    Pub/Sub app patches to reflect the click.
    """
    message = _button_clicked_payload(event).get("message")
    name = message.get("name") if isinstance(message, dict) else None
    return str(name or "")


def attachments_of(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the inbound message's attachments (``message.attachment[]``).

    The add-on field name is the singular, repeated ``attachment`` (not
    ``attachments``); non-dict entries are dropped defensively.
    """
    raw = _message(event).get("attachment")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def format_for_chat(text: str) -> str:
    """Convert agent Markdown to Google Chat's text-formatting syntax.

    The agent emits CommonMark, but Chat's ``text`` field renders a
    different lightweight syntax (``*bold*``, ``_italic_``, ``<url|label>``)
    and shows Markdown constructs like ``**bold**`` / ``# headings`` /
    ``[text](url)`` literally. Delegates to
    :func:`app.channels.google_chat.formatting.md_to_chat`.
    """
    # Lazy import: markdown-it is heavy and only needed while delivering.
    from .formatting import md_to_chat  # noqa: PLC0415

    return md_to_chat(text)
