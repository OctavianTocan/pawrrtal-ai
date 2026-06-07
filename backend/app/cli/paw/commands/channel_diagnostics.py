"""Read-only local diagnostics for channel operator commands."""

from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli.paw.errors import LocalError
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import User, async_session_maker
from app.infrastructure.models.channel import ChannelBinding
from app.infrastructure.models.conversation import ChatMessage, Conversation
from app.infrastructure.models.governance import CostLedger

TELEGRAM_PROVIDER = "telegram"


async def diagnose_telegram_state(
    *,
    limit: int,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Read local DB state needed to explain Telegram delivery failures."""
    async with async_session_maker() as session:
        bindings = await _diagnose_bindings(session)
        recent_messages = await _diagnose_recent_messages(session, limit=limit)
        trace = await _diagnose_conversation_trace(session, conversation_id, limit=limit)
        stuck_messages = [
            message for message in recent_messages if message["assistant_status"] == "streaming"
        ]
    return {
        "configured": bool(settings.telegram_bot_token),
        "mode": settings.telegram_mode,
        "bindings": bindings,
        "recent_messages": recent_messages,
        "stuck_streaming_messages": stuck_messages,
        "conversation_trace": trace,
    }


async def _diagnose_bindings(session: AsyncSession) -> list[dict[str, Any]]:
    """Return Telegram channel bindings with best-effort user emails."""
    user_model = cast(Any, User)
    result = await session.execute(
        select(ChannelBinding, user_model.email)
        .outerjoin(User, user_model.id == ChannelBinding.user_id)
        .where(ChannelBinding.provider == TELEGRAM_PROVIDER)
        .order_by(ChannelBinding.created_at.desc())
    )
    return [
        {
            "user_id": str(binding.user_id),
            "email": email,
            "external_user_id": binding.external_user_id,
            "external_chat_id": binding.external_chat_id,
            "display_handle": binding.display_handle,
            "created_at": binding.created_at.isoformat(),
        }
        for binding, email in result.all()
    ]


async def _diagnose_recent_messages(session: AsyncSession, *, limit: int) -> list[dict[str, Any]]:
    """Return recent Telegram-originated messages in reverse chronological order."""
    result = await session.execute(
        select(ChatMessage, Conversation.model_id)
        .join(Conversation, Conversation.id == ChatMessage.conversation_id)
        .where(Conversation.origin_channel == TELEGRAM_PROVIDER)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    return [_message_diagnostic(message, model_id=model_id) for message, model_id in result.all()]


async def _diagnose_conversation_trace(
    session: AsyncSession,
    conversation_id: str | None,
    *,
    limit: int,
) -> dict[str, Any] | None:
    """Return conversation-level Codex/thread state plus recent messages."""
    if conversation_id is None:
        return None
    try:
        parsed_id = uuid.UUID(conversation_id)
    except ValueError as exc:
        raise LocalError(f"Invalid conversation UUID: {conversation_id}") from exc
    conversation = await session.get(Conversation, parsed_id)
    if conversation is None:
        raise LocalError(f"No conversation found for id {conversation_id}.")
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == parsed_id)
        .order_by(ChatMessage.ordinal.desc())
        .limit(limit)
    )
    messages = [
        _message_diagnostic(message, model_id=conversation.model_id) for message in result.scalars()
    ]
    return {
        "conversation_id": str(conversation.id),
        "origin_channel": conversation.origin_channel,
        "telegram_thread_id": conversation.telegram_thread_id,
        "model_id": conversation.model_id,
        "provider_session_id": conversation.provider_session_id,
        "reasoning_effort": conversation.reasoning_effort,
        "verbose_level": conversation.verbose_level,
        "workspace_skill_prompt_mode": settings.workspace_skill_prompt_mode,
        "recent_usage": await _diagnose_recent_usage(session, parsed_id, limit=limit),
        "messages": messages,
    }


def _message_diagnostic(message: ChatMessage, *, model_id: str | None) -> dict[str, Any]:
    """Render a chat message row for operator diagnostics."""
    timeline = message.timeline if isinstance(message.timeline, list) else []
    content = message.content or ""
    return {
        "message_id": str(message.id),
        "conversation_id": str(message.conversation_id),
        "role": message.role,
        "ordinal": message.ordinal,
        "content": content,
        "content_preview": content[:160],
        "assistant_status": message.assistant_status,
        "model_id": model_id,
        "timeline_count": len(timeline),
        "thinking_present": bool(message.thinking),
        "thinking_chars": len(message.thinking or ""),
        "thinking_duration_seconds": message.thinking_duration_seconds,
        "tool_call_count": len(message.tool_calls or []),
        "duration_ms": _message_duration_ms(message),
        "created_at": message.created_at.isoformat(),
        "updated_at": message.updated_at.isoformat(),
    }


async def _diagnose_recent_usage(
    session: AsyncSession, conversation_id: uuid.UUID, *, limit: int
) -> list[dict[str, Any]]:
    """Return recent cost ledger rows for a focused Telegram conversation."""
    result = await session.execute(
        select(CostLedger)
        .where(CostLedger.conversation_id == conversation_id)
        .order_by(CostLedger.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "created_at": row.created_at.isoformat(),
            "model_id": row.model_id,
            "surface": row.surface,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "cost_usd": row.cost_usd,
        }
        for row in result.scalars()
    ]


def _message_duration_ms(message: ChatMessage) -> int | None:
    """Best-effort persisted turn duration from assistant row timestamps."""
    if message.role != "ai" or message.updated_at is None or message.created_at is None:
        return None
    return max(0, round((message.updated_at - message.created_at).total_seconds() * 1000))
