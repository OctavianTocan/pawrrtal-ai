"""CRUD service tests for conversations."""

import uuid
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.conversation import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations_for_user,
    update_conversation,
    update_conversation_model,
    update_conversation_title,
)
from app.db import User
from app.models import Conversation
from app.schemas import ConversationCreate, ConversationUpdate


@pytest.mark.anyio
async def test_create_conversation_uses_client_supplied_id(
    db_session: AsyncSession, test_user: User
) -> None:
    """Conversation creation preserves a frontend-generated UUID."""
    conversation_id = uuid4()

    conversation = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(id=conversation_id, title="Hello"),
    )

    assert conversation.id == conversation_id
    assert conversation.title == "Hello"
    assert conversation.user_id == test_user.id


@pytest.mark.anyio
async def test_create_conversation_defaults_title(
    db_session: AsyncSession, test_user: User
) -> None:
    """Conversation creation falls back to the default title."""
    conversation = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(),
    )

    assert conversation.title == "New Conversation"


@pytest.mark.anyio
async def test_create_conversation_is_idempotent_for_same_owner(
    db_session: AsyncSession, test_user: User
) -> None:
    """Retrying create with an existing owned UUID returns the existing row."""
    conversation_id = uuid4()
    first = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(id=conversation_id, title="Original"),
    )

    second = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(id=conversation_id, title="Retry title"),
    )

    assert second.id == first.id
    assert second.title == "Original"


@pytest.mark.anyio
async def test_create_conversation_rejects_cross_user_uuid_collision(
    db_session: AsyncSession, test_user: User
) -> None:
    """An existing conversation ID owned by another user raises a service error."""
    other_user = User(
        id=uuid4(),
        email="other@example.com",
        hashed_password="not-used",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db_session.add(other_user)
    await db_session.commit()
    conversation_id = uuid4()
    await create_conversation(
        other_user.id,
        db_session,
        ConversationCreate(id=conversation_id, title="Other"),
    )

    with pytest.raises(ValueError, match="already in use"):
        await create_conversation(
            test_user.id,
            db_session,
            ConversationCreate(id=conversation_id, title="Collision"),
        )


@pytest.mark.anyio
async def test_get_conversation_scopes_to_owner(db_session: AsyncSession, test_user: User) -> None:
    """Conversation lookup returns None for the wrong owner."""
    conversation = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(title="Owned"),
    )

    assert await get_conversation(uuid4(), db_session, conversation.id) is None


@pytest.mark.anyio
async def test_get_conversations_for_user_orders_newest_first(
    db_session: AsyncSession, test_user: User
) -> None:
    """Conversation listing is sorted by updated_at descending."""
    first = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(title="First"),
    )
    second = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(title="Second"),
    )

    conversations = await list_conversations_for_user(test_user.id, db_session)

    assert [conversation.id for conversation in conversations] == [second.id, first.id]


@pytest.mark.anyio
async def test_update_conversation_title_updates_title_and_timestamp(
    db_session: AsyncSession, test_user: User
) -> None:
    """Title updates persist and bump updated_at."""
    conversation = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(title="Old"),
    )
    original_updated_at = conversation.updated_at

    updated = await update_conversation_title("New", test_user.id, conversation.id, db_session)

    assert updated is not None
    assert updated.title == "New"
    assert updated.updated_at >= original_updated_at


@pytest.mark.anyio
async def test_update_conversation_metadata_updates_only_provided_fields(
    db_session: AsyncSession, test_user: User
) -> None:
    """Partial metadata updates leave unspecified fields unchanged."""
    conversation = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(title="Keep me"),
    )

    updated = await update_conversation(
        ConversationUpdate(is_archived=True, is_flagged=True, status="done"),
        test_user.id,
        conversation.id,
        db_session,
    )

    assert updated is not None
    assert updated.title == "Keep me"
    assert updated.is_archived is True
    assert updated.is_flagged is True
    assert updated.is_unread is False
    assert updated.status == "done"


@pytest.mark.anyio
async def test_update_conversation_model_service_sets_model_id(
    db_session: AsyncSession, test_user: User
) -> None:
    """Model updates persist the selected model identifier."""
    conversation = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(title="Model"),
    )

    updated = await update_conversation_model(
        "gemini-3-flash-preview", test_user.id, conversation.id, db_session
    )

    assert updated is not None
    assert updated.model_id == "gemini-3-flash-preview"


@pytest.mark.anyio
async def test_delete_conversation_removes_owned_row(
    db_session: AsyncSession, test_user: User
) -> None:
    """Delete returns True and removes an owned conversation."""
    conversation = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(title="Delete"),
    )

    deleted = await delete_conversation(test_user.id, db_session, conversation.id)

    assert deleted is True
    assert await get_conversation(test_user.id, db_session, conversation.id) is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "value",
    ["minimal", "low", "medium", "high", "extra-high", None],
)
async def test_reasoning_effort_accepts_literal_values(
    db_session: AsyncSession, test_user: User, value: str | None
) -> None:
    """Every ``ReasoningEffort`` literal value (and NULL) survives a round-trip.

    The CHECK constraint added in migration 021 (#367) must not reject any
    of the documented literal values, including NULL for "let the provider
    pick its default".
    """
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="reasoning",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        reasoning_effort=value,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    assert conv.reasoning_effort == value


@pytest.mark.anyio
async def test_reasoning_effort_rejects_unknown_value(
    db_session: AsyncSession, test_user: User
) -> None:
    """The DB-level CHECK constraint blocks values outside the literal set.

    Regression for #367 — without this gate, a typo or stale enum string
    from the CRUD setter would silently land in the column and only blow
    up later during provider resolution.
    """
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="bad effort",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        reasoning_effort="ultra-mega-high",  # not in the literal
    )
    db_session.add(conv)
    with pytest.raises(IntegrityError):
        await db_session.commit()
