"""Tests for ``app.conversations.exports`` — golden-output checks per format."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from app.conversations.exports import render_html, render_json, render_markdown
from app.models import ChatMessage, Conversation


@pytest.fixture
def conversation() -> Conversation:
    """A representative conversation row for export tests."""
    return Conversation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="My Cool Chat",
        created_at=datetime(2026, 5, 14, 10, 0, 0, tzinfo=UTC).replace(tzinfo=None),
        updated_at=datetime(2026, 5, 14, 10, 5, 0, tzinfo=UTC).replace(tzinfo=None),
        is_archived=False,
        is_flagged=False,
        is_unread=False,
        labels=[],
        model_id="claude-code-pty:anthropic/claude-sonnet-4-6",
    )


@pytest.fixture
def messages(conversation: Conversation) -> list[ChatMessage]:
    """Two-turn conversation: user → assistant with tool call + thinking."""
    return [
        ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            user_id=conversation.user_id,
            ordinal=0,
            role="user",
            content="What files are in the workspace?",
            created_at=datetime(2026, 5, 14, 10, 0, 0, tzinfo=UTC).replace(tzinfo=None),
            updated_at=datetime(2026, 5, 14, 10, 0, 0, tzinfo=UTC).replace(tzinfo=None),
        ),
        ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            user_id=conversation.user_id,
            ordinal=1,
            role="assistant",
            content="There are three files in your workspace.",
            thinking="Let me list the workspace contents…",
            tool_calls=[
                {
                    "name": "workspace_list",
                    "status": "completed",
                    "input": {"path": ""},
                    "result": "AGENTS.md\nSOUL.md\nnotes.txt",
                }
            ],
            assistant_status="complete",
            created_at=datetime(2026, 5, 14, 10, 5, 0, tzinfo=UTC).replace(tzinfo=None),
            updated_at=datetime(2026, 5, 14, 10, 5, 0, tzinfo=UTC).replace(tzinfo=None),
        ),
    ]


class TestMarkdown:
    def test_includes_title_and_messages(
        self, conversation: Conversation, messages: list[ChatMessage]
    ) -> None:
        out = render_markdown(conversation=conversation, messages=messages)
        assert "# My Cool Chat" in out
        assert "What files" in out
        assert "There are three files" in out
        # Tool calls + thinking surface in the doc.
        assert "workspace_list" in out
        assert "Reasoning" in out

    def test_renders_with_no_messages(self, conversation: Conversation) -> None:
        out = render_markdown(conversation=conversation, messages=[])
        assert "Message count:** 0" in out


class TestHtml:
    def test_self_contained_document(
        self, conversation: Conversation, messages: list[ChatMessage]
    ) -> None:
        out = render_html(conversation=conversation, messages=messages)
        assert out.startswith("<!DOCTYPE html>")
        assert "<style>" in out
        assert "<title>My Cool Chat</title>" in out
        assert "There are three files" in out

    def test_escapes_untrusted_content(self, conversation: Conversation) -> None:
        # Even a tool result that's pure HTML must escape into safe text.
        rogue = ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            user_id=conversation.user_id,
            ordinal=0,
            role="assistant",
            content="<script>alert(1)</script>",
            created_at=datetime.now(UTC).replace(tzinfo=None),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        )
        out = render_html(conversation=conversation, messages=[rogue])
        assert "<script>alert(1)</script>" not in out
        assert "&lt;script&gt;" in out


class TestJson:
    def test_round_trips(self, conversation: Conversation, messages: list[ChatMessage]) -> None:
        body = render_json(conversation=conversation, messages=messages)
        payload = json.loads(body)
        assert payload["conversation"]["id"] == str(conversation.id)
        assert payload["conversation"]["model_id"] == "claude-code-pty:anthropic/claude-sonnet-4-6"
        assert len(payload["messages"]) == 2
        assistant = payload["messages"][1]
        assert assistant["role"] == "assistant"
        assert assistant["tool_calls"][0]["name"] == "workspace_list"
        assert assistant["thinking"] == "Let me list the workspace contents…"

    def test_empty_messages_serializes(self, conversation: Conversation) -> None:
        body = render_json(conversation=conversation, messages=[])
        payload = json.loads(body)
        assert payload["messages"] == []
