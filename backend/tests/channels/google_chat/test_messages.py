"""Google Chat channel — Pub/Sub event decode + field extraction (messages).

Pure functions: a Chat event arrives base64-encoded inside a Pub/Sub envelope;
these cover decoding both the classic flat shape and the Google Workspace
add-on shape (incl. the URL-safe-base64 fallback) and reading the handful of
fields the channel cares about.
"""

from __future__ import annotations

import base64
import json

from app.channels.google_chat.messages import (
    decode_pubsub_message,
    event_type,
    message_text,
    sender_display,
    sender_name,
    space_name,
    thread_name,
)
from tests.channels.google_chat.helpers import (
    DEV_ADMIN_SENDER,
    SPACE,
    THREAD,
    addon_event,
    chat_event,
    pubsub_envelope,
)


def test_decode_pubsub_message_decodes_message_event() -> None:
    ack_id, event = decode_pubsub_message(pubsub_envelope(chat_event()))
    assert ack_id == "ack-1"
    assert event is not None
    assert event_type(event) == "MESSAGE"


def test_decode_pubsub_message_rejects_bad_base64() -> None:
    bad = {"ackId": "ack-2", "message": {"data": "!!!not-base64!!!"}}
    ack_id, event = decode_pubsub_message(bad)
    assert ack_id == "ack-2"
    assert event is None


def test_decode_pubsub_message_handles_missing_data() -> None:
    ack_id, event = decode_pubsub_message({"ackId": "ack-3", "message": {}})
    assert ack_id == "ack-3"
    assert event is None


def test_event_extractors_read_message_fields() -> None:
    event = chat_event(text="do the thing")
    assert message_text(event) == "do the thing"
    assert space_name(event) == SPACE
    assert thread_name(event) == THREAD
    assert sender_name(event) == DEV_ADMIN_SENDER
    assert sender_display(event) == "Tavi"


def test_addon_event_type_is_message() -> None:
    # No top-level ``type``; the presence of ``messagePayload`` implies MESSAGE.
    assert event_type(addon_event()) == "MESSAGE"


def test_addon_event_extractors_read_message_fields() -> None:
    event = addon_event(text="add-on hi")
    assert message_text(event) == "add-on hi"
    assert space_name(event) == SPACE
    assert thread_name(event) == THREAD
    assert sender_name(event) == DEV_ADMIN_SENDER
    assert sender_display(event) == "Tavi"


def test_decode_pubsub_message_decodes_addon_event() -> None:
    ack_id, event = decode_pubsub_message(pubsub_envelope(addon_event()))
    assert ack_id == "ack-1"
    assert event is not None
    assert event_type(event) == "MESSAGE"
    assert message_text(event) == "hello"


def test_decode_pubsub_message_handles_url_safe_base64() -> None:
    # Live add-on payloads arrive URL-safe-encoded; the decoder must fall back
    # from the standard alphabet to the URL-safe one. The ">>>>" run forces
    # bytes that differ between the two alphabets so this genuinely exercises it.
    event = addon_event(text="payload >>>>>>>> marker")
    url_safe = base64.urlsafe_b64encode(json.dumps(event).encode("utf-8")).decode("ascii")
    assert ("-" in url_safe) or ("_" in url_safe)
    ack_id, decoded = decode_pubsub_message({"ackId": "ack-u", "message": {"data": url_safe}})
    assert ack_id == "ack-u"
    assert decoded is not None
    assert message_text(decoded) == "payload >>>>>>>> marker"
