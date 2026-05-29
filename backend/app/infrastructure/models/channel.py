"""Third-party channel binding ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models.base import Base


class ChannelLinkCode(Base):
    """A short-lived one-time-use code for linking a Pawrrtal user to a third-party channel."""

    __tablename__ = "channel_link_codes"

    # HMAC-SHA-256 hex hash of the user-facing code. PK so lookups are
    # by hash; the plaintext is never persisted.
    code_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Indexed because the cleanup job scans on (expires_at, used_at IS NULL)
    # to GC unredeemed codes; matches migration 007's ix_channel_link_codes_expires_at.
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # NULL while the code is unredeemed; populated once the bot consumes it.
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChannelBinding(Base):
    """A binding between a Pawrrtal user and a third-party channel."""

    __tablename__ = "channel_bindings"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_user_id",
            name="uq_channel_bindings_provider_external_user",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # The Pawrrtal user ID.
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    # Stable identity from the provider (Telegram user_id as text so the
    # column type is the same across providers).
    external_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Default chat to push to. For Telegram direct chats this matches
    # external_user_id; for groups it's the chat where the bind happened.
    external_chat_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Display handle captured at bind time. Surfaced in the Settings UI
    # connected-state ("@<display_handle>"); never trusted for auth.
    display_handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Whether the Telegram chat has Topics (forum threads) enabled.
    has_topics_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


__all__ = ["ChannelBinding", "ChannelLinkCode"]
