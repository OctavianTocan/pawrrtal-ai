"""API tests for conversation routes."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import User
from app.models import Conversation


@pytest.mark.anyio
async def test_create_conversation_returns_created_metadata(
    client: AsyncClient,
) -> None:
    """POST /api/v1/conversations/{id} creates metadata for a conversation."""
    conversation_id = uuid4()

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "Hello"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(conversation_id)
    assert payload["title"] == "Hello"
    assert payload["is_archived"] is False
    assert payload["status"] is None


@pytest.mark.anyio
async def test_create_conversation_is_idempotent(client: AsyncClient) -> None:
    """Repeating POST with the same client UUID returns the existing row."""
    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "Original"})

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "Retry"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Original"


@pytest.mark.anyio
async def test_patch_conversation_accepts_status_only_payload(
    client: AsyncClient,
) -> None:
    """PATCH accepts metadata-only updates without requiring a title."""
    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "Status"})

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"status": "done"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert response.json()["title"] == "Status"


@pytest.mark.anyio
async def test_patch_conversation_rejects_blank_title(client: AsyncClient) -> None:
    """PATCH rejects blank titles with a validation error."""
    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "Title"})

    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "   "},
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_list_conversations_returns_newest_first(client: AsyncClient) -> None:
    """GET /api/v1/conversations returns most recent conversations first."""
    first_id = uuid4()
    second_id = uuid4()
    await client.post(f"/api/v1/conversations/{first_id}", json={"title": "First"})
    await client.post(f"/api/v1/conversations/{second_id}", json={"title": "Second"})

    response = await client.get("/api/v1/conversations")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(second_id), str(first_id)]


@pytest.mark.anyio
async def test_delete_conversation_removes_conversation(client: AsyncClient) -> None:
    """DELETE removes an owned conversation."""
    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "Delete"})

    delete_response = await client.delete(f"/api/v1/conversations/{conversation_id}")
    get_response = await client.get(f"/api/v1/conversations/{conversation_id}")

    assert delete_response.status_code == 204
    assert get_response.status_code == 200
    assert get_response.json() is None


@pytest.mark.anyio
async def test_get_conversation_messages_returns_empty_for_new_conversation(
    client: AsyncClient,
) -> None:
    """A freshly-created conversation has no chat_messages rows yet — empty list."""
    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "Messages"})

    response = await client.get(f"/api/v1/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_generate_conversation_title_persists_usable_title(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Title generation persists normalized provider output."""
    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "Old"})

    # Monkeypatch the actual call site so the test isn't pinned to the
    # provider implementation behind title generation.
    async def _fake_generate_text(_prompt: str) -> str:
        return '"Better   Title"'

    monkeypatch.setattr(
        "app.api.conversations.generate_text_once",
        _fake_generate_text,
    )

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/title",
        params={"first_message": "hello"},
    )
    get_response = await client.get(f"/api/v1/conversations/{conversation_id}")

    assert response.status_code == 200
    assert response.json() == "Better Title"
    assert get_response.json()["title"] == "Better Title"


@pytest.mark.anyio
async def test_conversation_response_includes_codex_thread_id(
    client: AsyncClient, db_session: AsyncSession, test_user: User
) -> None:
    """ConversationRead must include codex_thread_id so paw verify can assert it.

    The column already exists on the ORM (models.py: Conversation.codex_thread_id)
    but was being dropped from the API response. Without exposing it, an HTTP
    client has no way to observe that the codex provider persisted a stable
    thread id across turns.
    """
    conversation_id = uuid4()
    now = datetime.now(UTC)
    conversation = Conversation(
        id=conversation_id,
        user_id=test_user.id,
        title="codex thread persistence",
        created_at=now,
        updated_at=now,
        model_id="openai-codex:openai/gpt-5.5",
        codex_thread_id="thr_test_abc",
    )
    db_session.add(conversation)
    await db_session.commit()

    response = await client.get(f"/api/v1/conversations/{conversation_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "codex_thread_id" in body, f"missing field; got keys={list(body.keys())}"
    assert body["codex_thread_id"] == "thr_test_abc"
