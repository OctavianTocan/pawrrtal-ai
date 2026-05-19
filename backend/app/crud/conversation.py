"""CRUD operations for the Conversation model.

All functions enforce user ownership — a user can only access or modify
their own conversations.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio.session import AsyncSession

# Re-export so the chat router imports the normalize seam from
# ``crud.conversation`` — which it's already importing — instead of
# pulling in ``crud.channel`` as a separate module. Keeps chat.py
# under sentrux's ``no_god_files`` fan-out budget.
from app.crud.channel import (  # noqa: F401 — re-export, must follow other crud imports
    normalize_conversation_reasoning_effort,
)
from app.governance_models import CostLedger
from app.models import ChatMessage, Conversation
from app.schemas import ConversationCreate, ConversationUpdate


@dataclass(frozen=True, slots=True)
class ConversationStatus:
    """Aggregated read-only snapshot of a conversation for status displays."""

    conversation_id: uuid.UUID
    model_id: str | None
    verbose_level: int | None
    reasoning_effort: str | None
    started_at: datetime
    message_count: int
    user_message_count: int
    assistant_message_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float


async def create_conversation(
    user_id: uuid.UUID, session: AsyncSession, schema_data: ConversationCreate
) -> Conversation:
    """Create a new conversation with an initial title.

    The title starts from the provided first-message fallback when available,
    otherwise "New Conversation", and can later be replaced by an LLM-generated
    title based on the first message.

    Args:
        user_id: Owner of the conversation.
        session: Async database session.
        schema_data: Creation payload (may include a pre-generated UUID).

    Returns:
        The newly created ``Conversation`` row.
    """
    if schema_data.id is not None:
        existing_conversation_result = await session.execute(
            select(Conversation).where(Conversation.id == schema_data.id)
        )
        existing_conversation = existing_conversation_result.scalar_one_or_none()

        if existing_conversation is not None:
            if existing_conversation.user_id != user_id:
                raise ValueError("Conversation ID is already in use.")
            return existing_conversation

    new_conversation = Conversation(
        id=schema_data.id,
        user_id=user_id,
        title=schema_data.title or "New Conversation",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    session.add(new_conversation)
    await session.commit()
    await session.refresh(new_conversation)
    return new_conversation


async def get_conversation(
    user_id: uuid.UUID, session: AsyncSession, conversation_id: uuid.UUID
) -> Conversation | None:
    """Retrieve a single conversation by ID, scoped to the given user.

    Args:
        user_id: Owner to match against.
        session: Async database session.
        conversation_id: The conversation to look up.

    Returns:
        The ``Conversation`` if found and owned by ``user_id``, else ``None``.
    """
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_conversations_for_user(
    user_id: uuid.UUID, session: AsyncSession
) -> list[Conversation]:
    """Retrieve all conversations for a user, most-recent first.

    Args:
        user_id: Owner whose conversations to fetch.
        session: Async database session.

    Returns:
        List of ``Conversation`` objects ordered by ``updated_at`` descending.
    """
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_conversation_title(
    title: str, user_id: uuid.UUID, conversation_id: uuid.UUID, session: AsyncSession
) -> Conversation | None:
    """Update the title of an existing conversation.

    Args:
        title: The new title to set.
        user_id: Owner to match against (ownership check).
        conversation_id: The conversation to update.
        session: Async database session.

    Returns:
        The updated ``Conversation``, or ``None`` if not found / not owned.
    """
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user_id)
    )
    result = await session.execute(stmt)
    conversation = result.scalar_one_or_none()

    if conversation is None:
        return None

    conversation.title = title
    conversation.updated_at = datetime.now()
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def update_conversation(
    payload: ConversationUpdate,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    session: AsyncSession,
) -> Conversation | None:
    """Update mutable fields on an existing conversation.

    Only fields explicitly set in ``payload`` are applied. Supports title,
    is_archived, is_flagged, is_unread, and status.

    Args:
        payload: Partial update schema — unset fields are left unchanged.
        user_id: Owner to match against (ownership check).
        conversation_id: The conversation to update.
        session: Async database session.

    Returns:
        The updated ``Conversation``, or ``None`` if not found / not owned.
    """
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user_id)
    )
    result = await session.execute(stmt)
    conversation = result.scalar_one_or_none()

    if conversation is None:
        return None

    if payload.title is not None:
        conversation.title = payload.title.strip()
    if payload.is_archived is not None:
        conversation.is_archived = payload.is_archived
    if payload.is_flagged is not None:
        conversation.is_flagged = payload.is_flagged
    if payload.is_unread is not None:
        conversation.is_unread = payload.is_unread
    if payload.status is not None:
        conversation.status = payload.status
    if payload.model_id is not None:
        conversation.model_id = payload.model_id
    if payload.labels is not None:
        # Full replacement — the frontend sends the desired final set,
        # so we don't merge here. `list(...)` detaches from the request
        # object so cleanup of the Pydantic model can't mutate ours.
        conversation.labels = list(payload.labels)
    if payload.project_id_set:
        # Explicit set (even to None) — drag-and-drop into a project sets
        # project_id, dragging out clears it. The companion flag lets us
        # distinguish "set to null" from "leave unchanged" since the JSON
        # body collapses them otherwise.
        conversation.project_id = payload.project_id

    conversation.updated_at = datetime.now()
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def update_conversation_model(
    model_id: str,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    session: AsyncSession,
) -> Conversation | None:
    """Persist a model_id change on an existing conversation.

    Args:
        model_id: The new model identifier to store.
        user_id: Owner to match against (ownership check).
        conversation_id: The conversation to update.
        session: Async database session.

    Returns:
        The updated ``Conversation``, or ``None`` if not found / not owned.
    """
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user_id)
    )
    result = await session.execute(stmt)
    conversation = result.scalar_one_or_none()

    if conversation is None:
        return None

    conversation.model_id = model_id
    conversation.updated_at = datetime.now()
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def get_conversation_status(
    *,
    conversation_id: uuid.UUID,
    session: AsyncSession,
) -> ConversationStatus | None:
    """Return a read-only status snapshot for the given conversation.

    Aggregates per-role message counts from ``chat_messages`` and per-turn
    token totals from ``cost_ledger`` for the conversation. Returns ``None``
    when the conversation does not exist.

    Args:
        conversation_id: The conversation to snapshot.
        session: Async database session.

    Returns:
        A :class:`ConversationStatus` snapshot or ``None`` when not found.
    """
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        return None

    role_counts_stmt = (
        select(ChatMessage.role, func.count(ChatMessage.id))
        .where(ChatMessage.conversation_id == conversation_id)
        .group_by(ChatMessage.role)
    )
    role_counts = dict((await session.execute(role_counts_stmt)).all())
    user_count = int(role_counts.get("user", 0))
    assistant_count = int(role_counts.get("assistant", 0))

    token_totals_stmt = select(
        func.coalesce(func.sum(CostLedger.input_tokens), 0),
        func.coalesce(func.sum(CostLedger.output_tokens), 0),
        func.coalesce(func.sum(CostLedger.cost_usd), 0.0),
    ).where(CostLedger.conversation_id == conversation_id)
    total_input, total_output, total_cost = (await session.execute(token_totals_stmt)).one()

    return ConversationStatus(
        conversation_id=conversation_id,
        model_id=conversation.model_id,
        verbose_level=conversation.verbose_level,
        reasoning_effort=conversation.reasoning_effort,
        started_at=conversation.created_at,
        message_count=user_count + assistant_count,
        user_message_count=user_count,
        assistant_message_count=assistant_count,
        total_input_tokens=int(total_input),
        total_output_tokens=int(total_output),
        total_cost_usd=float(total_cost),
    )


async def delete_conversation(
    user_id: uuid.UUID, session: AsyncSession, conversation_id: uuid.UUID
) -> bool:
    """Delete an existing conversation owned by the given user.

    Heartbeat-labelled conversations are protected: the scheduler
    persists into them and the user re-creates one by re-syncing,
    so a casual delete from the sidebar would only confuse next sync.
    The DELETE route translates ``False`` to a 404 (same as "not
    yours"), which is the right surface for the protection — the UI
    hides the delete affordance for heartbeat rows anyway.

    Returns:
        ``True`` when a conversation was deleted, otherwise ``False``.
    """
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user_id)
    )
    result = await session.execute(stmt)
    conversation = result.scalar_one_or_none()

    if conversation is None:
        return False

    if HEARTBEAT_LABEL in (conversation.labels or []):
        return False

    await session.delete(conversation)
    await session.commit()
    return True


# Label that marks a conversation as the heartbeat sink for a workspace.
# The frontend's NAV_CHATS_LABELS includes a matching entry so the row
# renders with the 🫀 colour and the sidebar can pin / group it without
# a schema change.
HEARTBEAT_LABEL = "heartbeat"
# Conversation title used when the heartbeat sink is auto-created.
# Kept verbatim so the UI can match on it for future "rename guard"
# rules, but the user is free to rename — get_or_create only inspects
# the label, not the title.
HEARTBEAT_CONVERSATION_TITLE = "🫀 Heartbeat"


async def get_or_create_heartbeat_conversation(
    user_id: uuid.UUID, session: AsyncSession
) -> Conversation:
    """Return the user's heartbeat conversation, creating it on first call.

    Lookup is by ``(user_id, HEARTBEAT_LABEL in labels)``. The newest
    row wins when somehow there's more than one — the constraint is
    soft (a user could manually label a second conversation), and the
    sync helper only needs *a* destination, not the canonical one.

    Caller owns the transaction; this helper flushes but does not
    commit so it can participate in a larger transaction (e.g. the
    workspace bootstrap that also writes the seeding row).
    """
    # JSON-column containment isn't portable across SQLite (tests) and
    # Postgres (prod), so filter in Python over the user's rows. A user
    # typically has < a few hundred conversations — well within budget
    # for the once-per-sync lookup. Promote to a dialect-specific
    # ``.where`` if this ever becomes hot.
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
    )
    result = await session.execute(stmt)
    for conv in result.scalars():
        if HEARTBEAT_LABEL in (conv.labels or []):
            return conv

    from datetime import UTC  # noqa: PLC0415

    now = datetime.now(UTC).replace(tzinfo=None)
    conversation = Conversation(
        id=uuid.uuid4(),
        user_id=user_id,
        title=HEARTBEAT_CONVERSATION_TITLE,
        created_at=now,
        updated_at=now,
        labels=[HEARTBEAT_LABEL],
    )
    session.add(conversation)
    await session.flush()
    return conversation
