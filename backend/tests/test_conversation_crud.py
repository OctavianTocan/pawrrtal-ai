"""CRUD service tests for conversations."""

import uuid
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.crud import (
    apply_model_switch_and_normalize_reasoning,
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversation_status,
    list_conversations_for_user,
    update_conversation,
    update_conversation_model,
    update_conversation_title,
)
from app.core.providers.catalog import MODEL_CATALOG
from app.core.providers.model_id import Host
from app.infrastructure.database.legacy import User
from app.models import Conversation
from app.schemas import ConversationCreate, ConversationUpdate


def _model_id_for(host: Host, model: str) -> str:
    """Canonical ``host:vendor/model`` id from the catalog (test helper)."""
    entry = next(e for e in MODEL_CATALOG if e.host is host and e.model == model)
    return entry.id


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
    """Conversation lookup returns ``None`` for the wrong owner.

    Returns-adoption pilot Phase 2: ``get_conversation`` returns
    ``Conversation | None``. Cross-user access surfaces as ``None``
    so the route boundary can translate to a 404 without leaking
    existence.
    """
    conversation = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(title="Owned"),
    )

    assert await get_conversation(uuid4(), db_session, conversation.id) is None


@pytest.mark.anyio
async def test_get_conversation_returns_some_for_owner(
    db_session: AsyncSession, test_user: User
) -> None:
    """``get_conversation`` returns the row when the owner matches.

    Pairs with ``test_get_conversation_scopes_to_owner`` to cover both
    branches of the Phase 2 ``Conversation | None`` migration. The
    test inspects the container directly (rather than unwrapping)
    so a regression that flips back to ``Optional[Conversation]``
    fails loudly here instead of silently at call sites.
    """
    conversation = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(title="Owned"),
    )

    result = await get_conversation(test_user.id, db_session, conversation.id)

    assert result is not None
    assert result.id == conversation.id


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
    # Phase 2: deleted row → ``None`` instead of ``None``.
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


# ---------------------------------------------------------------------------
# apply_model_switch_and_normalize_reasoning (#366)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_apply_model_switch_updates_model_and_bumps_timestamp(
    db_session: AsyncSession, test_user: User
) -> None:
    """A real model switch updates both ``model_id`` and ``updated_at``."""
    original_model = _model_id_for(Host.xai, "grok-4.3")
    new_model = _model_id_for(Host.agent_sdk, "claude-opus-4-7")
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="switch",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        model_id=original_model,
        reasoning_effort="medium",
    )
    db_session.add(conv)
    await db_session.commit()
    original_updated_at = conv.updated_at

    resolution, previous_effort = await apply_model_switch_and_normalize_reasoning(
        conversation=conv,
        new_model_id=new_model,
        session=db_session,
    )

    assert conv.model_id == new_model
    assert conv.updated_at >= original_updated_at
    assert previous_effort == "medium"
    # claude-opus-4-7 supports "medium" — the stored value is used as-is.
    assert resolution.action == "use"
    assert resolution.effective == "medium"


@pytest.mark.anyio
async def test_apply_model_switch_noop_does_not_bump_timestamp(
    db_session: AsyncSession, test_user: User
) -> None:
    """A no-op call (same model) leaves ``updated_at`` untouched.

    The original helpers bumped ``updated_at`` only when ``model_id``
    actually changed; preserving that semantic prevents every chat
    round from re-ordering the sidebar's recency-sorted list.
    """
    same_model = _model_id_for(Host.agent_sdk, "claude-opus-4-7")
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="noop",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        model_id=same_model,
        reasoning_effort="high",
    )
    db_session.add(conv)
    await db_session.commit()
    original_updated_at = conv.updated_at

    await apply_model_switch_and_normalize_reasoning(
        conversation=conv,
        new_model_id=same_model,
        session=db_session,
    )

    assert conv.updated_at == original_updated_at


@pytest.mark.anyio
async def test_apply_model_switch_normalizes_unsupported_effort(
    db_session: AsyncSession, test_user: User
) -> None:
    """A model that doesn't honour the stored effort gets cleared atomically.

    Regression for #366 — previously this was two ``session.commit``
    calls. Now both the new ``model_id`` and the normalized
    ``reasoning_effort`` land in the same transaction, so a crash
    between writes can't leave the row holding a stale effort that
    belongs to the previous model.
    """
    grok_supports_reasoning = _model_id_for(Host.xai, "grok-4.3")
    haiku_no_reasoning = _model_id_for(Host.agent_sdk, "claude-haiku-4-5")
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="normalize",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        model_id=grok_supports_reasoning,
        reasoning_effort="high",
    )
    db_session.add(conv)
    await db_session.commit()

    resolution, previous_effort = await apply_model_switch_and_normalize_reasoning(
        conversation=conv,
        new_model_id=haiku_no_reasoning,
        session=db_session,
    )

    assert conv.model_id == haiku_no_reasoning
    # claude-haiku-4-5 has ``supports_reasoning=()`` — the stored
    # override gets cleared so the next turn picks up the provider default.
    assert conv.reasoning_effort is None
    assert resolution.action == "cleared"
    assert previous_effort == "high"


@pytest.mark.anyio
async def test_apply_model_switch_persists_after_session_refresh(
    db_session: AsyncSession, test_user: User
) -> None:
    """The combined write survives a session refresh (commit happened)."""
    original_model = _model_id_for(Host.xai, "grok-4.3")
    new_model = _model_id_for(Host.agent_sdk, "claude-opus-4-7")
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="persist",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        model_id=original_model,
        reasoning_effort="low",
    )
    db_session.add(conv)
    await db_session.commit()

    await apply_model_switch_and_normalize_reasoning(
        conversation=conv,
        new_model_id=new_model,
        session=db_session,
    )

    await db_session.refresh(conv)
    assert conv.model_id == new_model
    assert conv.reasoning_effort == "low"  # claude-opus honours low


# ---------------------------------------------------------------------------
# get_conversation_status
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_conversation_status_returns_nothing_for_unknown_id(
    db_session: AsyncSession,
) -> None:
    """Unknown conversation ID surfaces as ``None``.

    Phase 2 contract: callers (Telegram /status handler) rely on
    ``None`` to render the gateway-only fallback instead of
    crashing.
    """
    result = await get_conversation_status(
        conversation_id=uuid4(),
        session=db_session,
    )

    assert result is None


@pytest.mark.anyio
async def test_get_conversation_status_returns_some_for_existing_row(
    db_session: AsyncSession, test_user: User
) -> None:
    """An existing conversation yields the snapshot.

    Asserts that the container shape carries through; specific
    aggregate counts are exercised by the dedicated status tests.
    """
    conversation = await create_conversation(
        test_user.id,
        db_session,
        ConversationCreate(title="Status"),
    )

    result = await get_conversation_status(
        conversation_id=conversation.id,
        session=db_session,
    )

    assert result is not None
    assert result.conversation_id == conversation.id
    assert result.message_count == 0
