"""This module contains the conversation endpoints for the API."""

import logging
import uuid
from typing import Any, Literal, cast

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations import crud
from app.conversations.gemini_utils import generate_text_once
from app.conversations.messages_crud import get_messages_for_conversation
from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session
from app.models import ChatMessage, Conversation
from app.schemas import (
    ChatMessageRead,
    ConversationCreate,
    ConversationRead,
    ConversationUpdate,
)

# Logger follows module namespace conventions for consistent filtering and tracing.
logger = logging.getLogger(__name__)

# Generated conversation titles longer than this are treated as overflow / model
# refusal text and rejected in favour of falling back to the heuristic title.
MAX_GENERATED_TITLE_LENGTH = 80


def _serialize_chat_message(row: ChatMessage) -> ChatMessageRead:
    """Convert a ``ChatMessage`` ORM row into the API ``ChatMessageRead`` shape."""
    role = cast(Literal["user", "assistant"], row.role)
    status_value = (
        cast(Literal["streaming", "complete", "failed"], row.assistant_status)
        if row.assistant_status in {"streaming", "complete", "failed"}
        else None
    )
    return ChatMessageRead(
        role=role,
        content=row.content,
        thinking=row.thinking,
        tool_calls=row.tool_calls,
        timeline=row.timeline,
        thinking_duration_seconds=row.thinking_duration_seconds,
        assistant_status=status_value,
        duration_ms=_message_duration_ms(row),
    )


def _message_duration_ms(row: ChatMessage) -> int | None:
    """Best-effort persisted assistant turn duration from row timestamps."""
    if row.role != "assistant" or row.created_at is None or row.updated_at is None:
        return None
    return max(0, round((row.updated_at - row.created_at).total_seconds() * 1000))


GENERATED_TITLE_REJECTION_PHRASES = (
    "api key",
    "authentication",
    "unauthorized",
    "invalid request",
    "no api",
    "pass a valid",
    "was provided",
)


def _normalize_generated_title(content: Any) -> str | None:
    """Return a usable generated title, or ``None`` for provider/error text."""
    title = str(content or "").strip().strip('"').strip("'").strip()
    if not title:
        return None

    collapsed_title = " ".join(title.split())
    title_lower = collapsed_title.lower()
    if any(phrase in title_lower for phrase in GENERATED_TITLE_REJECTION_PHRASES):
        return None

    if len(collapsed_title) > MAX_GENERATED_TITLE_LENGTH:
        return None

    return collapsed_title


def get_conversations_router() -> APIRouter:  # noqa: C901 — FastAPI router builders aggregate many route handlers; complexity reflects route count, not branching depth
    """Get a router for the conversations API."""
    router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])

    @router.get("/{conversation_id}/messages")
    async def get_conversation_messages(
        conversation_id: uuid.UUID,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> list[ChatMessageRead]:
        """Return message history for a conversation.

        Verifies ownership first, then reads the persisted ``chat_messages``
        rows in insertion order. Each row carries the full chain-of-thought
        state (thinking, tool calls, timeline, duration), so a hard reload
        rehydrates the chat exactly as the user last saw it.
        """
        conversation = await crud.get_conversation(user.id, session, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        rows = await get_messages_for_conversation(session, conversation_id)
        return [_serialize_chat_message(row) for row in rows]

    @router.get("/{conversation_id}")
    async def get_conversation(
        conversation_id: uuid.UUID,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> ConversationRead | None:
        """Return metadata for a single conversation."""
        conversation = await crud.get_conversation(user.id, session, conversation_id)
        if conversation:
            return ConversationRead(
                title=conversation.title,
                id=conversation.id,
                user_id=conversation.user_id,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                is_archived=conversation.is_archived,
                is_flagged=conversation.is_flagged,
                is_unread=conversation.is_unread,
                status=conversation.status,
                model_id=conversation.model_id,
                labels=list(conversation.labels or []),
                project_id=conversation.project_id,
                provider_session_id=conversation.provider_session_id,
            )
        return None

    @router.post("/{conversation_id}/title")
    async def generate_conversation_title(
        conversation_id: uuid.UUID,
        first_message: str = "",
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> str:
        """Generate and persist a short conversation title from the first message."""
        try:
            raw_title = await generate_text_once(
                "Generate a short title (max 8 words) for the conversation based on "
                "this first message: " + first_message + ". Return only the title, nothing else."
            )
        except Exception:
            # Gemini API errors (invalid key, model unavailable, rate limit) must
            # not 500 the whole request — the title is best-effort UI polish.
            logger.exception(
                "Title generation failed for conversation %s — returning empty title",
                conversation_id,
            )
            return ""

        generated_title = _normalize_generated_title(raw_title)
        if generated_title is None:
            logger.warning(
                "Skipping unusable generated title for conversation %s",
                conversation_id,
            )
            return ""

        await crud.update_conversation_title(
            title=generated_title,
            user_id=user.id,
            conversation_id=conversation_id,
            session=session,
        )
        return generated_title

    @router.patch("/{conversation_id}", response_model=ConversationRead)
    async def update_conversation(
        conversation_id: uuid.UUID,
        payload: ConversationUpdate,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> ConversationRead:
        """Update mutable conversation metadata for the authenticated user.

        Accepts any combination of: title, is_archived, is_flagged, is_unread,
        and status. Only fields present in the payload are updated.
        """
        if payload.title is not None and not payload.title.strip():
            raise HTTPException(status_code=422, detail="Conversation title cannot be empty")

        conversation = await crud.update_conversation(
            payload=payload,
            user_id=user.id,
            conversation_id=conversation_id,
            session=session,
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return ConversationRead(
            title=conversation.title,
            id=conversation.id,
            user_id=conversation.user_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            is_archived=conversation.is_archived,
            is_flagged=conversation.is_flagged,
            is_unread=conversation.is_unread,
            status=conversation.status,
            model_id=conversation.model_id,
            labels=list(conversation.labels or []),
            project_id=conversation.project_id,
            provider_session_id=conversation.provider_session_id,
        )

    @router.delete("/{conversation_id}", status_code=204)
    async def delete_conversation(
        conversation_id: uuid.UUID,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> None:
        """Delete a conversation owned by the authenticated user."""
        deleted = await crud.delete_conversation(user.id, session, conversation_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")

    @router.get("")
    async def list_conversations(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> list[ConversationRead]:
        """List all conversations for the authenticated user, most recent first."""
        conversations: list[Conversation] = await crud.list_conversations_for_user(user.id, session)
        return [
            ConversationRead(
                title=conversation.title,
                id=conversation.id,
                user_id=conversation.user_id,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                is_archived=conversation.is_archived,
                is_flagged=conversation.is_flagged,
                is_unread=conversation.is_unread,
                status=conversation.status,
                model_id=conversation.model_id,
                labels=list(conversation.labels or []),
                project_id=conversation.project_id,
                provider_session_id=conversation.provider_session_id,
            )
            for conversation in conversations
        ]

    @router.post("/{conversation_id}")
    async def create_conversation(
        conversation_id: uuid.UUID,
        payload: ConversationCreate | None = Body(default=None),
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> ConversationRead:
        """Create a new conversation with an immediate initial title.

        Frontend generates the UUID first; this endpoint persists metadata before
        the first streamed turn.
        """
        creation_payload = payload or ConversationCreate()
        try:
            new_conversation: Conversation = await crud.create_conversation(
                user.id,
                session,
                ConversationCreate(id=conversation_id, title=creation_payload.title),
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

        return ConversationRead(
            title=new_conversation.title,
            id=new_conversation.id,
            user_id=new_conversation.user_id,
            created_at=new_conversation.created_at,
            updated_at=new_conversation.updated_at,
            is_archived=new_conversation.is_archived,
            is_flagged=new_conversation.is_flagged,
            is_unread=new_conversation.is_unread,
            status=new_conversation.status,
            model_id=new_conversation.model_id,
            labels=list(new_conversation.labels or []),
            project_id=new_conversation.project_id,
            provider_session_id=new_conversation.provider_session_id,
        )

    return router
