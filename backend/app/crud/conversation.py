"""CRUD operations for the Conversation model.

All functions enforce user ownership — a user can only access or modify
their own conversations.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio.session import AsyncSession

from app.crud.subagent import cancel_running_subagents_for_conversation
from app.models import Conversation
from app.schemas import ConversationCreate, ConversationUpdate


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


async def delete_conversation(
    user_id: uuid.UUID, session: AsyncSession, conversation_id: uuid.UUID
) -> bool:
    """Delete an existing conversation owned by the given user.

    Cascade-cancels every still-running subagent in the conversation
    *before* the row is removed so the audit trail records why each
    child died (``error="conversation deleted"``) rather than losing
    them to the FK CASCADE.  The DB-level CASCADE on
    ``subagents.conversation_id`` is the safety net for subagents
    whose live ``asyncio.Task`` ref lives on a different worker.

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

    await cancel_running_subagents_for_conversation(
        session, conversation_id=conversation_id
    )
    await session.delete(conversation)
    await session.commit()
    return True
