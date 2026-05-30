"""Unit tests for conversation API helper functions."""

from datetime import datetime
from uuid import uuid4

from app.conversations.router import _normalize_generated_title, _serialize_chat_message
from app.models import ChatMessage


def test_normalize_generated_title_collapses_valid_title() -> None:
    """Generated titles are stripped, unquoted, and whitespace-normalized."""
    assert _normalize_generated_title('"  Build   a test suite  "') == "Build a test suite"


def test_normalize_generated_title_rejects_provider_error_text() -> None:
    """Provider/authentication error text is not persisted as a title."""
    assert _normalize_generated_title("No API key was provided") is None


def test_normalize_generated_title_rejects_long_titles() -> None:
    """Overly long generated titles are rejected."""
    assert _normalize_generated_title("x" * 81) is None


def test_serialize_chat_message_passes_through_optional_fields() -> None:
    """ChatMessage rows project all rich fields onto the API shape."""
    row = ChatMessage(
        id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        ordinal=0,
        role="assistant",
        content="hello",
        thinking="reasoning",
        tool_calls=[{"id": "t1", "name": "web_search", "input": {}, "status": "completed"}],
        timeline=[
            {"kind": "thinking", "text": "reasoning"},
            {"kind": "tool", "toolCallId": "t1"},
        ],
        thinking_duration_seconds=4,
        assistant_status="complete",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    serialized = _serialize_chat_message(row)
    assert serialized.role == "assistant"
    assert serialized.content == "hello"
    assert serialized.thinking == "reasoning"
    assert serialized.thinking_duration_seconds == 4
    assert serialized.assistant_status == "complete"
    assert serialized.tool_calls == row.tool_calls
    assert serialized.timeline == row.timeline


def test_serialize_chat_message_drops_unknown_status() -> None:
    """An unexpected assistant_status value falls back to None instead of crashing."""
    row = ChatMessage(
        id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        ordinal=0,
        role="user",
        content="hi",
        thinking=None,
        tool_calls=None,
        timeline=None,
        thinking_duration_seconds=None,
        assistant_status="bogus-state",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    serialized = _serialize_chat_message(row)
    assert serialized.assistant_status is None
