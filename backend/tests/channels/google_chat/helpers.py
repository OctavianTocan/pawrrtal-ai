"""Shared builders + constants for the Google Chat channel tests.

Pure, import-light fixtures-by-hand: event-shape builders for the Pub/Sub
envelope, classic + add-on message events, slash-command events, card-button
clicks, and a couple of dict-navigation helpers. No app imports — the heavy
shared fixture (a real ``CommandContext`` over the DB) lives in ``conftest.py``.

These are part of the test package's public helper surface, so they use
public names (no leading underscore) per the module-privacy rule: other test
modules import them.
"""

from __future__ import annotations

import base64
import json
from typing import Any

DEV_ADMIN_SENDER = "users/1234567890"
OTHER_SENDER = "users/9999999999"
SPACE = "spaces/AAAA"
THREAD = "spaces/AAAA/threads/TTTT"


def chat_event(*, text: str = "hello", sender: str = DEV_ADMIN_SENDER) -> dict[str, Any]:
    """Build a representative classic Chat ``MESSAGE`` event."""
    return {
        "type": "MESSAGE",
        "space": {"name": SPACE},
        "message": {
            "name": f"{SPACE}/messages/MMMM",
            "text": text,
            "sender": {"name": sender, "displayName": "Tavi", "type": "HUMAN"},
            "thread": {"name": THREAD},
        },
    }


def pubsub_envelope(event: dict[str, Any], *, ack_id: str = "ack-1") -> dict[str, Any]:
    """Wrap a Chat event in the Pub/Sub ``receivedMessages`` shape."""
    data = base64.b64encode(json.dumps(event).encode("utf-8")).decode("ascii")
    return {"ackId": ack_id, "message": {"data": data}}


def addon_event(*, text: str = "hello", sender: str = DEV_ADMIN_SENDER) -> dict[str, Any]:
    """Build a Google Workspace add-on ``MESSAGE`` event (the modern shape).

    Add-on Chat apps wrap the message under ``chat.messagePayload`` and omit
    the classic top-level ``type``/``message``/``space`` keys. This mirrors a
    real DM event captured from a live add-on Chat app.
    """
    sender_obj = {"name": sender, "displayName": "Tavi", "type": "HUMAN"}
    return {
        "commonEventObject": {"userLocale": "en", "hostApp": "CHAT"},
        "chat": {
            "user": sender_obj,
            "messagePayload": {
                "space": {"name": SPACE, "type": "DM"},
                "message": {
                    "name": f"{SPACE}/messages/MMMM",
                    "text": text,
                    "sender": sender_obj,
                    "thread": {"name": THREAD},
                },
            },
        },
    }


def addon_command_event(*, command_text: str, argument_text: str | None = None) -> dict[str, Any]:
    """Build an add-on slash-command event (``chat.appCommandPayload``)."""
    message: dict[str, Any] = {"name": f"{SPACE}/messages/CMD", "text": command_text}
    if argument_text is not None:
        message["argumentText"] = argument_text
    return {
        "commonEventObject": {"hostApp": "CHAT"},
        "chat": {
            "user": {"name": DEV_ADMIN_SENDER, "displayName": "Tavi"},
            "appCommandPayload": {"space": {"name": SPACE}, "message": message},
        },
    }


def click_event(*, function: str, value: str) -> dict[str, Any]:
    """Build an add-on card-button-click event."""
    return {
        "commonEventObject": {
            "hostApp": "CHAT",
            "invokedFunction": function,
            "parameters": {"value": value},
        },
        "chat": {
            "user": {"name": DEV_ADMIN_SENDER, "displayName": "Tavi"},
            "buttonClickedPayload": {
                "message": {"name": f"{SPACE}/messages/CARD"},
                "space": {"name": SPACE},
            },
        },
    }


def event_with_attachment(att: dict[str, Any]) -> dict[str, Any]:
    """Attach a single ``attachment`` entry to an add-on message event."""
    event = addon_event()
    event["chat"]["messagePayload"]["message"]["attachment"] = [att]
    return event


def picker_buttons(card: list[dict[str, Any]]) -> list[Any]:
    """Pull the buttonList buttons out of a picker card."""
    buttons = card[0]["card"]["sections"][0]["widgets"][1]["buttonList"]["buttons"]
    assert isinstance(buttons, list)
    return buttons
