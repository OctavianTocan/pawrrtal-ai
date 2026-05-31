"""Conversation and chat-message ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Text

from app.infrastructure.models.base import Base


class SenderType(Enum):
    """Identifies who sent a message in a conversation."""

    AI = "ai"
    USER = "user"


_REASONING_EFFORT_VALUES = ("minimal", "low", "medium", "high", "extra-high")


class Conversation(Base):
    """Conversation metadata stored in the application database.

    Renderable message content lives in ``chat_messages``. Provider-native
    transcript stores are only used as implementation details.
    """

    __tablename__ = "conversations"
    __table_args__ = (
        # Pin ``reasoning_effort`` to the ``ReasoningEffort`` literal values
        # (or NULL). The setter in ``app.channels.crud`` accepts ``str | None``,
        # so without this constraint a typo or stale enum value could land in
        # the DB and silently break provider resolution. SQL ``CHECK`` allows
        # NULL by default, which is what we want for "let the provider pick".
        # Issue #367.
        CheckConstraint(
            "reasoning_effort IN (" + ", ".join(f"'{v}'" for v in _REASONING_EFFORT_VALUES) + ")",
            name="ck_conversations_reasoning_effort_values",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_unread: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # JSON array of label IDs (e.g. ["bug", "feature"]). Validated against
    # the frontend pre-defined CHAT_LABELS list — the backend stores raw
    # IDs without enforcement so adding a new label client-side does not
    # require a migration. Defaults to an empty list rather than NULL so
    # `Conversation.labels.append(...)` always works without a None guard.
    labels: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Optional FK to the project this conversation belongs to. NULL means
    # the conversation lives in the unattached "Chats" list at the bottom
    # of the sidebar; setting it surfaces the row under the project's
    # nested children. ON DELETE SET NULL so removing a project keeps the
    # conversations around and just unattaches them.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    # Channel that created this conversation (e.g. "telegram", "web").
    origin_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Telegram Bot API 9.3+ topic thread ID. NULL for non-topic DMs.
    telegram_thread_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Codex SDK thread ID for native openai_codex provider resume support.
    # Stored when the provider emits a "codex_thread_created" internal event.
    codex_thread_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # SHA-256 fingerprint of the prompt/model used to create codex_thread_id.
    # A mismatch means prompt shape changed and the native thread must restart.
    codex_thread_prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Lifecycle marker for the auto-title feature:
    # NULL = not yet titled, "auto" = generated, "user" = user-edited.
    title_set_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Per-conversation verbose level for streaming UX (PR 07):
    # 0 = quiet (only deltas + errors), 1 = normal (+ tool_use names),
    # 2 = detailed (+ thinking + tool inputs). NULL inherits
    # settings.telegram_verbose_default (or 1 if unset).
    verbose_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Per-conversation reasoning depth. One of the ReasoningEffort literal
    # values ("minimal" | "low" | "medium" | "high" | "extra-high") or NULL
    # to let the provider pick its default. Pinned by the
    # ``ck_conversations_reasoning_effort_values`` CHECK constraint above
    # so bad enum strings never make it to the DB. Mirrors verbose_level's
    # plumbing: a chat request may still override per-turn, but absent that
    # the persisted value is what the turn runner forwards to the provider.
    reasoning_effort: Mapped[str | None] = mapped_column(String(16), nullable=True)


class ChatMessage(Base):
    """A single chat message within a conversation, including reasoning state.

    This is the source of truth for what the chat UI renders on a refresh:
    role, plain-text content, thinking/reasoning text, tool invocations and
    their results, the arrival-ordered timeline, and the reasoning duration.
    Provider-agnostic turns write here; provider-native transcript stores
    are not used for rendering history.
    """

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id", ondelete="CASCADE"))
    # Stable insertion order within a conversation. Only ever increases —
    # regenerate replaces the row in place rather than allocating a new ordinal.
    ordinal: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, default="")
    thinking: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON arrays — None when absent so the column shrinks to NULL on reads.
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    timeline: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    thinking_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "streaming" | "complete" | "failed" — only meaningful on assistant rows.
    assistant_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Workspace-relative path to a file the agent delivered via send_message.
    attachment: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    # MIME type detected from the attachment path (e.g. "image/png").
    attachment_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


__all__ = ["ChatMessage", "Conversation", "SenderType"]
